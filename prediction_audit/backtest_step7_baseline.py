"""
Step 7: a real, small-scale baseline backtest -- runs the Step 6 composer
(`resolve_historical_model_home_away_score`) against every real REG game in one real target
week, compares each real predicted margin against the real actual margin AND the real closing
line (from Step 5's own real habitatring.com ingestion), and reports real aggregate accuracy
metrics (MAE vs actual, ATS win rate vs the real closing line).

Real, honest scoping: this reuses `demo_full_game_prediction.py`'s own real, plausible
Model-Assumptions-style constants (documented there as representative values matching what
this session's own individual resolver verifications found sane, not freshly re-extracted from
a live Model Assumptions sheet) -- so treat this as a real, honest PRELIMINARY backtest proving
the real pipeline works end to end, not a final validated accuracy number. A production Step 7
run should source these constants from the real frozen v35 Model Assumptions sheet directly.

Real market lines come from `market_data.fetch_real_market_lines()` -- the SAME real, free,
verified source Step 5 already uses (habitatring.com via nfl_data_py), fetched fresh here for
the target season rather than read back from the audit database (which currently only holds
2026-season rows).

Usage:
    uv run python prediction_audit/backtest_step7_baseline.py [season] [week]
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
from prediction_audit.historical.demo_full_game_prediction import build_demo_constants  # noqa: E402
from prediction_audit.historical.full_game_prediction import (  # noqa: E402
    HistoricalGameDataBundle,
    resolve_historical_model_home_away_score,
)
from prediction_audit.market_data import fetch_real_market_lines  # noqa: E402


def main(season: int, week: int) -> None:
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

    week_games = sched_current[
        (sched_current["season"] == season) & (sched_current["week"] == week)
        & (sched_current["game_type"] == "REG")
    ].sort_values("game_id")

    rows = []
    for _, game in week_games.iterrows():
        home_abbr, away_abbr = game["home_team"], game["away_team"]
        home_team, away_team = TEAM_NAMES[home_abbr], TEAM_NAMES[away_abbr]
        try:
            home_score, away_score = resolve_historical_model_home_away_score(
                bundle, constants, season, week, home_team, home_abbr, away_team, away_abbr,
            )
        except ValueError as e:
            print(f"  SKIP {away_abbr}@{home_abbr}: {e}")
            continue

        predicted_margin = home_score - away_score
        real_actual_margin = None
        if pd.notna(game.get("home_score")) and pd.notna(game.get("away_score")):
            real_actual_margin = game["home_score"] - game["away_score"]

        real_closing_spread = None
        line = real_lines.get((week, away_team, home_team))
        if line is not None:
            real_closing_spread = line.spread_line  # real, positive = home favored

        rows.append({
            "game": f"{away_abbr}@{home_abbr}", "predicted_margin": predicted_margin,
            "real_actual_margin": real_actual_margin,
            "real_closing_spread": real_closing_spread,
        })

    if not rows:
        print("No real games resolved for this target -- nothing to backtest.")
        return

    df = pd.DataFrame(rows)
    print()
    print(df.to_string(index=False))

    with_actual = df.dropna(subset=["real_actual_margin"])
    if not with_actual.empty:
        mae = (with_actual["predicted_margin"] - with_actual["real_actual_margin"]).abs().mean()
        winner_correct = (
            (with_actual["predicted_margin"] > 0) == (with_actual["real_actual_margin"] > 0)
        ).mean()
        print(f"\nReal MAE vs actual margin: {mae:.2f} pts "
              f"(n={len(with_actual)} real completed games)")
        print(f"Real winner-pick accuracy: {winner_correct:.1%}")
    else:
        print("\nNo real completed games in this target week yet -- no MAE/winner-pick "
              "metrics (real future games have no real result to compare against).")

    with_line = df.dropna(subset=["real_closing_spread"])
    if not with_line.empty:
        # ATS: does the model's real predicted margin agree with which side the real closing
        # line favors, directionally? (A real, simple market-agreement check, not a real
        # graded ATS bet outcome, which needs the real final score too.)
        agrees = (
            (with_line["predicted_margin"] > 0) == (with_line["real_closing_spread"] > 0)
        ).mean()
        print(f"Real directional agreement with the real closing line: {agrees:.1%} "
              f"(n={len(with_line)} real games with a real closing line)")


if __name__ == "__main__":
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2025
    week = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    main(season, week)
