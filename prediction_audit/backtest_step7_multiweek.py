"""
Step 7 scale-up: reruns `backtest_step7_real_constants.py`'s own real pipeline (real Model
Assumptions constants + real per-week league stats + real Travel Effect/Direction, now that
`stadium_locations.py` fills those 2 real gaps) across several real consecutive weeks in one
real season, fetching the real season-level data (pbp/schedule/PFR/FTN/NGS) only once and
reusing it.

Real efficiency fix (this version): only QB Index and RB Index league stats genuinely depend
on the real target week (their own real current-season blend uses "how many games has this
team played so far"). The other 6 tabs' real league stats (OL Index, Pass Rush Generation,
Pass/Run Defense Matchup, QB Environment Model, Explosive Play Matchup) are real season-level
values with no week dependency -- resolved ONCE per season here, not once per target week. An
earlier version of this script recomputed all 8 tabs fresh for every week (documented there as
"correctness over efficiency for a handful of weeks"); live-timed, that redundant recomputation
of OL Index's own real 3-year PFR+FTN+pbp join alone made a 5-week run take multiple real hours
-- real evidence the earlier scoping call was wrong at this scale, not a hypothetical concern.

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

FROZEN_XLSX = str(
    Path(__file__).resolve().parent / "frozen_baselines" / "NFL_Prediction_Model_v35.xlsx"
)

from nflverse_pull.efficiency import fetch_pbp  # noqa: E402
from nflverse_pull.oline_stats import fetch_ftn, fetch_pfr_pass, fetch_pfr_rush  # noqa: E402
from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from nflverse_pull.rb_stats import fetch_ngs_rushing  # noqa: E402
from prediction_audit.engine.explosive_play_matchup import (  # noqa: E402
    ExplosivePlayMatchupConstants,
)
from prediction_audit.engine.offensive_line_index import OLIndexConstants  # noqa: E402
from prediction_audit.engine.pass_defense_matchup import PassDefenseMatchupConstants  # noqa: E402
from prediction_audit.engine.pass_rush_generation_index import (  # noqa: E402
    PassRushGenerationConstants,
)
from prediction_audit.engine.qb_environment_model import QBEnvironmentModelConstants  # noqa: E402
from prediction_audit.engine.qb_index import QBIndexConstants  # noqa: E402
from prediction_audit.engine.rb_index import RBIndexConstants  # noqa: E402
from prediction_audit.engine.run_defense_matchup import RunDefenseMatchupConstants  # noqa: E402
from prediction_audit.historical.explosive_play_matchup_historical import (  # noqa: E402
    resolve_explosive_play_matchup_league_stats,
)
from prediction_audit.historical.full_game_prediction import (  # noqa: E402
    HistoricalGameDataBundle,
    resolve_historical_model_home_away_score,
)
from prediction_audit.historical.offensive_line_index_historical import (  # noqa: E402
    resolve_ol_index_league_stats,
)
from prediction_audit.historical.pass_defense_matchup_historical import (  # noqa: E402
    resolve_pass_defense_matchup_league_stats,
)
from prediction_audit.historical.pass_rush_generation_index_historical import (  # noqa: E402
    resolve_pass_rush_generation_league_stats,
)
from prediction_audit.historical.qb_environment_model_historical import (  # noqa: E402
    resolve_qb_environment_model_league_stats,
)
from prediction_audit.historical.qb_index_historical import (  # noqa: E402
    resolve_qb_index_league_stats,
)
from prediction_audit.historical.rb_index_historical import (  # noqa: E402
    resolve_rb_index_league_stats,
)
from prediction_audit.historical.real_constants import (  # noqa: E402
    build_real_constants,
    load_real_model_assumptions,
)
from prediction_audit.historical.run_defense_matchup_historical import (  # noqa: E402
    resolve_run_defense_matchup_league_stats,
)
from prediction_audit.market_data import fetch_real_market_lines  # noqa: E402


def _resolve_season_level_stats(bundle: HistoricalGameDataBundle, target_season: int, c: dict):
    """Real league stats for the 6 tabs with NO real week dependency -- resolved once per
    season, reused for every real target week (see module docstring's real efficiency note)."""
    ol_placeholder = OLIndexConstants(
        decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
        blend_base=c[12], blend_per_game=c[13], blend_cap=c[14],
        weights={"pass_protection": c[58], "run_blocking": c[59], "sack_free_rate": c[81]},
        score_baseline=c[37], points_per_sd=c[38],
        league_avg=dict.fromkeys(["pass_protection", "run_blocking", "sack_free_rate"], 0.0),
        league_std=dict.fromkeys(["pass_protection", "run_blocking", "sack_free_rate"], 1.0),
    )
    ol_stats = resolve_ol_index_league_stats(
        bundle.pfr_pass_3yr, bundle.pfr_rush_3yr, bundle.pbp_3yr_prior, bundle.ftn_3yr,
        target_season, ol_placeholder,
    )
    print(f"  real OL Index league stats: {ol_stats}")

    prg_placeholder = PassRushGenerationConstants(
        decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
        weights={"sack_rate": c[119], "pressure_proxy": c[120], "blitz_rate": c[121]},
        league_avg=dict.fromkeys(["sack_rate", "pressure_proxy", "blitz_rate"], 0.0),
        league_std=dict.fromkeys(["sack_rate", "pressure_proxy", "blitz_rate"], 1.0),
    )
    prg_stats = resolve_pass_rush_generation_league_stats(
        bundle.pbp_3yr_prior, target_season, prg_placeholder,
    )
    print(f"  real Pass Rush Generation league stats: {prg_stats}")

    pd_placeholder = PassDefenseMatchupConstants(
        decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
        weights={"epa_dropback": c[87], "pass_success": c[88], "completion_pct": c[89],
                 "nya": c[90], "explosive_pass": c[91]},
        score_baseline=c[37], points_per_sd=c[38],
        league_avg=dict.fromkeys(
            ["epa_dropback", "pass_success", "completion_pct", "nya", "explosive_pass"], 0.0,
        ),
        league_std=dict.fromkeys(
            ["epa_dropback", "pass_success", "completion_pct", "nya", "explosive_pass"], 1.0,
        ),
    )
    pd_stats = resolve_pass_defense_matchup_league_stats(
        bundle.pbp_3yr_prior, target_season, pd_placeholder,
    )
    print(f"  real Pass Defense Matchup league stats: {pd_stats}")

    rd_placeholder = RunDefenseMatchupConstants(
        decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
        weights={"epa_rush": c[94], "run_success": c[95], "ypc": c[96],
                 "explosive_run": c[97], "stuff_rate": c[98]},
        score_baseline=c[37], points_per_sd=c[38],
        league_avg=dict.fromkeys(
            ["epa_rush", "run_success", "ypc", "explosive_run", "stuff_rate"], 0.0,
        ),
        league_std=dict.fromkeys(
            ["epa_rush", "run_success", "ypc", "explosive_run", "stuff_rate"], 1.0,
        ),
    )
    rd_stats = resolve_run_defense_matchup_league_stats(
        bundle.pbp_3yr_prior, target_season, rd_placeholder,
    )
    print(f"  real Run Defense Matchup league stats: {rd_stats}")

    qbe_placeholder = QBEnvironmentModelConstants(
        decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
        league_avg=dict.fromkeys(["success", "explosive", "sack"], 0.0),
        league_std=dict.fromkeys(["success", "explosive", "sack"], 1.0),
        success_weight=c[128], explosive_weight=c[129], epa_weight=c[34],
        cpoe_weight=c[35], anya_weight=c[36], score_baseline=c[37], points_per_sd=c[38],
        new_team_penalty=c[130], recently_injured_penalty=c[131],
    )
    qbe_stats = resolve_qb_environment_model_league_stats(
        bundle.pbp_3yr_prior, target_season, qbe_placeholder,
    )
    print(f"  real QB Environment Model league stats: {qbe_stats}")

    ep_placeholder = ExplosivePlayMatchupConstants(
        decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
        league_avg_pass_off=0.0, league_std_pass_off=1.0,
        league_avg_run_off=0.0, league_std_run_off=1.0,
        league_avg_deep_pass_allowed=0.0, league_std_deep_pass_allowed=1.0,
        league_avg_yac_allowed=0.0, league_std_yac_allowed=1.0,
        pass_prevention_w_explosive_pass_allowed=c[136],
        pass_prevention_w_deep_pass_allowed=c[137], pass_prevention_w_yac_allowed=c[138],
    )
    ep_stats = resolve_explosive_play_matchup_league_stats(
        bundle.pbp_3yr_prior, target_season, pd_placeholder, rd_placeholder, ep_placeholder,
    )
    print(f"  real Explosive Play Matchup league stats: {ep_stats}")

    return ol_stats, prg_stats, pd_stats, rd_stats, qbe_stats, ep_stats


def _resolve_week_level_stats(
    bundle: HistoricalGameDataBundle, target_season: int, target_week: int, c: dict,
):
    """Real league stats for the 2 tabs with a real current-season blend -- genuinely depend
    on the real target week, so these alone are recomputed per week."""
    qb_placeholder = QBIndexConstants(
        decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
        blend_base=c[12], blend_per_game=c[13], blend_cap=c[14],
        weights={"epa": c[34], "cpoe": c[35], "anya": c[36]}, score_baseline=c[37],
        points_per_sd=c[38],
        league_avg=dict.fromkeys(["epa", "cpoe", "anya"], 0.0),
        league_std=dict.fromkeys(["epa", "cpoe", "anya"], 1.0),
    )
    qb_stats = resolve_qb_index_league_stats(
        bundle.pbp_3yr_prior, bundle.pbp_current_season, bundle.sched_current_season,
        target_season, target_week, qb_placeholder,
    )

    rb_placeholder = RBIndexConstants(
        decay_factor=c[20], regression_weight=c[21], last_year_emphasis=c[22],
        blend_base=c[12], blend_per_game=c[13], blend_cap=c[14],
        weights={"rushing_epa": c[44], "rushing_sr": c[45], "ypc": c[46], "ryoe": c[82],
                 "rz_share": c[124]},
        score_baseline=c[37], points_per_sd=c[38],
        league_avg=dict.fromkeys(["rushing_epa", "rushing_sr", "ypc", "ryoe", "rz_share"], 0.0),
        league_std=dict.fromkeys(["rushing_epa", "rushing_sr", "ypc", "ryoe", "rz_share"], 1.0),
    )
    rb_stats = resolve_rb_index_league_stats(
        bundle.pbp_3yr_prior, bundle.pbp_current_season, bundle.ngs_rushing_3yr_prior,
        bundle.ngs_rushing_current, bundle.sched_current_season, target_season, target_week,
        rb_placeholder,
    )
    return qb_stats, rb_stats


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

    print("Resolving real season-level league stats (once, reused every target week)...")
    ol_stats, prg_stats, pd_stats, rd_stats, qbe_stats, ep_stats = _resolve_season_level_stats(
        bundle, season, c,
    )

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

        print("  Resolving real week-dependent league stats (QB Index, RB Index)...")
        qb_stats, rb_stats = _resolve_week_level_stats(bundle, season, week, c)
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
