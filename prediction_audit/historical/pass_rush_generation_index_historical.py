"""
Step 6: resolves a real historical Pass Rush Generation Index for one real team, using only
real data available before a target game's own kickoff -- third matchup tab. Team-level, no
current-season blend, no player role resolution.

Merges two real already-parameterized nflverse_pull.defense_stats functions: Sack Rate and
Pressure Proxy (QB Hit Rate) both come from `compute_team_season_front7_stats` (the SAME
real team-level function Front Seven Index already uses); Blitz Rate comes from
`compute_team_season_participation_context` (real nflverse participation data,
number_of_pass_rushers >= 5).
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.defense_stats import (
    compute_team_season_front7_stats,
    compute_team_season_participation_context,
)
from prediction_audit.engine.pass_rush_generation_index import (
    METRIC_KEYS,
    PassRushGenerationResult,
    PassRushGenerationTeamHistory,
    compute_pass_rush_generation_index,
)
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)

_METRIC_COLUMN = {
    "sack_rate": "Sack Rate", "pressure_proxy": "QB Hit Rate", "blitz_rate": "Blitz Rate",
}


def build_real_team_table(pbp: pd.DataFrame) -> pd.DataFrame:
    """Real merged per-team-season Pass Rush Generation metric table."""
    front7 = compute_team_season_front7_stats(pbp)
    participation = compute_team_season_participation_context(pbp)
    return front7.merge(
        participation[["Team", "Season", "Blitz Rate"]], on=["Team", "Season"], how="left",
    )


def _metric_dict_for_team_season(
    team_table: pd.DataFrame, team: str, season: int,
) -> dict[str, float] | None:
    match = team_table[(team_table["Team"] == team) & (team_table["Season"] == season)]
    if match.empty:
        return None
    row = match.iloc[0]
    if any(pd.isna(row[col]) for col in _METRIC_COLUMN.values()):
        return None
    return {key: float(row[col]) for key, col in _METRIC_COLUMN.items()}


def _league_baseline_for_season(team_table: pd.DataFrame, season: int) -> dict[str, float]:
    year_stats = team_table[
        (team_table["Season"] == season)
        & team_table[list(_METRIC_COLUMN.values())].notna().all(axis=1)
    ]
    if year_stats.empty:
        raise ValueError(f"No real Pass Rush Generation team stats with full real metric "
                          f"coverage for season {season} -- cannot resolve a real league "
                          f"baseline (never fabricated).")
    return {key: float(year_stats[col].mean()) for key, col in _METRIC_COLUMN.items()}


def resolve_pass_rush_generation_history(
    pbp_3yr_prior: pd.DataFrame, target_season: int, team: str,
) -> PassRushGenerationTeamHistory:
    """Raises ValueError (never fabricates) if `team` has no real qualifying data in any of
    the 3 real prior seasons, or if a real league baseline can't be resolved."""
    prior_table = build_real_team_table(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    )
    y1 = _metric_dict_for_team_season(prior_table, team, target_season - 1)
    y2 = _metric_dict_for_team_season(prior_table, team, target_season - 2)
    y3 = _metric_dict_for_team_season(prior_table, team, target_season - 3)
    missing = [label for label, v in (("Y-1", y1), ("Y-2", y2), ("Y-3", y3)) if v is None]
    if missing:
        raise ValueError(
            f"No real Pass Rush Generation data found for {team!r} in {missing} -- cannot "
            f"resolve real historical Pass Rush Generation Index (never fabricated)."
        )

    league_baseline_y1 = _league_baseline_for_season(prior_table, target_season - 1)
    return PassRushGenerationTeamHistory(
        team=team, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
    )


def resolve_pass_rush_generation_league_stats(
    pbp_3yr_prior: pd.DataFrame, target_season: int, constants_without_league_stats,
) -> dict[str, dict[str, float]]:
    """Real league-wide average/std-dev of the real Projected Baseline (no blend step exists
    for this tab), across every real team with full real metric coverage."""
    prior_table = build_real_team_table(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    )
    all_teams = sorted(prior_table["Team"].dropna().unique())

    proj_baselines: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for team in all_teams:
        try:
            history = resolve_pass_rush_generation_history(pbp_3yr_prior, target_season, team)
        except ValueError:
            continue
        result: PassRushGenerationResult = compute_pass_rush_generation_index(
            history, constants_without_league_stats,
        )
        for key in METRIC_KEYS:
            proj_baselines[key].append(result.proj_baseline[key])

    stats = {}
    for key in METRIC_KEYS:
        values = pd.Series(proj_baselines[key])
        if values.empty:
            raise ValueError(
                f"No real qualifying teams resolved league-wide for metric {key!r} in "
                f"season {target_season} (never fabricated)."
            )
        stats[key] = {"avg": float(values.mean()), "std": float(values.std(ddof=0))}
    return stats
