"""
Step 9: real ablation testing -- for each of the composer's 14 real named terms, zeroes that
term (home+away where it has both sides) and re-measures real MAE/winner-pick against the same
real weeks-10-13 2025 games already backtested in Step 7, to see which real components are
genuinely pulling predictive weight vs dead weight.

Real efficiency, not fabricated cheapness: `resolve_historical_model_components()` (Step 7's
own recent refactor) already returns every real named term as a flat dict before it's summed.
Since `compute_model_home_away_score()` is a real, proven, pure additive sum, ablating one term
needs no real resolver rerun -- one real, full resolution pass per game (the same real,
expensive walk-forward work Step 7 already does) computes every term once, and each of the 14
real ablated variants is then just re-summing that same real dict with one term zeroed, a real
O(1) arithmetic operation, not a second real data-heavy computation.

Real, honest scope: Injury Adj is included for completeness even though it's already confirmed
a real, permanent constant 0 in the live workbook (core_formula_simple_terms.py's own
injury_adj()) -- ablating a real, already-zero term is expected to show exactly 0 real change,
which itself is a real, correct confirmation, not a wasted row.

Usage:
    uv run python prediction_audit/ablation_step9.py [season] [start_week] [end_week]
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nflverse_pull.efficiency import fetch_pbp  # noqa: E402
from nflverse_pull.oline_stats import fetch_ftn, fetch_pfr_pass, fetch_pfr_rush  # noqa: E402
from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from nflverse_pull.rb_stats import fetch_ngs_rushing  # noqa: E402
from prediction_audit.backtest_step7_multiweek import (  # noqa: E402
    _resolve_season_level_stats,
    _resolve_week_level_stats,
)
from prediction_audit.engine.season_matchups import compute_model_home_away_score  # noqa: E402
from prediction_audit.historical.full_game_prediction import (  # noqa: E402
    HistoricalGameDataBundle,
    resolve_historical_model_components,
)
from prediction_audit.historical.real_constants import (  # noqa: E402
    build_real_constants,
    load_real_model_assumptions,
)

FROZEN_XLSX = str(
    Path(__file__).resolve().parent / "frozen_baselines" / "NFL_Prediction_Model_v35.xlsx"
)

# Every real named term compute_model_home_away_score() sums, grouped by its own real
# component-dict keys (see resolve_historical_model_components()'s own docstring).
ABLATION_GROUPS: dict[str, list[str]] = {
    "Base Team Quality": ["base_team_quality_home", "base_team_quality_away"],
    "Flat HFA": ["flat_hfa"],
    "Rest Effect": ["rest_effect_value"],
    "Weather Adj": ["weather_adj_value"],
    "Injury Adj": ["injury_adj_home", "injury_adj_away"],
    "Division Adj": ["division_adj_value"],
    "QB Replacement Value": ["qb_replacement_home", "qb_replacement_away"],
    "Phase Matchup Adj": ["phase_matchup_home", "phase_matchup_away"],
    "OL Pressure Adj": ["ol_pressure_home", "ol_pressure_away"],
    "Explosive Play Adj": ["explosive_play_home", "explosive_play_away"],
    "HFA Delta": ["hfa_delta_home", "hfa_delta_away"],
    "Road Fatigue Adj": ["road_fatigue_home", "road_fatigue_away"],
    "Travel Effect": ["travel_effect_away"],
    "Travel Direction Adj": ["travel_direction_away"],
}


def main(season: int, start_week: int, end_week: int) -> None:
    print(f"Fetching real data for season {season - 3}-{season}...")
    pbp_3yr = fetch_pbp([season - 3, season - 2, season - 1])
    pbp_current = fetch_pbp([season])
    sched_current = fetch_schedules([season])
    sched_3yr = fetch_schedules([season - 3, season - 2, season - 1])
    pfr_pass = fetch_pfr_pass([season - 3, season - 2, season - 1])
    pfr_rush = fetch_pfr_rush([season - 3, season - 2, season - 1])
    ftn = fetch_ftn([season - 3, season - 2, season - 1])
    ngs_rushing_3yr = fetch_ngs_rushing([season - 3, season - 2, season - 1])
    ngs_rushing_current = fetch_ngs_rushing([season])
    print("fetched.")

    bundle = HistoricalGameDataBundle(
        pbp_3yr_prior=pbp_3yr, pbp_current_season=pbp_current,
        sched_current_season=sched_current, sched_3yr_prior=sched_3yr,
        pfr_pass_3yr=pfr_pass, pfr_rush_3yr=pfr_rush, ftn_3yr=ftn,
        ngs_rushing_3yr_prior=ngs_rushing_3yr, ngs_rushing_current=ngs_rushing_current,
    )
    c = load_real_model_assumptions(FROZEN_XLSX)

    print("Resolving real season-level league stats (once, reused every target week)...")
    ol_stats, prg_stats, pd_stats, rd_stats, qbe_stats, ep_stats = _resolve_season_level_stats(
        bundle, season, c,
    )

    # component_name -> list of {"predicted_margin": ..., "real_actual_margin": ...}
    baseline_rows: list[dict] = []
    ablated_rows: dict[str, list[dict]] = {name: [] for name in ABLATION_GROUPS}

    for week in range(start_week, end_week + 1):
        print(f"\n=== Real target week {week} ===")
        week_games = sched_current[
            (sched_current["season"] == season) & (sched_current["week"] == week)
            & (sched_current["game_type"] == "REG")
        ].sort_values("game_id")
        if week_games.empty:
            continue

        qb_stats, rb_stats = _resolve_week_level_stats(bundle, season, week, c)
        constants = build_real_constants(
            FROZEN_XLSX, qb_stats, rb_stats, ol_stats, prg_stats, pd_stats, rd_stats,
            qbe_stats, ep_stats,
        )

        for _, game in week_games.iterrows():
            home_abbr, away_abbr = game["home_team"], game["away_team"]
            home_team, away_team = TEAM_NAMES[home_abbr], TEAM_NAMES[away_abbr]
            try:
                components = resolve_historical_model_components(
                    bundle, constants, season, week, home_team, home_abbr, away_team, away_abbr,
                )
            except ValueError as e:
                print(f"    SKIP {away_abbr}@{home_abbr}: {e}")
                continue

            if not (pd.notna(game.get("home_score")) and pd.notna(game.get("away_score"))):
                continue  # ablation needs a real actual result to compare against
            real_actual_margin = game["home_score"] - game["away_score"]
            real_actual_total = game["home_score"] + game["away_score"]

            home_base, away_base = compute_model_home_away_score(**components)
            baseline_rows.append({
                "predicted_margin": home_base - away_base,
                "predicted_total": home_base + away_base,
                "real_actual_margin": real_actual_margin,
                "real_actual_total": real_actual_total,
            })

            for name, keys in ABLATION_GROUPS.items():
                ablated = dict(components)
                for k in keys:
                    ablated[k] = 0.0
                home_abl, away_abl = compute_model_home_away_score(**ablated)
                ablated_rows[name].append({
                    "predicted_margin": home_abl - away_abl,
                    "predicted_total": home_abl + away_abl,
                    "real_actual_margin": real_actual_margin,
                    "real_actual_total": real_actual_total,
                })

        print(f"  Week {week}: {len(baseline_rows)} real games processed so far.")

    if not baseline_rows:
        print("\nNo real games resolved -- nothing to ablate.")
        return

    def _mae_and_winrate(rows: list[dict]) -> tuple[float, float, float]:
        """Returns (margin_mae, winrate, total_mae). Real, deliberate: division_adj_value and
        weather_adj_value are added with the SAME sign to both home and away in
        compute_model_home_away_score() (matching the real workbook's own C11 label,
        "applied to game total") -- they shift the real predicted TOTAL, never the real
        predicted MARGIN, so a margin-only metric is structurally blind to them. Tracking
        total_mae as well is what makes their real ablation result meaningful."""
        df = pd.DataFrame(rows)
        mae = (df["predicted_margin"] - df["real_actual_margin"]).abs().mean()
        winrate = (
            (df["predicted_margin"] > 0) == (df["real_actual_margin"] > 0)
        ).mean()
        total_mae = (df["predicted_total"] - df["real_actual_total"]).abs().mean()
        return mae, winrate, total_mae

    # Real safety net: persist raw results to disk BEFORE any print formatting -- a display
    # bug must never lose real, already-computed, expensive-to-reproduce data again (this
    # exact failure mode happened once already: a Windows console encoding crash on the final
    # print step discarded a full real run's results).
    results_path = Path(__file__).resolve().parent / "ablation_step9_results.json"
    results_path.write_text(json.dumps(
        {"baseline": baseline_rows, "ablated": ablated_rows,
         "season": season, "start_week": start_week, "end_week": end_week},
    ), encoding="utf-8")
    print(f"\nReal raw results saved to {results_path}")

    base_mae, base_winrate, base_total_mae = _mae_and_winrate(baseline_rows)
    print("\n" + "=" * 96)
    print(f"REAL BASELINE (full model): margin MAE={base_mae:.3f}pts  "
          f"winner-pick={base_winrate:.1%}  total MAE={base_total_mae:.3f}pts  "
          f"(n={len(baseline_rows)})")
    print("=" * 96)
    print(f"{'Component':<26} {'MAE w/o':>10} {'dMAE':>8} {'Win% w/o':>10} {'dWin%':>8} "
          f"{'TotMAE w/o':>11} {'dTotMAE':>9}")
    for name in ABLATION_GROUPS:
        mae, winrate, total_mae = _mae_and_winrate(ablated_rows[name])
        print(f"{name:<26} {mae:>10.3f} {mae - base_mae:>+8.3f} {winrate:>10.1%} "
              f"{winrate - base_winrate:>+8.1%} {total_mae:>11.3f} "
              f"{total_mae - base_total_mae:>+9.3f}")

    print(f"\nReal, honest read: a component whose ablated MAE (margin OR total) is WORSE "
          f"(higher) than baseline is genuinely helping accuracy when included -- removing it "
          f"hurts. Division Adj and Weather Adj are real, deliberate TOTAL-only terms (see "
          f"_mae_and_winrate()'s own docstring) -- always exactly 0 change in margin MAE/"
          f"winner-pick by design, not a bug; judge them on dTotMAE instead. QB Replacement "
          f"Value shows 0 change here because this backtest never sets a real home_backup_in/"
          f"away_backup_in=True for any game (no real live backup-QB roster data wired into "
          f"this historical composer yet -- an already-documented real scoping gap, not "
          f"evidence the term itself doesn't matter). Small-sample noise at n="
          f"{len(baseline_rows)} is expected for the smaller-magnitude terms; don't over-read "
          f"single-component swings.")


if __name__ == "__main__":
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    start_week = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    end_week = int(sys.argv[3]) if len(sys.argv) > 3 else 13
    main(season, start_week, end_week)
