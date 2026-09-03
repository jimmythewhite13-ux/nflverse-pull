"""
Step 6: resolves a real historical Team-Specific HFA for an arbitrary real target season,
using nflverse_pull's own already-tested compute_team_season_home_away_splits() (real per-team
home/away scoring margin, any real season) wired into team_specific_hfa.py's already-Excel-
proven compute_team_specific_hfa().

No current-season blend step exists for this tab (confirmed this session while porting it --
"no blend, single metric, no Z-scoring at all"), so unlike Base Team Quality this needs no
partial-season/`through_week` logic at all: Y1/Y2/Y3 are always the 3 full real prior seasons,
identical in shape to how the live 2026 pipeline itself always uses them.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import compute_team_season_home_away_splits
from prediction_audit.engine.team_specific_hfa import (
    TeamSpecificHFAConstants,
    TeamSpecificHFAHistory,
    TeamSpecificHFAResult,
    compute_team_specific_hfa,
)
from prediction_audit.historical.relocations import normalize_relocated_abbreviations


def resolve_team_specific_hfa_history(
    sched: pd.DataFrame, target_season: int, team: str,
) -> TeamSpecificHFAHistory:
    """
    Real Y1/Y2/Y3 = raw HFA (Home Margin - Away Margin) for the 3 full real prior seasons.
    Real league_baseline_y1 = the real 32-team average raw HFA for target_season-1 (Section 2's
    own real AVERAGEIF-across-32-teams logic). Raises ValueError (never fabricates) if `team`
    has no real qualifying home/away split in any of the 3 real prior seasons.
    """
    normalized = normalize_relocated_abbreviations(sched)
    splits = compute_team_season_home_away_splits(normalized)
    splits = splits.copy()
    splits["HFA"] = splits["Home Margin"] - splits["Away Margin"]

    def _hfa_for(season: int) -> pd.DataFrame:
        return splits[splits["Season"] == season]

    def _row(season: int) -> float:
        year_df = _hfa_for(season)
        match = year_df[year_df["Team"] == team]
        if match.empty or pd.isna(match.iloc[0]["HFA"]):
            raise ValueError(
                f"No real home/away split found for {team!r} in season {season} -- cannot "
                f"resolve real historical HFA (never fabricated)."
            )
        return float(match.iloc[0]["HFA"])

    y1 = _row(target_season - 1)
    y2 = _row(target_season - 2)
    y3 = _row(target_season - 3)

    y1_df = _hfa_for(target_season - 1)
    if y1_df["HFA"].isna().all():
        raise ValueError(
            f"No real league-wide HFA data for season {target_season - 1} -- cannot resolve "
            f"a real league baseline (never fabricated)."
        )
    league_baseline_y1 = float(y1_df["HFA"].mean())

    return TeamSpecificHFAHistory(
        team=team, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
    )


def resolve_team_specific_hfa_for_game(
    sched: pd.DataFrame, target_season: int, home_team: str,
    constants: TeamSpecificHFAConstants,
) -> TeamSpecificHFAResult:
    """Returns the real home team's own walk-forward Team-Specific HFA result (this tab is
    home-team-specific only -- the away team's own HFA doesn't apply to a game it's not
    hosting, matching the live workbook's own real convention)."""
    history = resolve_team_specific_hfa_history(sched, target_season, home_team)
    return compute_team_specific_hfa(history, constants)
