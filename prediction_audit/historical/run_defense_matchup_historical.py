"""
Step 6: resolves a real historical Run Defense Matchup for one real team, using only real data
available before a target game's own kickoff -- second matchup tab, following Pass Defense
Matchup's exact pattern. Team-level, no current-season blend, no player role resolution. 4 of
the 5 real metrics are "Allowed" rates (inverted, lower-is-better); Stuff Rate is deliberately
NOT inverted (higher stuff rate is better defense) -- handled inside
`compute_run_defense_matchup()` itself, confirmed via its own real `INVERTED_METRICS` set.

All 5 real metrics come from the SAME real `compute_team_season_matchup_metrics` function
Pass Defense Matchup already uses -- no second data source needed here (Run Defense has no
NY/A-style pass-only column to merge in separately).
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.efficiency import compute_team_season_matchup_metrics
from prediction_audit.engine.run_defense_matchup import (
    METRIC_KEYS,
    RunDefenseMatchupResult,
    RunDefenseTeamHistory,
    compute_run_defense_matchup,
)
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)

_METRIC_COLUMN = {
    "epa_rush": "EPA/Rush Allowed (Def)", "run_success": "Run Success Rate Allowed (Def)",
    "ypc": "Yards/Carry Allowed (Def)", "explosive_run": "Explosive Run Rate Allowed (Def)",
    "stuff_rate": "Stuff Rate Allowed (Def)",
}


def build_real_team_table(pbp: pd.DataFrame) -> pd.DataFrame:
    """Real per-team-season Run Defense Matchup metric table."""
    return compute_team_season_matchup_metrics(pbp)


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
        raise ValueError(f"No real Run Defense team stats with full real metric coverage for "
                          f"season {season} -- cannot resolve a real league baseline (never "
                          f"fabricated).")
    return {key: float(year_stats[col].mean()) for key, col in _METRIC_COLUMN.items()}


def resolve_run_defense_matchup_history(
    pbp_3yr_prior: pd.DataFrame, target_season: int, team: str,
) -> RunDefenseTeamHistory:
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
            f"No real Run Defense data found for {team!r} in {missing} -- cannot resolve "
            f"real historical Run Defense Matchup (never fabricated)."
        )

    league_baseline_y1 = _league_baseline_for_season(prior_table, target_season - 1)
    return RunDefenseTeamHistory(
        team=team, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
    )


def resolve_run_defense_matchup_league_stats(
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
            history = resolve_run_defense_matchup_history(pbp_3yr_prior, target_season, team)
        except ValueError:
            continue
        result: RunDefenseMatchupResult = compute_run_defense_matchup(
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
