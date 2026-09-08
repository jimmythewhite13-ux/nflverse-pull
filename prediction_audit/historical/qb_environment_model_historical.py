"""
Step 6: resolves a real historical QB Environment Model for one specific real player, using
only real data available before a target season -- fifth matchup-adjacent tab, and the one
this project's own PROGRESS.md previously (incorrectly) documented as out of scope for Z/AA
before a real correction found it DOES feed Season Matchups via Effective QB Rating.

Reuses the already-built QB Index walk-forward resolver directly: `epa_z_ref`/`cpoe_z_ref`/
`anya_z_ref` are QB Index's own real Z-scores for the SAME player (`compute_qb_index(...)
.z_scores["epa"/"cpoe"/"anya"]`), composed here exactly as the real engine's own docstring
describes ("live-referenced... composing the two engines together is the caller's job").

New real data source: `nflverse_pull.qb_stats.compute_player_season_qb_extended_stats` (real
Success Rate / Explosive Pass Rate / Sack Rate, already parameterized for any real years --
first used this session for QB Index's own current-season resolution, reused here for its
OTHER real metrics).

Two real, deliberately scoped inputs (documented, not fabricated):
- `new_team_this_season` IS computed for real -- compares the real Team on this player's most
  recent real qualifying season against his real Y-1 team.
- `recently_returned_from_injury` defaults to False. No free, reliable real data source for
  this specific flag was identified in this session (unlike every other placeholder in this
  project, this one is NOT weight-0 -- it can reduce a real player's Situational Adjustment by
  a real, nonzero amount when it should apply -- so a walk-forward score for a player who
  genuinely just returned from injury will be a real, honest slight overestimate for that
  specific real case, not indistinguishable from the true value).
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.qb_stats import compute_player_season_qb_extended_stats
from prediction_audit.engine.qb_environment_model import (
    QBEnvironmentModelHistory,
    QBEnvironmentModelResult,
    compute_qb_environment_model,
)
from prediction_audit.engine.qb_index import QBIndexConstants, compute_qb_index
from prediction_audit.historical.qb_index_historical import resolve_qb_index_history
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)

_METRIC_COLUMN = {
    "success": "Success Rate", "explosive": "Explosive Pass Rate", "sack": "Sack Rate",
}


def build_real_metric_table(pbp: pd.DataFrame) -> pd.DataFrame:
    """Real per-player-season Success/Explosive/Sack Rate table."""
    return compute_player_season_qb_extended_stats(
        normalize_relocated_abbreviations(pbp, columns=PBP_TEAM_COLUMNS)
    )


def _metric_dict_for_player_season(
    metric_table: pd.DataFrame, player_id: str, season: int,
) -> dict[str, float] | None:
    match = metric_table[
        (metric_table["Player ID"] == player_id) & (metric_table["Season"] == season)
    ]
    if match.empty:
        return None
    row = match.iloc[0]
    if any(pd.isna(row[col]) for col in _METRIC_COLUMN.values()):
        return None
    return {key: float(row[col]) for key, col in _METRIC_COLUMN.items()}


def _league_baseline_for_season(metric_table: pd.DataFrame, season: int) -> dict[str, float]:
    year_stats = metric_table[
        (metric_table["Season"] == season)
        & metric_table[list(_METRIC_COLUMN.values())].notna().all(axis=1)
    ]
    if year_stats.empty:
        raise ValueError(f"No real QB extended-stats coverage for season {season} -- cannot "
                          f"resolve a real league baseline (never fabricated).")
    return {key: float(year_stats[col].mean()) for key, col in _METRIC_COLUMN.items()}


def _resolve_new_team_flag(
    metric_table: pd.DataFrame, player_id: str, target_season: int,
) -> bool:
    """Real, computed (not fabricated): True if this player's real team in target_season-1
    differs from his real team in target_season-2 -- a real proxy for "changed teams
    recently" using the same real data already being pulled, not a guess."""
    y1 = metric_table[
        (metric_table["Player ID"] == player_id) & (metric_table["Season"] == target_season - 1)
    ]
    y2 = metric_table[
        (metric_table["Player ID"] == player_id) & (metric_table["Season"] == target_season - 2)
    ]
    if y1.empty or y2.empty:
        return False
    return y1.iloc[0]["Team"] != y2.iloc[0]["Team"]


def resolve_qb_environment_model_history(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame,
    sched: pd.DataFrame, target_season: int, target_week: int, team: str, role: str,
) -> QBEnvironmentModelHistory:
    """Raises ValueError (never fabricates) if QB Index itself can't resolve `team`/`role`,
    or if a real Y1/Y2/Y3/league-baseline value for this tab's own metrics can't be resolved."""
    # Reuse the already-built QB Index resolver for the real EPA/CPOE/ANY-A Z-score
    # references -- placeholder league stats are fine here since only .z_scores is read, not
    # .score (same real technique resolve_qb_index_league_stats() itself uses internally).
    placeholder_qb_constants = QBIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        blend_base=0.15, blend_per_game=0.08, blend_cap=0.85,
        weights={"epa": 0.5, "cpoe": 0.3, "anya": 0.2},
        score_baseline=50, points_per_sd=10,
        league_avg={"epa": 0.0, "cpoe": 0.0, "anya": 0.0},
        league_std={"epa": 1.0, "cpoe": 1.0, "anya": 1.0},
    )
    qb_history = resolve_qb_index_history(
        pbp_3yr_prior, pbp_current_season, sched, target_season, target_week, team, role,
    )
    qb_result = compute_qb_index(qb_history, placeholder_qb_constants)
    player_id = qb_history.player_id

    metric_table = build_real_metric_table(pbp_3yr_prior)
    y1 = _metric_dict_for_player_season(metric_table, player_id, target_season - 1)
    y2 = _metric_dict_for_player_season(metric_table, player_id, target_season - 2)
    y3 = _metric_dict_for_player_season(metric_table, player_id, target_season - 3)
    missing = [label for label, v in (("Y-1", y1), ("Y-2", y2), ("Y-3", y3)) if v is None]
    if missing:
        raise ValueError(
            f"Real player {player_id!r} ({team} {role}) has no real qualifying QB Environment "
            f"Model data in {missing} -- never fabricated here."
        )

    league_baseline_y1 = _league_baseline_for_season(metric_table, target_season - 1)
    new_team = _resolve_new_team_flag(metric_table, player_id, target_season)

    return QBEnvironmentModelHistory(
        player_id=player_id, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
        epa_z_ref=qb_result.z_scores["epa"], cpoe_z_ref=qb_result.z_scores["cpoe"],
        anya_z_ref=qb_result.z_scores["anya"], new_team_this_season=new_team,
        recently_returned_from_injury=False,
    )


def resolve_qb_environment_model_league_stats(
    pbp_3yr_prior: pd.DataFrame, target_season: int, constants_without_league_stats,
) -> dict[str, dict[str, float]]:
    """Real Section 4: league-wide average/std-dev of the real Projected Baseline for this
    tab's own 3 metrics (success/explosive/sack -- NOT the EPA/CPOE/ANY-A references, which
    reuse QB Index's own Section 4 unchanged), across every real qualifying player."""
    metric_table = build_real_metric_table(pbp_3yr_prior)
    year1_ids = set(
        metric_table[metric_table["Season"] == target_season - 1]["Player ID"]
    )

    proj_baselines: dict[str, list[float]] = {key: [] for key in _METRIC_COLUMN}
    for player_id in year1_ids:
        y1 = _metric_dict_for_player_season(metric_table, player_id, target_season - 1)
        y2 = _metric_dict_for_player_season(metric_table, player_id, target_season - 2)
        y3 = _metric_dict_for_player_season(metric_table, player_id, target_season - 3)
        if y1 is None or y2 is None or y3 is None:
            continue
        league_baseline_y1 = _league_baseline_for_season(metric_table, target_season - 1)
        history = QBEnvironmentModelHistory(
            player_id=player_id, y1=y1, y2=y2, y3=y3, league_baseline_y1=league_baseline_y1,
            epa_z_ref=0.0, cpoe_z_ref=0.0, anya_z_ref=0.0, new_team_this_season=False,
            recently_returned_from_injury=False,
        )
        result: QBEnvironmentModelResult = compute_qb_environment_model(
            history, constants_without_league_stats,
        )
        for key in _METRIC_COLUMN:
            proj_baselines[key].append(result.proj_baseline[key])

    stats = {}
    for key in _METRIC_COLUMN:
        values = pd.Series(proj_baselines[key])
        if values.empty:
            raise ValueError(
                f"No real qualifying players resolved league-wide for metric {key!r} in "
                f"season {target_season} (never fabricated)."
            )
        stats[key] = {"avg": float(values.mean()), "std": float(values.std(ddof=0))}
    return stats
