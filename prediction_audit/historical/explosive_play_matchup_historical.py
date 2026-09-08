"""
Step 6: resolves a real historical Explosive Play Matchup for one real team, using only real
data available before a target game's own kickoff -- the last remaining unported piece, and
the one this project's own PROGRESS.md flagged from the start as genuinely harder: it
cross-references Pass Defense Matchup's and Run Defense Matchup's own real Z-scores directly.

Composes 3 already-built real resolvers, not just 1 new data source: this team's own real
`resolve_pass_defense_matchup_history()`/`resolve_run_defense_matchup_history()` results
provide the real `explosive_pass_allowed_z_ref`/`explosive_run_allowed_z_ref` this tab's own
real formula live-references (confirmed via the engine's own docstring: THIS team's own
defensive Z, not an opponent's -- the opponent-vs-team matchup diff happens one level up, in
`explosive_play_matchup_adj()`, which this module does not call).

This tab's own 4 real metrics come from two already-parameterized real
`nflverse_pull.efficiency` functions: `compute_team_season_matchup_metrics` (Explosive
Pass/Run Rate (Off) -- the SAME function Pass/Run Defense Matchup already use, just reading
its Off-side columns this time) and `compute_team_season_deep_pass_yac_metrics` (real Deep
Pass Completion Rate Allowed, real YAC Allowed).
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.efficiency import (
    compute_team_season_deep_pass_yac_metrics,
    compute_team_season_matchup_metrics,
)
from prediction_audit.engine.explosive_play_matchup import (
    ExplosivePlayMatchupConstants,
    ExplosivePlayMatchupResult,
    ExplosivePlayMatchupTeamHistory,
    compute_explosive_play_matchup,
)
from prediction_audit.engine.pass_defense_matchup import (
    PassDefenseMatchupConstants,
    compute_pass_defense_matchup,
)
from prediction_audit.engine.run_defense_matchup import (
    RunDefenseMatchupConstants,
    compute_run_defense_matchup,
)
from prediction_audit.historical.pass_defense_matchup_historical import (
    resolve_pass_defense_matchup_history,
)
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)
from prediction_audit.historical.run_defense_matchup_historical import (
    resolve_run_defense_matchup_history,
)

_METRIC_COLUMN = {
    "pass_off": "Explosive Pass Rate (Off)", "run_off": "Explosive Run Rate (Off)",
    "deep_pass_allowed": "Deep Pass Completion Rate Allowed (Def)",
    "yac_allowed": "YAC Allowed (Def)",
}


def build_real_team_table(pbp: pd.DataFrame) -> pd.DataFrame:
    """Real merged per-team-season Explosive Play Matchup metric table."""
    matchup = compute_team_season_matchup_metrics(pbp)
    deep_yac = compute_team_season_deep_pass_yac_metrics(pbp)
    return matchup.merge(
        deep_yac[["Team", "Season", "Deep Pass Completion Rate Allowed (Def)",
                  "YAC Allowed (Def)"]],
        on=["Team", "Season"], how="left",
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
        raise ValueError(f"No real Explosive Play team stats with full real metric coverage "
                          f"for season {season} -- cannot resolve a real league baseline "
                          f"(never fabricated).")
    return {key: float(year_stats[col].mean()) for key, col in _METRIC_COLUMN.items()}


def resolve_explosive_play_matchup_history(
    pbp_3yr_prior: pd.DataFrame, target_season: int, team: str,
    pass_defense_constants: PassDefenseMatchupConstants,
    run_defense_constants: RunDefenseMatchupConstants,
) -> ExplosivePlayMatchupTeamHistory:
    """Raises ValueError (never fabricates) if `team` has no real qualifying data in any of
    the 3 real prior seasons for this tab's own 4 metrics, or if the referenced Pass/Run
    Defense Matchup resolution itself fails for this team."""
    pd_history = resolve_pass_defense_matchup_history(pbp_3yr_prior, target_season, team)
    pd_result = compute_pass_defense_matchup(pd_history, pass_defense_constants)
    rd_history = resolve_run_defense_matchup_history(pbp_3yr_prior, target_season, team)
    rd_result = compute_run_defense_matchup(rd_history, run_defense_constants)

    team_table = build_real_team_table(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    )
    metrics = {}
    for label, season in (("y1", target_season - 1), ("y2", target_season - 2),
                          ("y3", target_season - 3)):
        m = _metric_dict_for_team_season(team_table, team, season)
        if m is None:
            raise ValueError(
                f"No real Explosive Play data found for {team!r} in {season} ({label}) -- "
                f"cannot resolve real historical Explosive Play Matchup (never fabricated)."
            )
        metrics[label] = m

    league_baseline_y1 = _league_baseline_for_season(team_table, target_season - 1)

    return ExplosivePlayMatchupTeamHistory(
        team=team,
        pass_off_y1=metrics["y1"]["pass_off"], pass_off_y2=metrics["y2"]["pass_off"],
        pass_off_y3=metrics["y3"]["pass_off"],
        pass_off_league_baseline_y1=league_baseline_y1["pass_off"],
        run_off_y1=metrics["y1"]["run_off"], run_off_y2=metrics["y2"]["run_off"],
        run_off_y3=metrics["y3"]["run_off"],
        run_off_league_baseline_y1=league_baseline_y1["run_off"],
        deep_pass_allowed_y1=metrics["y1"]["deep_pass_allowed"],
        deep_pass_allowed_y2=metrics["y2"]["deep_pass_allowed"],
        deep_pass_allowed_y3=metrics["y3"]["deep_pass_allowed"],
        deep_pass_allowed_league_baseline_y1=league_baseline_y1["deep_pass_allowed"],
        yac_allowed_y1=metrics["y1"]["yac_allowed"], yac_allowed_y2=metrics["y2"]["yac_allowed"],
        yac_allowed_y3=metrics["y3"]["yac_allowed"],
        yac_allowed_league_baseline_y1=league_baseline_y1["yac_allowed"],
        explosive_pass_allowed_z_ref=pd_result.z_scores["explosive_pass"],
        explosive_run_allowed_z_ref=rd_result.z_scores["explosive_run"],
    )


def resolve_explosive_play_matchup_league_stats(
    pbp_3yr_prior: pd.DataFrame, target_season: int,
    pass_defense_constants: PassDefenseMatchupConstants,
    run_defense_constants: RunDefenseMatchupConstants,
    constants_without_league_stats: ExplosivePlayMatchupConstants,
) -> dict[str, dict[str, float]]:
    """Real league-wide average/std-dev of the real Projected Baseline (no blend step exists
    for this tab), for this tab's own 4 metrics, across every real team that resolves fully
    (including its own real Pass/Run Defense Matchup reference)."""
    team_table = build_real_team_table(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    )
    all_teams = sorted(team_table["Team"].dropna().unique())

    proj_baselines: dict[str, list[float]] = {key: [] for key in _METRIC_COLUMN}
    for team in all_teams:
        try:
            history = resolve_explosive_play_matchup_history(
                pbp_3yr_prior, target_season, team, pass_defense_constants,
                run_defense_constants,
            )
        except ValueError:
            continue
        result: ExplosivePlayMatchupResult = compute_explosive_play_matchup(
            history, constants_without_league_stats,
        )
        proj_baselines["pass_off"].append(result.pass_off_proj_baseline)
        proj_baselines["run_off"].append(result.run_off_proj_baseline)
        proj_baselines["deep_pass_allowed"].append(result.deep_pass_allowed_proj_baseline)
        proj_baselines["yac_allowed"].append(result.yac_allowed_proj_baseline)

    stats = {}
    for key in _METRIC_COLUMN:
        values = pd.Series(proj_baselines[key])
        if values.empty:
            raise ValueError(
                f"No real qualifying teams resolved league-wide for metric {key!r} in "
                f"season {target_season} (never fabricated)."
            )
        stats[key] = {"avg": float(values.mean()), "std": float(values.std(ddof=0))}
    return stats
