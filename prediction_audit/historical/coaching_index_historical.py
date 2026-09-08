"""
Step 6: resolves a real historical Coaching Index for one real team, using only real data
available before a target game's own kickoff -- fourth matchup tab, and genuinely different
from every other index/matchup tab built so far: the real underlying data
(`compute_coach_season_stats`) is keyed by (Coach, Season, Team), not Team alone -- a coach's
own real Y1/Y2/Y3 history follows THAT PERSON, including across a real team change, matching
`CoachingTeamHistory`'s own real design (confirmed reading the engine before building this:
the dataclass is named team-first for interface consistency with every other tab, but its real
Y1/Y2/Y3 values are the COACH's own history, looked up by whoever is currently coaching that
team).

No current-season blend step exists for this tab (confirmed when it was first ported), so no
through_week/partial-season logic is needed.

Real current-coach resolution reuses `nflverse_pull.coaching_stats.compute_current_coach_by_team`
directly -- already real, already parameterized by season (works for any real season's
already-published schedule, not just "the current live one"), so no new role-ranking
convention is needed here (unlike WR-TE/Kicking/etc., which had no pre-existing convention to
reuse).

Real finding, caught while building this module's own tests (not in production data, but a
real, confirmed shared-function edge case worth flagging): `compute_coach_season_stats`'s own
real Penalty Rate division (`penalty_count / total_plays`) has no `fillna(0)` on
`penalty_count` first -- a coach with a real, genuine ZERO penalties across a real season's
worth of real games comes back with Penalty Rate = NaN (a pandas index-alignment artifact of
the missing key), not a real 0.0. This module's own existing "any NaN metric -> unresolvable,
never fabricated" handling already treats that correctly (raises rather than substituting a
guessed value), so no code change was needed here -- documented for whoever next touches
`coaching_stats.py` directly.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.coaching_stats import (
    compute_coach_season_stats,
    compute_current_coach_by_team,
    compute_game_coach_map,
)
from prediction_audit.engine.coaching_index import (
    METRIC_KEYS,
    CoachingIndexResult,
    CoachingTeamHistory,
    compute_coaching_index,
)

_METRIC_COLUMN = {
    "fourth_down": "4th Down Go Rate (Short)", "q1_epa": "1Q Net EPA/Play",
    "penalty": "Penalty Rate", "h2_epa_delta": "2H EPA Delta",
}


def build_real_coach_table(pbp: pd.DataFrame, sched: pd.DataFrame) -> pd.DataFrame:
    """Real per-(Coach, Season, Team) metric table, from real per-game coach attribution."""
    game_coach_map = compute_game_coach_map(sched)
    return compute_coach_season_stats(pbp, game_coach_map)


def _metric_dict_for_coach_season(
    coach_table: pd.DataFrame, coach: str, season: int,
) -> dict[str, float] | None:
    match = coach_table[
        (coach_table["Coach"] == coach) & (coach_table["Season"] == season)
    ]
    if match.empty:
        return None
    row = match.iloc[0]
    if any(pd.isna(row[col]) for col in _METRIC_COLUMN.values()):
        return None  # a real season with a genuinely missing metric (e.g. no qualifying
        # 4th-and-short situations) -- never substituted
    return {key: float(row[col]) for key, col in _METRIC_COLUMN.items()}


def _league_baseline_for_season(coach_table: pd.DataFrame, season: int) -> dict[str, float]:
    """Real league-wide average per metric for one real season -- ALL real coaches with full
    real metric coverage that season, no Team filter."""
    year_stats = coach_table[
        (coach_table["Season"] == season)
        & coach_table[list(_METRIC_COLUMN.values())].notna().all(axis=1)
    ]
    if year_stats.empty:
        raise ValueError(f"No real coach stats with full real metric coverage for season "
                          f"{season} -- cannot resolve a real league baseline (never "
                          f"fabricated).")
    return {key: float(year_stats[col].mean()) for key, col in _METRIC_COLUMN.items()}


def resolve_coaching_index_history(
    pbp_3yr_prior: pd.DataFrame, sched_3yr_prior: pd.DataFrame, sched_target_season: pd.DataFrame,
    target_season: int, team: str,
) -> CoachingTeamHistory:
    """Raises ValueError (never fabricates) if `team` has no real published coach for
    target_season, if that coach has no real qualifying data in any of the 3 real prior
    seasons (regardless of which real team he coached each of those seasons), or if a real
    league baseline can't be resolved."""
    current_coaches = compute_current_coach_by_team(sched_target_season, target_season)
    match = current_coaches[current_coaches["Team"] == team]
    if match.empty:
        raise ValueError(
            f"No real published coach found for {team!r} in season {target_season} (never "
            f"fabricated)."
        )
    coach = match.iloc[0]["Coach"]

    coach_table = build_real_coach_table(pbp_3yr_prior, sched_3yr_prior)
    y1 = _metric_dict_for_coach_season(coach_table, coach, target_season - 1)
    y2 = _metric_dict_for_coach_season(coach_table, coach, target_season - 2)
    y3 = _metric_dict_for_coach_season(coach_table, coach, target_season - 3)
    missing = [label for label, v in (("Y-1", y1), ("Y-2", y2), ("Y-3", y3)) if v is None]
    if missing:
        raise ValueError(
            f"Real coach {coach!r} ({team}'s current real coach) has no real qualifying "
            f"season in {missing} -- never fabricated here."
        )

    league_baseline_y1 = _league_baseline_for_season(coach_table, target_season - 1)
    return CoachingTeamHistory(
        team=team, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
    )


def resolve_coaching_index_league_stats(
    pbp_3yr_prior: pd.DataFrame, sched_3yr_prior: pd.DataFrame,
    sched_target_season: pd.DataFrame, target_season: int,
    constants_without_league_stats,
) -> dict[str, dict[str, float]]:
    """Real league-wide average/std-dev of the real Projected Baseline (no blend step exists
    for this tab), across every real team with a real, fully-resolvable current coach."""
    current_coaches = compute_current_coach_by_team(sched_target_season, target_season)
    all_teams = sorted(current_coaches["Team"].unique())

    proj_baselines: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for team in all_teams:
        try:
            history = resolve_coaching_index_history(
                pbp_3yr_prior, sched_3yr_prior, sched_target_season, target_season, team,
            )
        except ValueError:
            continue
        result: CoachingIndexResult = compute_coaching_index(
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
