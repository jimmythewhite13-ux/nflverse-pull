"""
Step 13: reruns the real weeks 10-18, 2025 backtest using `demo_full_game_prediction.py`'s own
representative Model Assumptions constants (not the real, workbook-extracted ones
`backtest_step7_multiweek.py`/`persist_step7_backtest.py` already use) -- for a real, fair,
apples-to-apples comparison of the two real constant sets on the SAME real games, both
including real Travel Effect/Direction (unlike the very first representative-constants run
this session, which predates that fix and only covered week 10 alone).

No per-week/per-season league-stats resolution needed here (unlike the real-constants
pipeline) -- `build_demo_constants()`'s own real league_avg/league_std values are hardcoded
representative constants, not resolved per target season, so one real data fetch covers every
target week with no re-resolution cost.

Usage:
    uv run python prediction_audit/backtest_step7_representative_multiweek.py [season] [start] [end]
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
from prediction_audit.historical.demo_full_game_prediction import (  # noqa: E402
    build_demo_constants,
)
from prediction_audit.historical.full_game_prediction import (  # noqa: E402
    HistoricalGameDataBundle,
    resolve_historical_model_home_away_score,
)
from prediction_audit.market_data import fetch_real_market_lines  # noqa: E402


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
    constants = build_demo_constants()

    all_rows = []
    for week in range(start_week, end_week + 1):
        print(f"\n=== Real target week {week} ===")
        week_games = sched_current[
            (sched_current["season"] == season) & (sched_current["week"] == week)
            & (sched_current["game_type"] == "REG")
        ].sort_values("game_id")
        if week_games.empty:
            continue

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
        print(f"  Week {week}: {len(all_rows)} real games processed so far.")

    if not all_rows:
        print("\nNo real games resolved -- nothing to summarize.")
        return

    df = pd.DataFrame(all_rows)
    with_actual = df.dropna(subset=["real_actual_margin"])
    mae = (with_actual["predicted_margin"] - with_actual["real_actual_margin"]).abs().mean()
    winner_correct = (
        (with_actual["predicted_margin"] > 0) == (with_actual["real_actual_margin"] > 0)
    ).mean()
    print("\n" + "=" * 78)
    print(f"REAL REPRESENTATIVE-CONSTANTS RESULT: MAE={mae:.3f}pts  "
          f"winner-pick={winner_correct:.1%}  (n={len(with_actual)})")
    with_line = df.dropna(subset=["real_closing_spread"])
    if not with_line.empty:
        agrees = (
            (with_line["predicted_margin"] > 0) == (with_line["real_closing_spread"] > 0)
        ).mean()
        print(f"Real closing-line agreement: {agrees:.1%} (n={len(with_line)})")
    print("=" * 78)


if __name__ == "__main__":
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    start_week = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    end_week = int(sys.argv[3]) if len(sys.argv) > 3 else 18
    main(season, start_week, end_week)
