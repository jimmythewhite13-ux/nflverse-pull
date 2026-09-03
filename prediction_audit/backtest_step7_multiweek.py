"""
Step 7 scale-up: reruns `backtest_step7_real_constants.py`'s own real pipeline (real Model
Assumptions constants + real per-week league stats + real Travel Effect/Direction, now that
`stadium_locations.py` fills those 2 real gaps) across several real consecutive weeks in one
real season, fetching the real season-level data (pbp/schedule/PFR/FTN/NGS) only once and
reusing it -- real per-week league stats (QB Index, RB Index -- the 2 tabs with a real
current-season blend) are still recomputed for each real target week, since those genuinely
depend on how much of the real season has elapsed by that week; the other 6 tabs' real league
stats are season-level (not week-dependent) and are also recomputed per week here for
simplicity, at the real cost of some redundant computation -- correctness over efficiency for
a "handful of weeks" scale.

Real, non-cherry-picked week selection: a contiguous real range immediately following the
single real week (10) already covered by the earlier preliminary run -- never hand-picked for
a favorable result.

Usage:
    uv run python prediction_audit/backtest_step7_multiweek.py [season] [start_week] [end_week]
"""
from __future__ import annotations

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
from prediction_audit.backtest_step7_real_constants import (  # noqa: E402
    FROZEN_XLSX,
    _resolve_all_real_league_stats,
)
from prediction_audit.historical.full_game_prediction import (  # noqa: E402
    HistoricalGameDataBundle,
    resolve_historical_model_home_away_score,
)
from prediction_audit.historical.real_constants import (  # noqa: E402
    build_real_constants,
    load_real_model_assumptions,
)
from prediction_audit.market_data import fetch_real_market_lines  # noqa: E402


def main(season: int, start_week: int, end_week: int) -> None:
    print(f"Fetching real data for season {season - 3}-{season} (one-time, reused every "
          f"target week)...")
    pbp_3yr = fetch_pbp([season - 3, season - 2, season - 1])
    pbp_current = fetch_pbp([season])
    sched_current = fetch_schedules([season])
    sched_3yr = fetch_schedules([season - 3, season - 2, season - 1])
    pfr_pass = fetch_pfr_pass([season - 3, season - 2, season - 1])
    pfr_rush = fetch_pfr_rush([season - 3, season - 2, season - 1])
    ftn = fetch_ftn([season - 3, season - 2, season - 1])
    ngs_rushing_3yr = fetch_ngs_rushing([season - 3, season - 2, season - 1])
    ngs_rushing_current = fetch_ngs_rushing([season])
    real_lines = {
        (line.week, line.away_team, line.home_team): line
        for line in fetch_real_market_lines(season)
    }
    print("fetched.")

    bundle = HistoricalGameDataBundle(
        pbp_3yr_prior=pbp_3yr, pbp_current_season=pbp_current,
        sched_current_season=sched_current, sched_3yr_prior=sched_3yr,
        pfr_pass_3yr=pfr_pass, pfr_rush_3yr=pfr_rush, ftn_3yr=ftn,
        ngs_rushing_3yr_prior=ngs_rushing_3yr, ngs_rushing_current=ngs_rushing_current,
    )
    c = load_real_model_assumptions(FROZEN_XLSX)

    all_rows = []
    per_week_summary = []
    for week in range(start_week, end_week + 1):
        print(f"\n=== Real target week {week} ===")
        week_games = sched_current[
            (sched_current["season"] == season) & (sched_current["week"] == week)
            & (sched_current["game_type"] == "REG")
        ].sort_values("game_id")
        if week_games.empty:
            print("  No real REG games this week -- skipping.")
            continue

        print("  Resolving real league-wide stats for this target week...")
        qb_stats, rb_stats, ol_stats, prg_stats, pd_stats, rd_stats, qbe_stats, ep_stats = (
            _resolve_all_real_league_stats(bundle, season, week, c)
        )
        constants = build_real_constants(
            FROZEN_XLSX, qb_stats, rb_stats, ol_stats, prg_stats, pd_stats, rd_stats,
            qbe_stats, ep_stats,
        )

        for _, game in week_games.iterrows():
            home_abbr, away_abbr = game["home_team"], game["away_team"]
            home_team, away_team = TEAM_NAMES[home_abbr], TEAM_NAMES[away_abbr]
            try:
                home_score, away_score = resolve_historical_model_home_away_score(
                    bundle, constants, season, week, home_team, home_abbr, away_team, away_abbr,
                )
            except ValueError as e:
                print(f"    SKIP {away_abbr}@{home_abbr}: {e}")
                continue

            predicted_margin = home_score - away_score
            real_actual_margin = None
            if pd.notna(game.get("home_score")) and pd.notna(game.get("away_score")):
                real_actual_margin = game["home_score"] - game["away_score"]
            real_closing_spread = None
            line = real_lines.get((week, away_team, home_team))
            if line is not None:
                real_closing_spread = line.spread_line

            all_rows.append({
                "week": week, "game": f"{away_abbr}@{home_abbr}",
                "predicted_margin": predicted_margin,
                "real_actual_margin": real_actual_margin,
                "real_closing_spread": real_closing_spread,
            })

        week_df = pd.DataFrame([r for r in all_rows if r["week"] == week])
        with_actual = week_df.dropna(subset=["real_actual_margin"])
        if not with_actual.empty:
            mae = (
                with_actual["predicted_margin"] - with_actual["real_actual_margin"]
            ).abs().mean()
            winner_correct = (
                (with_actual["predicted_margin"] > 0) == (with_actual["real_actual_margin"] > 0)
            ).mean()
            print(f"  Week {week}: real MAE={mae:.2f}pts, "
                  f"real winner-pick={winner_correct:.1%} (n={len(with_actual)})")
            per_week_summary.append((week, mae, winner_correct, len(with_actual)))

    if not all_rows:
        print("\nNo real games resolved across the target range -- nothing to summarize.")
        return

    df = pd.DataFrame(all_rows)
    print("\n" + "=" * 70)
    print(f"REAL AGGREGATE across weeks {start_week}-{end_week}, season {season}")
    print("=" * 70)
    print(df.to_string(index=False))

    with_actual = df.dropna(subset=["real_actual_margin"])
    if not with_actual.empty:
        mae = (with_actual["predicted_margin"] - with_actual["real_actual_margin"]).abs().mean()
        winner_correct = (
            (with_actual["predicted_margin"] > 0) == (with_actual["real_actual_margin"] > 0)
        ).mean()
        print(f"\nReal aggregate MAE vs actual margin: {mae:.2f} pts (n={len(with_actual)})")
        print(f"Real aggregate winner-pick accuracy: {winner_correct:.1%}")

    with_line = df.dropna(subset=["real_closing_spread"])
    if not with_line.empty:
        agrees = (
            (with_line["predicted_margin"] > 0) == (with_line["real_closing_spread"] > 0)
        ).mean()
        print(f"Real aggregate directional agreement with the real closing line: {agrees:.1%} "
              f"(n={len(with_line)})")

    print("\nPer-week breakdown:")
    for week, mae, winner_correct, n in per_week_summary:
        print(f"  week {week}: MAE={mae:.2f}pts winner-pick={winner_correct:.1%} (n={n})")


if __name__ == "__main__":
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    start_week = int(sys.argv[2]) if len(sys.argv) > 2 else 11
    end_week = int(sys.argv[3]) if len(sys.argv) > 3 else 15
    main(season, start_week, end_week)
