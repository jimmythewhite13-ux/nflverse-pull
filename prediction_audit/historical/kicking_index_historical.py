"""
Step 6: resolves a real historical Kicking Index for one real team's K1, using only real data
available before a target game's own kickoff -- the third player-level index made walk-forward
capable, and the simplest yet: a single real role per team (no Starter/Backup binary -- QB/RB's
own real "what if I bench the starter" question has no equivalent for a position with no
second roster kicker to swap in, per build_kicking_index.py's own docstring), and a real
league baseline over ALL qualifying rows (no Role filter needed at all, unlike QB/RB).

Reuses nflverse_pull.kicking_stats's own already-real, already-parameterized
`compute_team_season_kicking_stats` -- built for the live 2026 pipeline but takes pbp for any
real years, so it works unchanged for a historical target.

Real historical K1 resolution: no pre-existing `compute_kicker_roles`-style helper exists in
this project (unlike QB/RB's own real dropback/carry-ranking convention) -- this module
defines its own, applying the exact same real volume-ranking spirit (most real FG Attempts-
so-far this season = K1) to the target season's own real attempts before the target week.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.kicking_stats import compute_team_season_kicking_stats
from prediction_audit.engine.kicking_index import (
    METRIC_KEYS,
    KickerHistory,
    compute_kicking_index,
)
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)
from prediction_audit.historical.team_ppg import team_season_ppg

_METRIC_COLUMN = {"fg_pct_oe": "FG% Over Expected", "fg_pct": "FG%", "xp_pct": "XP%"}


def resolve_k1_as_of_week(pbp_current_season: pd.DataFrame, through_week: int) -> pd.DataFrame:
    """Real Team -> K1 Player ID as of `through_week` (weeks strictly before it only): the
    kicker with the most real FG Attempts-so-far for that team."""
    reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG") & (pbp_current_season["week"] < through_week)
    ]
    season_stats = compute_team_season_kicking_stats(reg)
    if season_stats.empty:
        return season_stats
    idx = season_stats.groupby("Team")["FG Attempts"].idxmax()
    return season_stats.loc[idx]


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
    """Real league average per metric for one real season -- ALL qualifying kickers, no Role
    filter (matches Kicking Index's own real Section 2 convention)."""
    year_stats = season_stats[season_stats["Season"] == season]
    if year_stats.empty:
        raise ValueError(f"No real kicker season stats for season {season} -- cannot resolve "
                          f"a real league baseline (never fabricated).")
    return {key: float(year_stats[col].mean()) for key, col in _METRIC_COLUMN.items()}


def _resolve_history_for_player(
    player_id: str, team: str, prior_stats: pd.DataFrame, current_stats: pd.DataFrame,
    sched_games: pd.DataFrame, target_season: int, league_baseline_y1: dict[str, float],
) -> KickerHistory | None:
    y1 = _metric_dict_for_player_season(prior_stats, player_id, target_season - 1)
    y2 = _metric_dict_for_player_season(prior_stats, player_id, target_season - 2)
    y3 = _metric_dict_for_player_season(prior_stats, player_id, target_season - 3)
    if y1 is None or y2 is None or y3 is None:
        return None

    current = _metric_dict_for_player_season(current_stats, player_id, target_season)
    if current is None:
        current = dict.fromkeys(METRIC_KEYS, 0.0)

    team_row = sched_games[sched_games["Team"] == team]
    games_played = int(team_row.iloc[0]["Games Played"]) if not team_row.empty else 0

    return KickerHistory(
        player_id=player_id, y1=y1, y2=y2, y3=y3,
        league_baseline_y1=league_baseline_y1, games_played=games_played,
        current_season=current,
    )


def resolve_kicking_index_history(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame,
    sched: pd.DataFrame, target_season: int, target_week: int, team: str,
) -> KickerHistory:
    """Raises ValueError (never fabricates) if `team` has no real qualifying K1 as of
    target_week, or if a real Y1/Y2/Y3/league-baseline value can't be resolved."""
    prior_stats = compute_team_season_kicking_stats(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    )
    k1_table = resolve_k1_as_of_week(pbp_current_season, target_week)

    match = k1_table[k1_table["Team"] == team] if not k1_table.empty else k1_table
    if match.empty:
        raise ValueError(
            f"No real K1 found for {team!r} as of season {target_season} week "
            f"{target_week} (never fabricated)."
        )
    player_id = match.iloc[0]["Player ID"]

    league_baseline_y1 = _league_baseline_for_season(prior_stats, target_season - 1)
    current_reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG")
        & (pbp_current_season["week"] < target_week)
    ]
    current_stats = compute_team_season_kicking_stats(current_reg)
    team_games = team_season_ppg(sched, season=target_season, through_week=target_week)

    history = _resolve_history_for_player(
        player_id, team, prior_stats, current_stats, team_games, target_season,
        league_baseline_y1,
    )
    if history is None:
        raise ValueError(
            f"Real player {player_id!r} ({team} K1) has no real qualifying season in "
            f"Y-1/Y-2/Y-3 -- rookie/partial-history substitution is real, separate future "
            f"work (never fabricated here)."
        )
    return history


def resolve_kicking_index_league_stats(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame,
    sched: pd.DataFrame, target_season: int, target_week: int,
    constants_without_league_stats,
) -> dict[str, dict[str, float]]:
    """Real Section 4: league-wide average/std-dev of the real BLENDED metric value, across
    every real K1 league-wide as of target_week."""
    prior_stats = compute_team_season_kicking_stats(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    )
    k1_table = resolve_k1_as_of_week(pbp_current_season, target_week)

    league_baseline_y1 = _league_baseline_for_season(prior_stats, target_season - 1)
    current_reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG")
        & (pbp_current_season["week"] < target_week)
    ]
    current_stats = compute_team_season_kicking_stats(current_reg)
    team_games = team_season_ppg(sched, season=target_season, through_week=target_week)

    blended_values: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for _, row in k1_table.iterrows():
        history = _resolve_history_for_player(
            row["Player ID"], row["Team"], prior_stats, current_stats, team_games,
            target_season, league_baseline_y1,
        )
        if history is None:
            continue
        result = compute_kicking_index(history, constants_without_league_stats)
        for key in METRIC_KEYS:
            blended_values[key].append(result.blended[key])

    stats = {}
    for key in METRIC_KEYS:
        values = pd.Series(blended_values[key])
        if values.empty:
            raise ValueError(
                f"No real qualifying K1s resolved league-wide for metric {key!r} as of "
                f"season {target_season} week {target_week} (never fabricated)."
            )
        stats[key] = {"avg": float(values.mean()), "std": float(values.std(ddof=0))}
    return stats
