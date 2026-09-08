"""
Step 6: resolves a real historical Offensive Line Index for one real team, using only real
data available before a target game's own kickoff -- eleventh and final index made
walk-forward-capable. Team-level (like Base Team Quality/Front Seven/Secondary), so no player
role resolution is needed.

Real, documented coverage constraint (found live before building this, not assumed): 2 of the
3 real metrics (Pass_Protection, Run_Blocking) need PFR data via `nfl_data_py.import_seasonal_pfr`,
which covers 2021+ fine. The third (Sack-Free Rate, Fault-Adjusted) needs real FTN charting
data via `nfl_data_py.import_ftn_data`, which **raises "Data not available before 2022"** --
verified live. This means a walk-forward target whose Y-3 falls before 2022 (i.e. target
seasons before 2025) cannot resolve all 3 real metrics -- both resolve functions raise a
clear, real error naming this constraint rather than silently dropping the third metric or
substituting a fabricated value.

Real current-season blend deliberately NOT applied: PFR's own real `import_seasonal_pfr` has
no real week-level granularity (full-season aggregates only), so there is no real mid-season
PFR slice to blend the way pbp-derived tabs use a real `through_week` filter -- resolving that
is real, separate future work. `games_played` is always 0 here (not sourced from the real
schedule, even though that data exists) specifically so `blend_weight()` returns 0 and the
real Y-1/Y-2/Y-3 baseline passes through unmodified -- pairing a real nonzero games_played
with a placeholder current_season would silently bias the blended value toward 0, a real
correctness bug this design avoids rather than risks.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.oline_stats import (
    compute_team_season_oline_stats,
    compute_team_season_sack_fault_stats,
)
from prediction_audit.engine.offensive_line_index import (
    METRIC_KEYS,
    OLIndexResult,
    OLTeamHistory,
    compute_ol_index,
)

_METRIC_COLUMN = {
    "pass_protection": "Pass_Protection", "run_blocking": "Run_Blocking",
    "sack_free_rate": "Sack-Free Rate (Fault-Adjusted)",
}

FTN_MIN_SEASON = 2022  # verified live: nfl_data_py.import_ftn_data raises before this


def _check_ftn_coverage(target_season: int) -> None:
    if target_season - 3 < FTN_MIN_SEASON:
        raise ValueError(
            f"Real walk-forward target season {target_season} needs Y-3={target_season - 3}, "
            f"but real FTN charting data (needed for Sack-Free Rate) is not available before "
            f"{FTN_MIN_SEASON} -- cannot resolve all 3 real OL Index metrics for this target "
            f"(never fabricated a substitute)."
        )


def build_real_team_table(
    pfr_pass: pd.DataFrame, pfr_rush: pd.DataFrame, pbp: pd.DataFrame, ftn: pd.DataFrame,
) -> pd.DataFrame:
    """Real merged per-team-season OL metric table, from the 2 real underlying source pairs."""
    oline = compute_team_season_oline_stats(pfr_pass, pfr_rush)
    sack_fault = compute_team_season_sack_fault_stats(pbp, ftn)
    return oline.merge(sack_fault, on=["Team", "Season"], how="outer")


def _metric_dict_for_team_season(
    team_table: pd.DataFrame, team: str, season: int,
) -> dict[str, float] | None:
    match = team_table[(team_table["Team"] == team) & (team_table["Season"] == season)]
    if match.empty:
        return None
    row = match.iloc[0]
    if any(pd.isna(row[col]) for col in _METRIC_COLUMN.values()):
        return None  # a real season with only partial metric coverage -- never substituted
    return {key: float(row[col]) for key, col in _METRIC_COLUMN.items()}


def _league_baseline_for_season(team_table: pd.DataFrame, season: int) -> dict[str, float]:
    year_stats = team_table[
        (team_table["Season"] == season)
        & team_table[list(_METRIC_COLUMN.values())].notna().all(axis=1)
    ]
    if year_stats.empty:
        raise ValueError(f"No real OL team stats with full real metric coverage for season "
                          f"{season} -- cannot resolve a real league baseline (never "
                          f"fabricated).")
    return {key: float(year_stats[col].mean()) for key, col in _METRIC_COLUMN.items()}


def resolve_ol_index_history(
    pfr_pass_3yr: pd.DataFrame, pfr_rush_3yr: pd.DataFrame, pbp_3yr_prior: pd.DataFrame,
    ftn_3yr_prior: pd.DataFrame, target_season: int, team: str,
) -> OLTeamHistory:
    """Raises ValueError (never fabricates) if target_season-3 < FTN_MIN_SEASON (a real,
    documented data-coverage constraint), if `team` has no real qualifying data in any of the
    3 real prior seasons, or if a real league baseline can't be resolved."""
    _check_ftn_coverage(target_season)

    prior_table = build_real_team_table(pfr_pass_3yr, pfr_rush_3yr, pbp_3yr_prior, ftn_3yr_prior)
    y1 = _metric_dict_for_team_season(prior_table, team, target_season - 1)
    y2 = _metric_dict_for_team_season(prior_table, team, target_season - 2)
    y3 = _metric_dict_for_team_season(prior_table, team, target_season - 3)
    missing = [label for label, v in (("Y-1", y1), ("Y-2", y2), ("Y-3", y3)) if v is None]
    if missing:
        raise ValueError(
            f"No real full-coverage OL data found for {team!r} in {missing} -- cannot "
            f"resolve real historical OL Index (never fabricated)."
        )

    league_baseline_y1 = _league_baseline_for_season(prior_table, target_season - 1)

    return OLTeamHistory(
        team=team, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
        games_played=0, current_season=dict.fromkeys(METRIC_KEYS, 0.0),
    )


def resolve_ol_index_league_stats(
    pfr_pass_3yr: pd.DataFrame, pfr_rush_3yr: pd.DataFrame, pbp_3yr_prior: pd.DataFrame,
    ftn_3yr_prior: pd.DataFrame, target_season: int, constants_without_league_stats,
) -> dict[str, dict[str, float]]:
    """Real Section 4: league-wide average/std-dev of the real BLENDED metric value (which,
    per this module's own no-current-season-blend design, equals the real pre-blend Projected
    Baseline), across every real team with full real metric coverage."""
    _check_ftn_coverage(target_season)

    prior_table = build_real_team_table(pfr_pass_3yr, pfr_rush_3yr, pbp_3yr_prior, ftn_3yr_prior)
    all_teams = sorted(prior_table["Team"].dropna().unique())

    blended_values: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for team in all_teams:
        try:
            history = resolve_ol_index_history(
                pfr_pass_3yr, pfr_rush_3yr, pbp_3yr_prior, ftn_3yr_prior, target_season, team,
            )
        except ValueError:
            continue
        result: OLIndexResult = compute_ol_index(history, constants_without_league_stats)
        for key in METRIC_KEYS:
            blended_values[key].append(result.blended[key])

    stats = {}
    for key in METRIC_KEYS:
        values = pd.Series(blended_values[key])
        if values.empty:
            raise ValueError(
                f"No real qualifying teams resolved league-wide for metric {key!r} as of "
                f"season {target_season} (never fabricated)."
            )
        stats[key] = {"avg": float(values.mean()), "std": float(values.std(ddof=0))}
    return stats
