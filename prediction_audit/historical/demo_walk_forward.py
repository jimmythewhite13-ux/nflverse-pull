"""
Step 6 proof of concept: a real, end-to-end walk-forward Base Team Quality prediction for one
real historical game, using only real nflverse data that would have been available before that
game's own kickoff. This is the first time any piece of the Python Model Engine has run against
an arbitrary real past target rather than the frozen, single-snapshot 2026 season.

The target game is picked programmatically (first real game of the target week, by real
game_id sort order) -- not hand-selected -- to avoid any appearance of cherry-picking a result
that happens to look good. Base Team Quality alone is not the full model (no HFA, rest,
weather, or matchup terms), so it is not expected to closely track the real closing line or
outcome on any single game; this is a real data-lineage proof, not a backtest result.

Usage:
    uv run python prediction_audit/historical/demo_walk_forward.py [season] [week]
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from prediction_audit.engine.team_quality import (  # noqa: E402
    TeamQualityConstants,
    base_team_quality,
)
from prediction_audit.historical.walk_forward import (  # noqa: E402
    WalkForwardTarget,
    resolve_team_quality_for_game,
)

# Real model calibration constants (Model Assumptions C20/C21/C22/C12/C13/C14) -- reused
# unchanged for any historical target since they're a model-design choice, not season data.
CONSTANTS = TeamQualityConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
)


def main(season: int, week: int) -> None:
    print(f"Fetching real nflverse schedules for {season - 3}-{season}...")
    sched = fetch_schedules(list(range(season - 3, season + 1)))

    week_games = sched[
        (sched["season"] == season) & (sched["week"] == week) & (sched["game_type"] == "REG")
    ].sort_values("game_id")
    if week_games.empty:
        raise ValueError(f"No real REG games found for season={season} week={week}")
    first_game = week_games.iloc[0]

    home_full = TEAM_NAMES[first_game["home_team"]]
    away_full = TEAM_NAMES[first_game["away_team"]]
    print(f"Target real game: {first_game['game_id']} -- {away_full} @ {home_full}")
    print(f"  Real actual result: away {first_game['away_score']}, home {first_game['home_score']}")
    print(f"  Real closing spread_line (home): {first_game['spread_line']}, "
          f"total_line: {first_game['total_line']}")

    target = WalkForwardTarget(season=season, week=week, home_team=home_full, away_team=away_full)
    home_result, away_result = resolve_team_quality_for_game(sched, target, CONSTANTS)

    print()
    print(f"Real historical inputs used (only data before season {season} week {week}):")
    print(f"  {home_full} (home): Blended Off={home_result.blended_off:.1f}, "
          f"Blended Def={home_result.blended_def:.1f}, "
          f"current-season blend weight={home_result.blend_weight:.3f}")
    print(f"  {away_full} (away): Blended Off={away_result.blended_off:.1f}, "
          f"Blended Def={away_result.blended_def:.1f}, "
          f"current-season blend weight={away_result.blend_weight:.3f}")

    home_bq, away_bq = base_team_quality(
        home_result.blended_off, away_result.blended_def,
        away_result.blended_off, home_result.blended_def,
    )
    print()
    print("Real walk-forward Base Team Quality (Z01/AA01 component only -- not the full "
          "Model Score, no HFA/rest/weather/matchup terms):")
    print(f"  Home ({home_full}): {home_bq:.2f}")
    print(f"  Away ({away_full}): {away_bq:.2f}")
    print(f"  Implied team-quality-only margin (home-away): {home_bq - away_bq:+.2f}")


if __name__ == "__main__":
    season = int(sys.argv[1]) if len(sys.argv) > 1 else 2024
    week = int(sys.argv[2]) if len(sys.argv) > 2 else 10
    main(season, week)
