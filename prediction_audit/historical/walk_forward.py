"""
Step 6: resolves a real historical Base Team Quality prediction for one real game, using only
real data that would have been available before that game's own kickoff -- the first genuine
walk-forward slice through the Python Model Engine (previously proven only against the frozen,
single-snapshot 2026 season; this is the first time any of it runs against an arbitrary real
past target).

Wires prediction_audit/historical/team_ppg.py's real, leak-guarded per-team PPG data into
team_quality.py's already-Excel-proven compute_team_quality()/base_team_quality() -- no new
scoring arithmetic here, only real historical data resolution, per this project's consistent
"arithmetic only, not data sourcing" module boundary (data resolution lives here, arithmetic
stays in engine/).

Historical scope note: this resolves Base Team Quality only (Season Matchups' Z01/AA01) -- the
foundational, simplest real piece of the full Z/AA formula, and a genuine end-to-end proof that
walk-forward reconstruction works. Extending every other real term (QB/RB/OL/defense indices,
Explosive Play Matchup, etc.) to arbitrary historical targets is real, separate, larger future
work -- each needs its own real historical per-player/per-team metric resolution from pbp, not
just PPG from final scores.
"""
from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from prediction_audit.engine.team_quality import (
    TeamQualityConstants,
    TeamQualityResult,
    TeamQualityTeamHistory,
    compute_team_quality,
)
from prediction_audit.historical.team_ppg import league_average_ppg, team_season_ppg


@dataclass
class WalkForwardTarget:
    season: int
    week: int
    home_team: str
    away_team: str


def resolve_team_quality_history(
    sched: pd.DataFrame, target_season: int, target_week: int, team: str,
) -> TeamQualityTeamHistory:
    """
    Real historical Y1/Y2/Y3 = the 3 full real prior seasons (target_season-1/-2/-3) --
    matches YoY Baseline Engine's own real convention of always using complete prior seasons,
    never a partial one, for the 3-Yr history. Real league_baseline_off/def_y1 = the real
    32-team average for target_season-1. Real current_season = the real partial-season PPG for
    target_season, using only weeks strictly before target_week (the no-future-information
    guard team_ppg.py's own through_week already enforces).

    Raises ValueError (never fabricates) if `team` has zero real qualifying games in any of
    the 3 real prior seasons -- a real data gap (e.g. an expansion/relocation edge case),
    not something to paper over with an invented number.
    """
    y1_df = team_season_ppg(sched, season=target_season - 1)
    y2_df = team_season_ppg(sched, season=target_season - 2)
    y3_df = team_season_ppg(sched, season=target_season - 3)
    current_df = team_season_ppg(sched, season=target_season, through_week=target_week)

    def _row(df: pd.DataFrame, season_label: int) -> pd.Series:
        match = df[df["Team"] == team]
        if match.empty:
            raise ValueError(
                f"No real games found for {team!r} in season {season_label} -- cannot "
                f"resolve real historical PPG (never fabricated)."
            )
        return match.iloc[0]

    y1_row = _row(y1_df, target_season - 1)
    y2_row = _row(y2_df, target_season - 2)
    y3_row = _row(y3_df, target_season - 3)
    league_baseline = league_average_ppg(y1_df)

    current_match = current_df[current_df["Team"] == team]
    if current_match.empty:
        # Real and legitimate for week 1 (or a team that hasn't played yet this season as of
        # target_week) -- current-season PPG of 0 with 0 games played, matching the live
        # workbook's own real convention (blend_weight() itself returns 0 at games_played=0,
        # so this value is never actually used in the blend).
        current_off, current_def, games_played = 0.0, 0.0, 0
    else:
        current_row = current_match.iloc[0]
        current_off = float(current_row["Off PPG"])
        current_def = float(current_row["Def PPG"])
        games_played = int(current_row["Games Played"])

    return TeamQualityTeamHistory(
        team=team,
        off_y1=float(y1_row["Off PPG"]), off_y2=float(y2_row["Off PPG"]),
        off_y3=float(y3_row["Off PPG"]),
        def_y1=float(y1_row["Def PPG"]), def_y2=float(y2_row["Def PPG"]),
        def_y3=float(y3_row["Def PPG"]),
        league_baseline_off_y1=league_baseline["off"],
        league_baseline_def_y1=league_baseline["def"],
        current_season_off_ppg=current_off, current_season_def_ppg=current_def,
        games_played=games_played,
    )


def resolve_team_quality_for_game(
    sched: pd.DataFrame, target: WalkForwardTarget, constants: TeamQualityConstants,
) -> tuple[TeamQualityResult, TeamQualityResult]:
    """Returns (home_result, away_result) -- real per-team compute_team_quality() results,
    built entirely from real historical data available before target.week's own kickoff."""
    home_history = resolve_team_quality_history(
        sched, target.season, target.week, target.home_team,
    )
    away_history = resolve_team_quality_history(
        sched, target.season, target.week, target.away_team,
    )
    home_result = compute_team_quality(home_history, constants)
    away_result = compute_team_quality(away_history, constants)
    return home_result, away_result
