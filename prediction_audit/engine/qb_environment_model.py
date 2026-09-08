"""
QB Environment Model's own real calculation chain -- CORRECTION to this project's own earlier
documentation (see PROGRESS.md): this tab is NOT out-of-scope for Z/AA. Its real "QB
Environment-Adjusted Baseline" output feeds Season Matchups' own real "Effective QB Rating"
(see effective_qb_rating.py), which in turn feeds Phase Matchup Adj -- found by re-inspecting
Season Matchups' AU/AX formulas more closely than the first pass through this tab.

Player-level (64 real QBs, same population QB Index itself scores), standard no-blend decay
chain (Success Rate, Explosive Pass Rate, Sack Rate -- confirmed via the real Section 5
formula text: none of the 3 are inverted, "higher is better" for all, including Sack Rate,
which is real but is a REFERENCE-only Z here, never part of the weighted Talent sum). Reuses
decay_baseline.py's decay_weighted_average/team_history/projected_baseline/z_score/
weighted_composite_score entirely unchanged.

Real formula chain, confirmed from the text directly:

    Section 3 (per metric): standard decay -> team_history -> projected_baseline, identical
    shape to every other no-blend tab. League baseline (Y-1) is a real per-season
    AVERAGEIFS/AVERAGEIF lookup, taken here as an already-resolved given input per this
    project's "arithmetic only, not data sourcing" scoping (same treatment as every other
    tab's league_baseline_y1).

    Section 5:
        Success Rate Z / Explosive Pass Rate Z / Sack Rate Z = standard z_score() (no
        inversion for any of the 3).
        EPA/CPOE/ANY-A Z are NOT computed on this tab -- they are LIVE-REFERENCED from QB
        Index's own Section 5 (that already-ported engine's own z_scores["epa"/"cpoe"/"anya"]),
        taken here as already-resolved given inputs (QB Index is already ported; composing
        the two engines together is the caller's job, same pattern as Explosive Play
        Matchup's own referenced Pass/Run Defense Matchup Z-scores).
        Weighted Talent Z-Sum = Success*C128 + Explosive*C129 + EPA*C34 + CPOE*C35 + ANYA*C36
            (QB Index's OWN real weights C34-36 reused unchanged for the 3 referenced metrics)
        Raw QB Talent Score = C37 + WeightedZSum*C38 (QB Index's OWN real baseline/points-per-
            SD constants reused unchanged -- "a score means the same thing on both tabs",
            per this tab's own real Section 5 header note).

    Section 6:
        Situational Adjustment = IF(new_team, -C130, 0) + IF(recently_injured, -C131, 0)
        QB Environment-Adjusted Baseline = Raw QB Talent Score + Situational Adjustment
"""
from __future__ import annotations

from dataclasses import dataclass

from .decay_baseline import (
    decay_weighted_average,
    projected_baseline,
    team_history,
    weighted_composite_score,
    z_score,
)

METRIC_KEYS = ("success", "explosive", "sack")


@dataclass
class QBEnvironmentModelConstants:
    decay_factor: float
    regression_weight: float
    last_year_emphasis: float
    league_avg: dict[str, float]   # {"success": ..., "explosive": ..., "sack": ...}
    league_std: dict[str, float]
    success_weight: float           # C128
    explosive_weight: float          # C129
    epa_weight: float                 # C34 (QB Index's own)
    cpoe_weight: float                # C35
    anya_weight: float                # C36
    score_baseline: float             # C37 (QB Index's own)
    points_per_sd: float              # C38
    new_team_penalty: float           # C130
    recently_injured_penalty: float   # C131


@dataclass
class QBEnvironmentModelHistory:
    player_id: str
    y1: dict[str, float]
    y2: dict[str, float]
    y3: dict[str, float]
    league_baseline_y1: dict[str, float]
    # Already-resolved given inputs, live-referenced from the already-ported QB Index engine's
    # own z_scores (compute_qb_index(...).z_scores["epa"/"cpoe"/"anya"] for this same QB).
    epa_z_ref: float
    cpoe_z_ref: float
    anya_z_ref: float
    new_team_this_season: bool
    recently_returned_from_injury: bool


@dataclass
class QBEnvironmentModelResult:
    player_id: str
    weighted_avg: dict[str, float]
    team_history: dict[str, float]
    proj_baseline: dict[str, float]
    z_scores: dict[str, float]        # success, explosive, sack (sack is reference-only)
    weighted_zsum: float
    raw_talent_score: float
    situational_adj: float
    adjusted_baseline: float          # the tab's own real final output


def compute_qb_environment_model(
    history: QBEnvironmentModelHistory, constants: QBEnvironmentModelConstants,
) -> QBEnvironmentModelResult:
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

    z_scores = {
        m: z_score(pb[m], constants.league_avg[m], constants.league_std[m])
        for m in METRIC_KEYS
    }

    all_z_scores = {
        "success": z_scores["success"], "explosive": z_scores["explosive"],
        "epa": history.epa_z_ref, "cpoe": history.cpoe_z_ref, "anya": history.anya_z_ref,
    }
    weights = {
        "success": constants.success_weight, "explosive": constants.explosive_weight,
        "epa": constants.epa_weight, "cpoe": constants.cpoe_weight,
        "anya": constants.anya_weight,
    }
    weighted_zsum, raw_talent_score = weighted_composite_score(
        all_z_scores, weights, constants.score_baseline, constants.points_per_sd,
    )

    situational_adj = 0.0
    if history.new_team_this_season:
        situational_adj -= constants.new_team_penalty
    if history.recently_returned_from_injury:
        situational_adj -= constants.recently_injured_penalty

    adjusted_baseline = raw_talent_score + situational_adj

    return QBEnvironmentModelResult(
        player_id=history.player_id, weighted_avg=weighted_avg, team_history=th,
        proj_baseline=pb, z_scores=z_scores, weighted_zsum=weighted_zsum,
        raw_talent_score=raw_talent_score, situational_adj=situational_adj,
        adjusted_baseline=adjusted_baseline,
    )
