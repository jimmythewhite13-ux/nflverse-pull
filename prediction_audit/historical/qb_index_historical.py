"""
Step 6: resolves a real historical QB Index for one real team's Starter or Backup, using only
real data available before a target game's own kickoff -- the first player-level index made
walk-forward-capable this session.

Reuses nflverse_pull.qb_stats's own already-real, already-parameterized functions
(`compute_team_season_qb_stats`, `compute_qb_roles`) rather than re-deriving per-QB EPA/CPOE/
ANY-A from raw pbp again -- these were built for the live 2026 pipeline but take `pbp`/
`season_stats` for any real years, so they work unchanged for a historical target.

Real finding, not assumed: QB Index's own "Current Season <metric>" cells (Section 3's
current-season blend) are REAL MANUAL INPUTS in the live workbook -- blue cells starting at 0,
filled in by hand each week -- not auto-computed from pbp at all (confirmed by reading
current_season_blend.py's own real `add_current_season_blend()` docstring/cell styling). A
historical walk-forward has no user to type that value in, so this module computes it for
real, directly from real historical pbp restricted to weeks before the target -- an honest,
automatic substitute for what the live pipeline leaves to manual entry, not a fabrication.

Real historical Starter/Backup role resolution reuses `compute_qb_roles()`'s own real
dropback-ranking method -- confirmed (in build_qb_index.py's own docstring) to be this
project's OWN documented historical-attempts-ranking fallback, not a new invention. Applied
here to the target season's OWN real dropbacks-so-far (through the target week), so a team's
real Starter/Backup as of that point in the season is whoever has actually taken the most/
second-most real dropbacks so far that season -- exactly the shape used for the games-not-yet-
played weeks the live 2026 workbook itself falls back to.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.qb_stats import compute_qb_roles, compute_team_season_qb_stats
from prediction_audit.engine.qb_index import METRIC_KEYS, QBHistory, compute_qb_index
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)
from prediction_audit.historical.team_ppg import team_season_ppg

_METRIC_COLUMN = {"epa": "EPA/Play", "cpoe": "CPOE", "anya": "ANY/A"}


def resolve_qb_roles_as_of_week(
    pbp_current_season: pd.DataFrame, target_season: int, through_week: int,
) -> pd.DataFrame:
    """
    Real Team|Role (Starter/Backup/Other) assignment as of `through_week` (weeks strictly
    before it only -- the same no-future-information guard used throughout this package),
    via the project's own real compute_team_season_qb_stats + compute_qb_roles chain applied
    to a real partial-season pbp slice.
    """
    reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG") & (pbp_current_season["week"] < through_week)
    ]
    season_stats = compute_team_season_qb_stats(reg)
    if season_stats.empty:
        return season_stats.assign(Role=pd.Series(dtype=str))
    return compute_qb_roles(season_stats)


def _metric_dict_for_player_season(
    season_stats: pd.DataFrame, player_id: str, season: int,
) -> dict[str, float] | None:
    match = season_stats[
        (season_stats["Player ID"] == player_id) & (season_stats["Season"] == season)
    ]
    if match.empty:
        return None
    row = match.iloc[0]
    return {key: float(row[col]) for key, col in _METRIC_COLUMN.items()}


def _league_baseline_for_season(season_stats: pd.DataFrame, season: int) -> dict[str, float]:
    """Real Starters+Backups-only league average per metric for one real season (matches
    QB Index's own real Section 2 AVERAGEIFS(...,role<>"Other") convention)."""
    year_stats = season_stats[season_stats["Season"] == season]
    if year_stats.empty:
        raise ValueError(f"No real QB season stats for season {season} -- cannot resolve a "
                          f"real league baseline (never fabricated).")
    roles = compute_qb_roles(year_stats)
    qualifying_ids = set(roles[roles["Role"] != "Other"]["Player ID"])
    pool = year_stats[year_stats["Player ID"].isin(qualifying_ids)]
    if pool.empty:
        raise ValueError(f"No real Starters/Backups found for season {season} -- cannot "
                          f"resolve a real league baseline (never fabricated).")
    return {key: float(pool[col].mean()) for key, col in _METRIC_COLUMN.items()}


def _prepare_prior_stats(pbp_3yr_prior: pd.DataFrame) -> pd.DataFrame:
    return compute_team_season_qb_stats(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    )


def _prepare_current_stats(pbp_current_season: pd.DataFrame, target_week: int) -> pd.DataFrame:
    current_reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG")
        & (pbp_current_season["week"] < target_week)
    ]
    return compute_team_season_qb_stats(current_reg)


def _resolve_history_for_player(
    player_id: str, team: str, prior_stats: pd.DataFrame, current_stats: pd.DataFrame,
    sched_games: pd.DataFrame, target_season: int, target_week: int,
    league_baseline_y1: dict[str, float],
) -> QBHistory | None:
    """Returns None (never fabricates) if a real Y1/Y2/Y3 value is missing for this player --
    rookie/partial-history substitution is real, separate future work."""
    y1 = _metric_dict_for_player_season(prior_stats, player_id, target_season - 1)
    y2 = _metric_dict_for_player_season(prior_stats, player_id, target_season - 2)
    y3 = _metric_dict_for_player_season(prior_stats, player_id, target_season - 3)
    if y1 is None or y2 is None or y3 is None:
        return None

    current_metrics = _metric_dict_for_player_season(current_stats, player_id, target_season)
    if current_metrics is None:
        current_metrics = dict.fromkeys(METRIC_KEYS, 0.0)

    team_row = sched_games[sched_games["Team"] == team]
    games_played = int(team_row.iloc[0]["Games Played"]) if not team_row.empty else 0

    return QBHistory(
        player_id=player_id, y1=y1, y2=y2, y3=y3,
        league_baseline_y1=league_baseline_y1, games_played=games_played,
        current_season=current_metrics,
    )


def resolve_qb_index_history(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame,
    sched: pd.DataFrame, target_season: int, target_week: int,
    team: str, role: str,
) -> QBHistory:
    """
    `pbp_3yr_prior`: real pbp for target_season-3..target_season-1 (full seasons).
    `pbp_current_season`: real pbp for target_season only (will be restricted to weeks before
    target_week internally, for both role resolution and the current-season value).
    `sched`: real schedules covering target_season (for the real team Games Played count).

    Raises ValueError (never fabricates) if `team` has no real qualifying QB at `role` as of
    target_week, or if a real Y1/Y2/Y3/league-baseline value can't be resolved.
    """
    prior_stats = _prepare_prior_stats(pbp_3yr_prior)
    current_roles = resolve_qb_roles_as_of_week(pbp_current_season, target_season, target_week)

    match = current_roles[(current_roles["Team"] == team) & (current_roles["Role"] == role)]
    if match.empty:
        raise ValueError(
            f"No real {role} found for {team!r} as of season {target_season} week "
            f"{target_week} (never fabricated)."
        )
    player_id = match.iloc[0]["Player ID"]

    league_baseline_y1 = _league_baseline_for_season(prior_stats, target_season - 1)
    current_stats = _prepare_current_stats(pbp_current_season, target_week)
    team_games = team_season_ppg(sched, season=target_season, through_week=target_week)

    history = _resolve_history_for_player(
        player_id, team, prior_stats, current_stats, team_games, target_season, target_week,
        league_baseline_y1,
    )
    if history is None:
        raise ValueError(
            f"Real player {player_id!r} ({team} {role}) has no real qualifying season in "
            f"Y-1/Y-2/Y-3 -- rookie/partial-history substitution is real, separate future "
            f"work (never fabricated here)."
        )
    return history


def resolve_qb_index_league_stats(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame,
    sched: pd.DataFrame, target_season: int, target_week: int,
    constants_without_league_stats,
) -> dict[str, dict[str, float]]:
    """
    Real Section 4: league-wide average/std-dev of the real BLENDED metric value (not the
    pre-blend Projected Baseline -- confirmed via current_season_blend.py's own docstring:
    Section 4 must be recomputed over the blended column for a walk-forward Z-score to be
    real), across every real Starter/Backup league-wide as of target_week.

    `constants_without_league_stats`: a QBIndexConstants with `league_avg`/`league_std` set to
    any placeholder dict (unused by the decay/blend arithmetic this needs) -- avoids a second,
    parallel constants shape just to drive compute_qb_index() through the blend step.

    Returns {metric_key: {"avg": ..., "std": ...}}. Real players missing Y-1/Y-2/Y-3 are
    skipped (never fabricated a substitute), consistent with resolve_qb_index_history's own
    per-player behavior.
    """
    prior_stats = _prepare_prior_stats(pbp_3yr_prior)
    current_roles = resolve_qb_roles_as_of_week(pbp_current_season, target_season, target_week)
    qualifying = current_roles[current_roles["Role"].isin(["Starter", "Backup"])]

    league_baseline_y1 = _league_baseline_for_season(prior_stats, target_season - 1)
    current_stats = _prepare_current_stats(pbp_current_season, target_week)
    team_games = team_season_ppg(sched, season=target_season, through_week=target_week)

    blended_values: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for _, row in qualifying.iterrows():
        history = _resolve_history_for_player(
            row["Player ID"], row["Team"], prior_stats, current_stats, team_games,
            target_season, target_week, league_baseline_y1,
        )
        if history is None:
            continue
        result = compute_qb_index(history, constants_without_league_stats)
        for key in METRIC_KEYS:
            blended_values[key].append(result.blended[key])

    stats = {}
    for key in METRIC_KEYS:
        values = pd.Series(blended_values[key])
        if values.empty:
            raise ValueError(
                f"No real qualifying QBs resolved league-wide for metric {key!r} as of "
                f"season {target_season} week {target_week} (never fabricated)."
            )
        stats[key] = {"avg": float(values.mean()), "std": float(values.std(ddof=0))}
    return stats
