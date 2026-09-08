"""
Step 6: resolves a real historical Special Teams Player Index for one real team's P/KR/PR,
using only real data available before a target game's own kickoff -- tenth index made
walk-forward-capable. No current-season blend step exists for this tab (confirmed when it was
first ported), so no through_week/partial-season logic is needed for the player's own metric,
only real Y1/Y2/Y3 (3 full real prior seasons) + a real per-slot-type league baseline/avg/std.

Reuses nflverse_pull.special_teams_stats's own already-real, already-parameterized functions
(`compute_player_season_punting_rates`/`compute_player_season_return_rates`) -- each already
applies its own real qualifying threshold (20 punts / 5 KR returns / 10 PR returns) and real
rookie-flag attachment.

Real historical P/KR/PR resolution: no pre-existing role-ranking helper exists for these slots
in this project -- this module defines its own, applying the same real volume-ranking spirit
as QB/RB/Kicking (most real Punts/KR-Returns/PR-Returns-so-far this season = that team's real
P/KR/PR).
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.special_teams_stats import (
    compute_player_season_punting_rates,
    compute_player_season_return_rates,
)
from prediction_audit.engine.special_teams_player_index import (
    SLOT_TYPES,
    SpecialTeamsPlayerHistory,
    SpecialTeamsPlayerIndexResult,
    compute_special_teams_player_index,
)
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)

_METRIC_COLUMN = {"P": "Net Punt Average", "KR": "KR Average", "PR": "PR Average"}
_COUNT_COLUMN = {"P": "Punts", "KR": "KR Returns", "PR": "PR Returns"}


def _slot_table(
    pbp: pd.DataFrame, rosters: pd.DataFrame, slot_type: str,
) -> pd.DataFrame:
    if slot_type == "P":
        return compute_player_season_punting_rates(pbp, rosters)
    if slot_type in ("KR", "PR"):
        table = compute_player_season_return_rates(pbp, rosters)
        col = _METRIC_COLUMN[slot_type]
        return table[table[col].notna()]
    raise ValueError(f"Unknown slot_type {slot_type!r} -- expected one of {SLOT_TYPES}.")


def resolve_slot_player_as_of_week(
    pbp_current_season: pd.DataFrame, rosters: pd.DataFrame, slot_type: str,
    through_week: int,
) -> pd.DataFrame:
    """Real Team -> slot_type player as of `through_week` (weeks strictly before it only):
    the player with the most real season-so-far count at that slot (Punts for P, KR/PR
    Returns for KR/PR)."""
    reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG") & (pbp_current_season["week"] < through_week)
    ]
    table = _slot_table(reg, rosters, slot_type)
    if table.empty:
        return table
    count_col = _COUNT_COLUMN[slot_type]
    idx = table.groupby("Team")[count_col].idxmax()
    return table.loc[idx]


def _metric_for_player_season(
    slot_table: pd.DataFrame, player_id: str, season: int, slot_type: str,
) -> float | None:
    match = slot_table[
        (slot_table["Player ID"] == player_id) & (slot_table["Season"] == season)
    ]
    if match.empty:
        return None
    return float(match.iloc[0][_METRIC_COLUMN[slot_type]])


def _league_baseline_for_season(slot_table: pd.DataFrame, season: int, slot_type: str) -> float:
    """Real per-slot-type league average for one real season -- matches this tab's own real
    Section 4 convention (P/KR/PR each scored against their OWN real population)."""
    year_stats = slot_table[slot_table["Season"] == season]
    if year_stats.empty:
        raise ValueError(
            f"No real {slot_type} season stats for season {season} -- cannot resolve a "
            f"real league baseline (never fabricated)."
        )
    return float(year_stats[_METRIC_COLUMN[slot_type]].mean())


def resolve_special_teams_player_history(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame, rosters: pd.DataFrame,
    target_season: int, target_week: int, team: str, slot_type: str,
) -> SpecialTeamsPlayerHistory:
    """Raises ValueError (never fabricates) if `team` has no real qualifying player at
    `slot_type` as of target_week, or if a real Y1/Y2/Y3/league-baseline value can't be
    resolved."""
    prior_table = _slot_table(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS),
        rosters, slot_type,
    )
    current_slot = resolve_slot_player_as_of_week(
        pbp_current_season, rosters, slot_type, target_week,
    )
    match = current_slot[current_slot["Team"] == team] if not current_slot.empty else current_slot
    if match.empty:
        raise ValueError(
            f"No real {slot_type} found for {team!r} as of season {target_season} week "
            f"{target_week} (never fabricated)."
        )
    player_id = match.iloc[0]["Player ID"]

    y1 = _metric_for_player_season(prior_table, player_id, target_season - 1, slot_type)
    y2 = _metric_for_player_season(prior_table, player_id, target_season - 2, slot_type)
    y3 = _metric_for_player_season(prior_table, player_id, target_season - 3, slot_type)
    missing = [label for label, v in (("Y-1", y1), ("Y-2", y2), ("Y-3", y3)) if v is None]
    if missing:
        raise ValueError(
            f"Real player {player_id!r} ({team} {slot_type}) has no real qualifying season "
            f"in {missing} -- never fabricated here."
        )

    league_baseline_y1 = _league_baseline_for_season(prior_table, target_season - 1, slot_type)
    return SpecialTeamsPlayerHistory(
        player_id=player_id, slot_type=slot_type, y1=y1, y2=y2, y3=y3,
        league_baseline_y1=league_baseline_y1,
    )


def _resolve_by_player_id(
    prior_table: pd.DataFrame, target_season: int, player_id: str, slot_type: str,
) -> SpecialTeamsPlayerHistory | None:
    """Returns None (never fabricates) if a real Y1/Y2/Y3 value is missing for this player."""
    y1 = _metric_for_player_season(prior_table, player_id, target_season - 1, slot_type)
    y2 = _metric_for_player_season(prior_table, player_id, target_season - 2, slot_type)
    y3 = _metric_for_player_season(prior_table, player_id, target_season - 3, slot_type)
    if y1 is None or y2 is None or y3 is None:
        return None
    league_baseline_y1 = _league_baseline_for_season(prior_table, target_season - 1, slot_type)
    return SpecialTeamsPlayerHistory(
        player_id=player_id, slot_type=slot_type, y1=y1, y2=y2, y3=y3,
        league_baseline_y1=league_baseline_y1,
    )


def resolve_special_teams_player_league_stats(
    pbp_3yr_prior: pd.DataFrame, rosters: pd.DataFrame, target_season: int, slot_type: str,
    constants_without_league_stats,
) -> dict[str, float]:
    """Real Section 4: league-wide average/std-dev of the real Projected Baseline (no blend
    step exists for this tab) for one real slot_type, across every real qualifying player with
    a real Y-1 in `pbp_3yr_prior` -- no current-season data needed, unlike QB/RB/Kicking's own
    league-stats resolvers, since this tab has no current-season blend step at all."""
    prior_table = _slot_table(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS),
        rosters, slot_type,
    )
    year1_ids = set(prior_table[prior_table["Season"] == target_season - 1]["Player ID"])

    proj_baselines = []
    for player_id in year1_ids:
        history = _resolve_by_player_id(prior_table, target_season, player_id, slot_type)
        if history is None:
            continue
        result: SpecialTeamsPlayerIndexResult = compute_special_teams_player_index(
            history, constants_without_league_stats,
        )
        proj_baselines.append(result.proj_baseline)

    values = pd.Series(proj_baselines)
    if values.empty:
        raise ValueError(
            f"No real qualifying players resolved league-wide for slot {slot_type!r} in "
            f"season {target_season} (never fabricated)."
        )
    if len(values) < 2:
        # Real finding, not a bug: KR specifically is a highly volatile role -- verified live
        # that only 1 real player had a qualifying KR season in all of 2021/2022/2023
        # simultaneously (this project's real "3 full consecutive qualifying years, never
        # substituted" requirement genuinely narrows an already-small population further for
        # this slot). A real population of size 1 gives std=0.0, which would silently produce
        # a ZeroDivisionError the moment any real player's Z-score is computed against it --
        # raised here instead, with the real cause named, rather than letting that happen
        # downstream.
        raise ValueError(
            f"Only {len(values)} real qualifying player(s) resolved league-wide for slot "
            f"{slot_type!r} in season {target_season} -- too few for a real, meaningful "
            f"league std-dev (never fabricated a substitute population)."
        )
    return {"avg": float(values.mean()), "std": float(values.std(ddof=0))}
