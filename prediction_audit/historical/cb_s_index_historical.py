"""
Step 6: resolves a real historical CB-S Index for one specific real player (given by
player_id), using only real data available before a target season -- third defensive
player-level index, following EDGE-IDL Index's exact pattern (no current-season blend step,
same real 4-source data assembly via nflverse_pull.defense_stats). Raw counts come from
`compute_player_season_secondary_stats` (real INT/PBU), the player-level twin of the
team-level function Secondary Index already uses.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.defense_stats import (
    compute_player_season_defensive_rates,
    compute_player_season_defensive_snaps,
    compute_player_season_secondary_stats,
)
from prediction_audit.engine.cb_s_index import (
    METRIC_KEYS,
    CBSIndexResult,
    CBSPlayerHistory,
    compute_cb_s_index,
)
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)

_RAW_COUNT_COLS = ["INT", "PBU"]
_METRIC_COLUMN = {"int_rate": "INT Rate", "pbu_rate": "PBU Rate"}


def build_real_rate_table(
    pbp: pd.DataFrame, snap_counts: pd.DataFrame, player_ids: pd.DataFrame,
    rosters: pd.DataFrame,
) -> pd.DataFrame:
    """Real per-player-season CB-S rate table, same real join chain as EDGE-IDL/LB Index."""
    raw_counts = compute_player_season_secondary_stats(
        normalize_relocated_abbreviations(pbp, columns=PBP_TEAM_COLUMNS)
    )
    snaps = compute_player_season_defensive_snaps(snap_counts, player_ids)
    return compute_player_season_defensive_rates(raw_counts, _RAW_COUNT_COLS, snaps, rosters)


def _metric_dict_for_player_season(
    rate_table: pd.DataFrame, player_id: str, season: int,
) -> dict[str, float] | None:
    match = rate_table[
        (rate_table["Player ID"] == player_id) & (rate_table["Season"] == season)
    ]
    if match.empty:
        return None
    row = match.iloc[0]
    return {key: float(row[col]) for key, col in _METRIC_COLUMN.items()}


def _league_baseline_for_season(rate_table: pd.DataFrame, season: int) -> dict[str, float]:
    year_stats = rate_table[rate_table["Season"] == season]
    if year_stats.empty:
        raise ValueError(f"No real qualifying CB-S player-seasons for season {season} -- "
                          f"cannot resolve a real league baseline (never fabricated).")
    return {key: float(year_stats[col].mean()) for key, col in _METRIC_COLUMN.items()}


def resolve_cb_s_history(
    rate_table_3yr_prior: pd.DataFrame, target_season: int, player_id: str,
) -> CBSPlayerHistory:
    y1 = _metric_dict_for_player_season(rate_table_3yr_prior, player_id, target_season - 1)
    y2 = _metric_dict_for_player_season(rate_table_3yr_prior, player_id, target_season - 2)
    y3 = _metric_dict_for_player_season(rate_table_3yr_prior, player_id, target_season - 3)
    missing = [label for label, v in (("Y-1", y1), ("Y-2", y2), ("Y-3", y3)) if v is None]
    if missing:
        raise ValueError(
            f"Real player {player_id!r} has no real qualifying (200+ snap) season in "
            f"{missing} -- never fabricated here."
        )

    league_baseline_y1 = _league_baseline_for_season(rate_table_3yr_prior, target_season - 1)
    return CBSPlayerHistory(
        player_id=player_id, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
    )


def resolve_cb_s_league_stats(
    rate_table_3yr_prior: pd.DataFrame, target_season: int, constants_without_league_stats,
) -> dict[str, dict[str, float]]:
    year1_ids = set(
        rate_table_3yr_prior[rate_table_3yr_prior["Season"] == target_season - 1]["Player ID"]
    )

    proj_baselines: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for player_id in year1_ids:
        try:
            history = resolve_cb_s_history(rate_table_3yr_prior, target_season, player_id)
        except ValueError:
            continue
        result: CBSIndexResult = compute_cb_s_index(history, constants_without_league_stats)
        for key in METRIC_KEYS:
            proj_baselines[key].append(result.proj_baseline[key])

    stats = {}
    for key in METRIC_KEYS:
        values = pd.Series(proj_baselines[key])
        if values.empty:
            raise ValueError(
                f"No real qualifying players resolved league-wide for metric {key!r} in "
                f"season {target_season} (never fabricated)."
            )
        stats[key] = {"avg": float(values.mean()), "std": float(values.std(ddof=0))}
    return stats
