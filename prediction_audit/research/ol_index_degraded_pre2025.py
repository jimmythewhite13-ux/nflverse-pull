"""
Phase 8 secondary check (2024) -- a real, narrowly-scoped, documented workaround for OL Index's
FTN-coverage constraint (`offensive_line_index_historical.FTN_MIN_SEASON = 2022`, verified live:
`nfl_data_py.import_ftn_data` raises before 2022), which blocks any full 22-input reconstruction
for target seasons before 2025 (Y-3 falls before 2022).

This module does NOT touch, patch, or change behavior for target_season >= 2025 (production).
It exists only so `phase8_2024_reconstruction.py` can produce a second real season's worth of
data to check whether Phase 10's HFA-A/Travel-G ranking holds up -- explicitly NOT usable as
Phase 11's untouched holdout (it evaluates a different-fidelity formula, not the literal
selected production model).

Real justification this is safe, not a shortcut: tracing every real caller of OL Index confirmed
that across the ENTIRE 22-input composer, OL Index's real output is consumed in exactly one
place -- `ol_pressure_adj_historical.resolve_ol_pressure_diff()` -- and that function reads only
`ol_result.z_scores["pass_protection"]`. It never reads `run_blocking`, `sack_free_rate`, or the
overall composite `.score`/`.weighted_zsum`. `pass_protection` and `run_blocking` are both
sourced from PFR (`nfl_data_py.import_seasonal_pfr`), real and available from 2021 -- no FTN
data is actually needed to compute the one real z-score this project's formula ever reads.
`sack_free_rate` is therefore given an inert real placeholder (0.0 throughout) purely so the
existing, unmodified `_metric_dict_for_team_season`/`_league_baseline_for_season`/
`compute_ol_index` functions (which expect all 3 METRIC_KEYS) run unchanged -- its resulting
z-score and weight contribution are computed but never read by anything downstream, confirmed
by the trace above, not assumed.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.oline_stats import compute_team_season_oline_stats
from prediction_audit.engine.offensive_line_index import OLTeamHistory
from prediction_audit.historical.offensive_line_index_historical import (
    _league_baseline_for_season,
    _metric_dict_for_team_season,
)

_INERT_SACK_FREE_RATE_COLUMN = "Sack-Free Rate (Fault-Adjusted)"
_INERT_PLACEHOLDER = 0.0  # never read downstream -- see module docstring


def _build_degraded_team_table(
    pfr_pass_3yr: pd.DataFrame, pfr_rush_3yr: pd.DataFrame,
) -> pd.DataFrame:
    """Real Pass_Protection/Run_Blocking (PFR, 2021+) plus an inert placeholder Sack-Free Rate
    column, so the existing, unmodified real lookup helpers run without a KeyError."""
    real_oline = compute_team_season_oline_stats(pfr_pass_3yr, pfr_rush_3yr)
    real_oline = real_oline.copy()
    real_oline[_INERT_SACK_FREE_RATE_COLUMN] = _INERT_PLACEHOLDER
    return real_oline


def resolve_ol_index_history_degraded(
    pfr_pass_3yr: pd.DataFrame, pfr_rush_3yr: pd.DataFrame, target_season: int, team: str,
) -> OLTeamHistory:
    """Degraded stand-in for `resolve_ol_index_history()` -- skips the FTN coverage check
    entirely (no FTN data touched at all), real Pass_Protection/Run_Blocking, inert placeholder
    Sack-Free Rate. Still raises (never fabricates) if the team lacks real PFR coverage in any
    of the 3 real prior seasons."""
    team_table = _build_degraded_team_table(pfr_pass_3yr, pfr_rush_3yr)
    y1 = _metric_dict_for_team_season(team_table, team, target_season - 1)
    y2 = _metric_dict_for_team_season(team_table, team, target_season - 2)
    y3 = _metric_dict_for_team_season(team_table, team, target_season - 3)
    missing = [label for label, v in (("Y-1", y1), ("Y-2", y2), ("Y-3", y3)) if v is None]
    if missing:
        raise ValueError(
            f"No real full-coverage PFR OL data found for {team!r} in {missing} (degraded "
            f"2024 path -- never fabricated)."
        )
    league_baseline_y1 = _league_baseline_for_season(team_table, target_season - 1)
    return OLTeamHistory(
        team=team, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
        games_played=0, current_season=dict.fromkeys(y1.keys(), 0.0),
    )


def resolve_ol_index_league_stats_degraded(
    pfr_pass_3yr: pd.DataFrame, pfr_rush_3yr: pd.DataFrame, target_season: int, constants,
) -> dict[str, dict[str, float]]:
    """Degraded stand-in for `resolve_ol_index_league_stats()` -- same skip, real
    Pass_Protection/Run_Blocking league avg/std, inert placeholder Sack-Free Rate stats."""
    team_table = _build_degraded_team_table(pfr_pass_3yr, pfr_rush_3yr)
    all_teams = sorted(team_table["Team"].dropna().unique())

    from prediction_audit.engine.offensive_line_index import compute_ol_index

    blended_values: dict[str, list[float]] = {
        "pass_protection": [], "run_blocking": [], "sack_free_rate": [],
    }
    for team in all_teams:
        try:
            history = resolve_ol_index_history_degraded(
                pfr_pass_3yr, pfr_rush_3yr, target_season, team,
            )
        except ValueError:
            continue
        result = compute_ol_index(history, constants)
        for key in blended_values:
            blended_values[key].append(result.blended[key])

    stats = {}
    for key, values_list in blended_values.items():
        values = pd.Series(values_list)
        if values.empty:
            raise ValueError(
                f"No real qualifying teams resolved league-wide for metric {key!r} as of "
                f"season {target_season} (degraded 2024 path -- never fabricated)."
            )
        stats[key] = {"avg": float(values.mean()), "std": float(values.std(ddof=0))}
    # Real, expected degenerate case: every team's inert `sack_free_rate` placeholder blends to
    # the identical value 0.0 (by construction -- see module docstring), so its real std is
    # exactly 0.0, which would divide-by-zero in `z_score()` downstream even though that
    # z-score is never read (only z_scores["pass_protection"] is consumed anywhere in this
    # composer -- confirmed by the same real trace). Overridden to an inert nonzero std purely
    # to avoid the crash, not to make the number meaningful.
    if stats["sack_free_rate"]["std"] == 0.0:
        stats["sack_free_rate"]["std"] = 1.0
    return stats
