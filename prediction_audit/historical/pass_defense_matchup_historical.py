"""
Step 6: resolves a real historical Pass Defense Matchup for one real team, using only real
data available before a target game's own kickoff. Team-level, no current-season blend
(confirmed when this tab was first ported), so no player role resolution or through_week logic
is needed -- just real Y1/Y2/Y3 (3 full real prior seasons) + a real league baseline/avg/std.
Metric inversion (all 5 real metrics are "Allowed" rates, lower-is-better) is handled inside
`compute_pass_defense_matchup()` itself -- this module feeds real, non-inverted raw values.

Merges two real already-parameterized `nflverse_pull.efficiency` functions:
`compute_team_season_matchup_metrics` (4 of the 5 real metrics) and
`compute_team_season_efficiency` (real NY/A Allowed).
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.efficiency import (
    compute_team_season_efficiency,
    compute_team_season_matchup_metrics,
)
from prediction_audit.engine.pass_defense_matchup import (
    METRIC_KEYS,
    PassDefenseMatchupResult,
    PassDefenseTeamHistory,
    compute_pass_defense_matchup,
)
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)

_METRIC_COLUMN = {
    "epa_dropback": "EPA/Dropback Allowed (Def)", "pass_success": "Pass Success Rate Allowed (Def)",
    "completion_pct": "Completion % Allowed (Def)", "nya": "NY/A Allowed (Def)",
    "explosive_pass": "Explosive Pass Rate Allowed (Def)",
}


def build_real_team_table(pbp: pd.DataFrame) -> pd.DataFrame:
    """Real merged per-team-season Pass Defense Matchup metric table."""
    matchup = compute_team_season_matchup_metrics(pbp)
    efficiency = compute_team_season_efficiency(pbp)
    return matchup.merge(
        efficiency[["Team", "Season", "NY/A Allowed (Def)"]], on=["Team", "Season"], how="left",
    )


def _metric_dict_for_team_season(
    team_table: pd.DataFrame, team: str, season: int,
) -> dict[str, float] | None:
    match = team_table[(team_table["Team"] == team) & (team_table["Season"] == season)]
    if match.empty:
        return None
    row = match.iloc[0]
    if any(pd.isna(row[col]) for col in _METRIC_COLUMN.values()):
        return None
    return {key: float(row[col]) for key, col in _METRIC_COLUMN.items()}


def _league_baseline_for_season(team_table: pd.DataFrame, season: int) -> dict[str, float]:
    year_stats = team_table[
        (team_table["Season"] == season)
        & team_table[list(_METRIC_COLUMN.values())].notna().all(axis=1)
    ]
    if year_stats.empty:
        raise ValueError(f"No real Pass Defense team stats with full real metric coverage "
                          f"for season {season} -- cannot resolve a real league baseline "
                          f"(never fabricated).")
    return {key: float(year_stats[col].mean()) for key, col in _METRIC_COLUMN.items()}


def resolve_pass_defense_matchup_history(
    pbp_3yr_prior: pd.DataFrame, target_season: int, team: str,
) -> PassDefenseTeamHistory:
    """Raises ValueError (never fabricates) if `team` has no real qualifying data in any of
    the 3 real prior seasons, or if a real league baseline can't be resolved."""
    prior_table = build_real_team_table(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    )
    y1 = _metric_dict_for_team_season(prior_table, team, target_season - 1)
    y2 = _metric_dict_for_team_season(prior_table, team, target_season - 2)
    y3 = _metric_dict_for_team_season(prior_table, team, target_season - 3)
    missing = [label for label, v in (("Y-1", y1), ("Y-2", y2), ("Y-3", y3)) if v is None]
    if missing:
        raise ValueError(
            f"No real Pass Defense data found for {team!r} in {missing} -- cannot resolve "
            f"real historical Pass Defense Matchup (never fabricated)."
        )

    league_baseline_y1 = _league_baseline_for_season(prior_table, target_season - 1)
    return PassDefenseTeamHistory(
        team=team, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
    )


def resolve_pass_defense_matchup_league_stats(
    pbp_3yr_prior: pd.DataFrame, target_season: int, constants_without_league_stats,
) -> dict[str, dict[str, float]]:
    """Real Section 4: league-wide average/std-dev of the real Projected Baseline (no blend
    step exists for this tab), across every real team with full real metric coverage."""
    prior_table = build_real_team_table(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    )
    all_teams = sorted(prior_table["Team"].dropna().unique())

    proj_baselines: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for team in all_teams:
        try:
            history = resolve_pass_defense_matchup_history(pbp_3yr_prior, target_season, team)
        except ValueError:
            continue
        result: PassDefenseMatchupResult = compute_pass_defense_matchup(
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
