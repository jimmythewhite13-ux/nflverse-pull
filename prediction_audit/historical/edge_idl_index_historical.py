"""
Step 6: resolves a real historical EDGE-IDL Index for one specific real player (given by
player_id, not resolved via a role/starter lookup here -- see module docstring below for why),
using only real data available before a target season. The first defensive PLAYER-level index
made walk-forward-capable.

Genuinely simpler than QB/RB/Kicking in one real respect: EDGE-IDL Index has NO current-season
blend step at all (confirmed when this tab was first ported -- Section 4's own real title says
"League Average & Std. Dev. of the 3-Yr Baselines", Z-scores reference Projected Baseline
directly) -- so this module needs no `through_week` partial-season logic for the player's own
metrics, only real Y1/Y2/Y3 (3 full real prior seasons) + a real league baseline/avg/std.

Real data assembly needs 3 separate real sources joined together, via
nflverse_pull.defense_stats's own already-real, already-parameterized functions:
`compute_player_season_front7_stats` (real per-player Sacks/TFL/QB Hits from pbp),
`fetch_snap_counts`/`fetch_player_ids`/`compute_player_season_defensive_snaps` (real per-player
defensive snaps, PFR-sourced, cross-walked to this project's gsis_id), and
`compute_player_season_defensive_rates` (the shared real snap-rate conversion + real
200-snap qualifying threshold + real rookie-flag layer used identically by LB/CB-S Index too).

This module deliberately does NOT resolve "who is starting at EDGE/IDL for this team" --
unlike QB/RB/Kicking's single team-wide role, EDGE-IDL Index's real population is every real
player who could appear as Starter OR Backup at any of 4 real slots (current_roster.py's own
per-slot logic) -- a genuinely different, harder resolution problem than a single volume rank,
deliberately deferred. Given a specific real player_id (however sourced), this module resolves
their own real historical score.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.defense_stats import (
    compute_player_season_defensive_rates,
    compute_player_season_defensive_snaps,
    compute_player_season_front7_stats,
)
from prediction_audit.engine.edge_idl_index import (
    METRIC_KEYS,
    EdgeIdlIndexResult,
    EdgeIdlPlayerHistory,
    compute_edge_idl_index,
)
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)

_RAW_COUNT_COLS = ["Sacks", "TFL", "QB Hits"]
_METRIC_COLUMN = {
    "sack_rate": "Sacks Rate", "tfl_rate": "TFL Rate", "qb_hit_rate": "QB Hits Rate",
}


def build_real_rate_table(
    pbp: pd.DataFrame, snap_counts: pd.DataFrame, player_ids: pd.DataFrame,
    rosters: pd.DataFrame,
) -> pd.DataFrame:
    """Real per-player-season EDGE-IDL rate table, assembled from the 4 real underlying
    sources -- one real network-free join chain, reusable for any real years those inputs
    cover."""
    raw_counts = compute_player_season_front7_stats(
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
    """Real league-wide average per metric for one real season -- all real qualifying
    (200+ snap) player-seasons, no Role filter (matches this tab's own real Section 2)."""
    year_stats = rate_table[rate_table["Season"] == season]
    if year_stats.empty:
        raise ValueError(f"No real qualifying EDGE-IDL player-seasons for season {season} -- "
                          f"cannot resolve a real league baseline (never fabricated).")
    return {key: float(year_stats[col].mean()) for key, col in _METRIC_COLUMN.items()}


def resolve_edge_idl_history(
    rate_table_3yr_prior: pd.DataFrame, target_season: int, player_id: str,
) -> EdgeIdlPlayerHistory:
    """`rate_table_3yr_prior`: a real rate table (from build_real_rate_table) covering at
    least target_season-3..target_season-1. Raises ValueError (never fabricates) if
    `player_id` has no real qualifying season in any of Y-1/Y-2/Y-3."""
    y1 = _metric_dict_for_player_season(rate_table_3yr_prior, player_id, target_season - 1)
    y2 = _metric_dict_for_player_season(rate_table_3yr_prior, player_id, target_season - 2)
    y3 = _metric_dict_for_player_season(rate_table_3yr_prior, player_id, target_season - 3)
    missing = [label for label, v in (("Y-1", y1), ("Y-2", y2), ("Y-3", y3)) if v is None]
    if missing:
        raise ValueError(
            f"Real player {player_id!r} has no real qualifying (200+ snap) season in "
            f"{missing} -- rookie/partial-history substitution is real, separate future work "
            f"(never fabricated here)."
        )

    league_baseline_y1 = _league_baseline_for_season(rate_table_3yr_prior, target_season - 1)
    return EdgeIdlPlayerHistory(
        player_id=player_id, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
    )


def resolve_edge_idl_league_stats(
    rate_table_3yr_prior: pd.DataFrame, target_season: int, constants_without_league_stats,
) -> dict[str, dict[str, float]]:
    """Real Section 4: league-wide average/std-dev of the real Projected Baseline (no blend
    step exists for this tab, so this is the pre-blend proj_baseline itself, unlike QB/RB/
    Kicking's post-blend value), across every real qualifying player with a real Y-1/Y-2/Y-3."""
    year1_ids = set(
        rate_table_3yr_prior[rate_table_3yr_prior["Season"] == target_season - 1]["Player ID"]
    )

    proj_baselines: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for player_id in year1_ids:
        try:
            history = resolve_edge_idl_history(rate_table_3yr_prior, target_season, player_id)
        except ValueError:
            continue
        result: EdgeIdlIndexResult = compute_edge_idl_index(
            history, constants_without_league_stats,
        )
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
