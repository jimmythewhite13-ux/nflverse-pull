"""
Step 6: resolves a real historical LB Index for one specific real player (given by player_id),
using only real data available before a target season -- second defensive player-level index,
following EDGE-IDL Index's exact pattern (no current-season blend step, same real 4-source
data assembly via nflverse_pull.defense_stats).

Only real difference from EDGE-IDL Index: raw counts come from TWO real functions merged
together -- `compute_player_season_tackle_stats` (real Tackles) and
`compute_player_season_front7_stats` (real TFL, reused -- the same function EDGE-IDL Index
uses for its own Sacks/TFL/QB-Hits, just taking only the TFL column here).
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.defense_stats import (
    compute_player_season_defensive_rates,
    compute_player_season_defensive_snaps,
    compute_player_season_front7_stats,
    compute_player_season_tackle_stats,
)
from prediction_audit.engine.lb_index import (
    METRIC_KEYS,
    LBIndexResult,
    LBPlayerHistory,
    compute_lb_index,
)
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)

_RAW_COUNT_COLS = ["Tackles", "TFL"]
_METRIC_COLUMN = {"tackle_rate": "Tackles Rate", "tfl_rate": "TFL Rate"}


def build_real_rate_table(
    pbp: pd.DataFrame, snap_counts: pd.DataFrame, player_ids: pd.DataFrame,
    rosters: pd.DataFrame,
) -> pd.DataFrame:
    """Real per-player-season LB rate table, merging Tackles + TFL raw counts before the
    shared real snap-rate conversion."""
    normalized = normalize_relocated_abbreviations(pbp, columns=PBP_TEAM_COLUMNS)
    tackles = compute_player_season_tackle_stats(normalized)
    tfl = compute_player_season_front7_stats(normalized)[["Player ID", "Season", "Team", "TFL"]]
    # Outer merge -- a real player-season with credits in only one of the two source
    # functions still needs a real Team value, so both sides' Team columns are kept (suffixed)
    # and coalesced rather than assuming the left side (tackles) always has it.
    raw_counts = tackles.merge(
        tfl, on=["Player ID", "Season"], how="outer", suffixes=("", "_tfl"),
    )
    raw_counts["Team"] = raw_counts["Team"].fillna(raw_counts["Team_tfl"])
    raw_counts = raw_counts.drop(columns=["Team_tfl"])
    raw_counts["Tackles"] = raw_counts["Tackles"].fillna(0.0)
    raw_counts["TFL"] = raw_counts["TFL"].fillna(0.0)

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
        raise ValueError(f"No real qualifying LB player-seasons for season {season} -- "
                          f"cannot resolve a real league baseline (never fabricated).")
    return {key: float(year_stats[col].mean()) for key, col in _METRIC_COLUMN.items()}


def resolve_lb_history(
    rate_table_3yr_prior: pd.DataFrame, target_season: int, player_id: str,
) -> LBPlayerHistory:
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
    return LBPlayerHistory(
        player_id=player_id, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
    )


def resolve_lb_league_stats(
    rate_table_3yr_prior: pd.DataFrame, target_season: int, constants_without_league_stats,
) -> dict[str, dict[str, float]]:
    year1_ids = set(
        rate_table_3yr_prior[rate_table_3yr_prior["Season"] == target_season - 1]["Player ID"]
    )

    proj_baselines: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for player_id in year1_ids:
        try:
            history = resolve_lb_history(rate_table_3yr_prior, target_season, player_id)
        except ValueError:
            continue
        result: LBIndexResult = compute_lb_index(history, constants_without_league_stats)
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
