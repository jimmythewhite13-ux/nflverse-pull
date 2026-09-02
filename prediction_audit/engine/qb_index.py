"""
QB Index's own real calculation chain, built from decay_baseline.py's shared generic
functions -- the first fully-wired position-index tab in the Python Model Engine. Mirrors
build_qb_index.py's real Section 3 -> current_season_blend.py's Section 3 extension ->
Section 4 -> Section 5 chain exactly, metric by metric (EPA/Play, CPOE, ANY/A -- Pure Y/A is
deliberately excluded here, matching its own real weight of 0 in QB Index Score; see
build_qb_index.py's own METRICS entry for why it exists at all).
"""
from __future__ import annotations

from dataclasses import dataclass

from .decay_baseline import (
    blend_weight,
    blended_value,
    decay_weighted_average,
    projected_baseline,
    team_history,
    weighted_composite_score,
    z_score,
)

METRIC_KEYS = ("epa", "cpoe", "anya")


@dataclass
class QBIndexConstants:
    """Every real Model Assumptions constant QB Index's own chain reads -- one object, not
    scattered magic numbers, so a parity test can construct it once from real extracted
    values and pass it to every player."""
    decay_factor: float          # Model Assumptions C20
    regression_weight: float     # C21 ("Carryover Weight")
    last_year_emphasis: float    # C22
    blend_base: float            # C12
    blend_per_game: float        # C13
    blend_cap: float             # C14
    weights: dict[str, float]    # {"epa": C34, "cpoe": C35, "anya": C36}
    score_baseline: float        # C37
    points_per_sd: float         # C38
    league_avg: dict[str, float]  # Section 4's real per-metric league average
    league_std: dict[str, float]  # Section 4's real per-metric STDEVP


@dataclass
class QBHistory:
    """One real QB's real Y-1/Y-2/Y-3 per metric (already resolved -- real history or
    Section 2B's own real rookie substitution, not re-derived here) plus real league
    baseline-by-year and real current-season/games-played blend inputs."""
    player_id: str
    y1: dict[str, float]
    y2: dict[str, float]
    y3: dict[str, float]
    league_baseline_y1: dict[str, float]
    games_played: int
    current_season: dict[str, float]


@dataclass
class QBIndexResult:
    player_id: str
    weighted_avg: dict[str, float]
    team_history: dict[str, float]
    proj_baseline: dict[str, float]
    blend_weight: float
    blended: dict[str, float]
    z_scores: dict[str, float]
    weighted_zsum: float
    score: float


def compute_qb_index(history: QBHistory, constants: QBIndexConstants) -> QBIndexResult:
    """Pure function -- the full real per-QB chain, metric by metric, then the weighted
    composite Score. No I/O, no network -- everything it needs is already in `history` and
    `constants`."""
    weighted_avg = {}
    th = {}
    pb = {}
    for m in METRIC_KEYS:
        weighted_avg[m] = decay_weighted_average(
            history.y1[m], history.y2[m], history.y3[m], constants.decay_factor,
        )
        th[m] = team_history(history.y1[m], weighted_avg[m], constants.last_year_emphasis)
        pb[m] = projected_baseline(
            th[m], history.league_baseline_y1[m], constants.regression_weight,
        )

    bw = blend_weight(
        history.games_played, constants.blend_base, constants.blend_per_game,
        constants.blend_cap,
    )
    blended = {
        m: blended_value(pb[m], history.current_season[m], bw) for m in METRIC_KEYS
    }

    z_scores = {
        m: z_score(blended[m], constants.league_avg[m], constants.league_std[m])
        for m in METRIC_KEYS
    }
    weighted_zsum, score = weighted_composite_score(
        z_scores, constants.weights, constants.score_baseline, constants.points_per_sd,
    )

    return QBIndexResult(
        player_id=history.player_id, weighted_avg=weighted_avg, team_history=th,
        proj_baseline=pb, blend_weight=bw, blended=blended, z_scores=z_scores,
        weighted_zsum=weighted_zsum, score=score,
    )


def replacement_value_index_points(
    starter_score: float | None, backup_score: float | None,
) -> float | None:
    """QB Index Section 6, column F: Starter QB Index Score minus Backup QB Index Score, per
    team. Real formula: =IF(OR(C="",E=""),"",C-E) -- a team whose Starter or Backup never
    reached the real qualifying dropback threshold shows blank rather than a misleading 0."""
    if starter_score in (None, "") or backup_score in (None, ""):
        return None
    return starter_score - backup_score


def replacement_value_game_points(
    rv_index_points: float | None, conversion: float,
) -> float | None:
    """QB Index Section 6, column G: applies the real Points-to-Game-Points Conversion
    (Model Assumptions C39). Real formula: =IF(F="","",F*C39)."""
    if rv_index_points in (None, ""):
        return None
    return rv_index_points * conversion
