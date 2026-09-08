"""
Step 6: resolves a real historical Secondary Index for one real team, using only real data
available before a target game's own kickoff -- team-level (same real pattern as Front Seven
Index), so no player role resolution is needed. nflverse_pull's own real
`compute_team_season_secondary_stats()` is already a full-season TEAM rate stat.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.defense_stats import compute_team_season_secondary_stats
from prediction_audit.engine.secondary_index import (
    METRIC_KEYS,
    SecondaryIndexResult,
    SecondaryTeamHistory,
    compute_secondary_index,
)
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)
from prediction_audit.historical.team_ppg import team_season_ppg

_METRIC_COLUMN = {"int_rate": "INT Rate", "pbu_rate": "PBU Rate"}


def _metric_dict_for_team_season(
    team_stats: pd.DataFrame, team: str, season: int,
) -> dict[str, float] | None:
    match = team_stats[(team_stats["Team"] == team) & (team_stats["Season"] == season)]
    if match.empty:
        return None
    row = match.iloc[0]
    return {key: float(row[col]) for key, col in _METRIC_COLUMN.items()}


def _league_baseline_for_season(team_stats: pd.DataFrame, season: int) -> dict[str, float]:
    year_stats = team_stats[team_stats["Season"] == season]
    if year_stats.empty:
        raise ValueError(f"No real Secondary team stats for season {season} -- cannot "
                          f"resolve a real league baseline (never fabricated).")
    return {key: float(year_stats[col].mean()) for key, col in _METRIC_COLUMN.items()}


def resolve_secondary_index_history(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame,
    sched: pd.DataFrame, target_season: int, target_week: int, team: str,
) -> SecondaryTeamHistory:
    """Raises ValueError (never fabricates) if `team` has no real qualifying data in any of
    the 3 real prior seasons."""
    prior_stats = compute_team_season_secondary_stats(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    )
    y1 = _metric_dict_for_team_season(prior_stats, team, target_season - 1)
    y2 = _metric_dict_for_team_season(prior_stats, team, target_season - 2)
    y3 = _metric_dict_for_team_season(prior_stats, team, target_season - 3)
    missing = [label for label, v in (("Y-1", y1), ("Y-2", y2), ("Y-3", y3)) if v is None]
    if missing:
        raise ValueError(
            f"No real Secondary data found for {team!r} in {missing} -- cannot resolve "
            f"real historical Secondary Index (never fabricated)."
        )

    league_baseline_y1 = _league_baseline_for_season(prior_stats, target_season - 1)

    current_reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG")
        & (pbp_current_season["week"] < target_week)
    ]
    current_stats = compute_team_season_secondary_stats(current_reg)
    current_metrics = _metric_dict_for_team_season(current_stats, team, target_season)
    if current_metrics is None:
        current_metrics = dict.fromkeys(METRIC_KEYS, 0.0)

    team_games = team_season_ppg(sched, season=target_season, through_week=target_week)
    team_row = team_games[team_games["Team"] == team]
    games_played = int(team_row.iloc[0]["Games Played"]) if not team_row.empty else 0

    return SecondaryTeamHistory(
        team=team, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
        games_played=games_played, current_season=current_metrics,
    )


def resolve_secondary_index_league_stats(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame,
    sched: pd.DataFrame, target_season: int, target_week: int,
    constants_without_league_stats,
) -> dict[str, dict[str, float]]:
    """Real Section 4: league-wide average/std-dev of the real BLENDED metric value, across
    every real team as of target_week."""
    prior_stats = compute_team_season_secondary_stats(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    )
    all_teams = sorted(prior_stats["Team"].unique())

    blended_values: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for team in all_teams:
        try:
            history = resolve_secondary_index_history(
                pbp_3yr_prior, pbp_current_season, sched, target_season, target_week, team,
            )
        except ValueError:
            continue
        result: SecondaryIndexResult = compute_secondary_index(
            history, constants_without_league_stats,
        )
        for key in METRIC_KEYS:
            blended_values[key].append(result.blended[key])

    stats = {}
    for key in METRIC_KEYS:
        values = pd.Series(blended_values[key])
        if values.empty:
            raise ValueError(
                f"No real qualifying teams resolved league-wide for metric {key!r} as of "
                f"season {target_season} week {target_week} (never fabricated)."
            )
        stats[key] = {"avg": float(values.mean()), "std": float(values.std(ddof=0))}
    return stats
