"""
Explosive Play Matchup's own real calculation chain -- the last remaining unported piece of
the real Z/AA formula (every other named term in v35_core_formula_components.csv is now
ported: see core_formula_simple_terms.py and team_quality.py).

Team-level (32 real teams), 4 real metrics, standard no-blend decay -> team-history ->
projected-baseline -> Z-score chain (same shape as Coaching/Pass-Defense/Run-Defense/etc.) for
Explosive Pass Rate (Off), Explosive Run Rate (Off), Deep Pass Completion Rate Allowed, and
YAC Allowed. Confirmed by reading the real Section 3/4/5 formula text directly (never assumed):
Explosive Pass/Run Rate (Off) are "higher is better" (no inversion); Deep Pass Comp. Allowed
and YAC Allowed are "lower is better" (inverted, same convention as pass_defense_matchup.py --
z_score() computed normally then negated).

Two real composites, NOT a single weighted_composite_score() call, and NOT symmetric --
confirmed a genuine, documented asymmetry in the tab's own Section 5 header text:
  - Pass Prevention Composite Z = a 3-term weighted sum of an Explosive Pass Rate Allowed Z
    LIVE-REFERENCED from Pass Defense Matchup's own Section 5 (that engine's own
    z_scores["explosive_pass"], already inverted there) plus this tab's own Deep Pass
    Completion Allowed Z and YAC Allowed Z.
  - Run Prevention Z is JUST Run Defense Matchup's own Explosive Run Rate Allowed Z
    (z_scores["explosive_run"]), live-referenced directly with no blending at all -- the tab's
    own header states "no run-side equivalent to Deep Pass/YAC exists."

Per this project's "arithmetic only, not data sourcing" scoping (used throughout), the
referenced Pass/Run Defense Matchup Z-scores are taken here as already-resolved given inputs
(both engines are already ported) rather than recomputed.

Season Matchups then wires each side's own Explosive Pass/Run Rate (Off) Z against the
OPPONENT's Pass/Run Prevention composite (a genuine home-vs-away matchup diff, not a
same-team lookup), converts to points, and sums -- confirmed via the real formula text:

    CE (Home Pass diff) = Home Pass Off Z - Away Pass Prevention Composite Z
    CH (Away Pass diff) = Away Pass Off Z - Home Pass Prevention Composite Z
    CK (Home Run diff)  = Home Run Off Z  - Away Run Prevention Z
    CN (Away Run diff)  = Away Run Off Z  - Home Run Prevention Z
    CO (Home Adj, pts)  = CE*C140 + CK*C141
    CP (Away Adj, pts)  = CH*C140 + CN*C141
"""
from __future__ import annotations

from dataclasses import dataclass

from .decay_baseline import (
    decay_weighted_average,
    projected_baseline,
    team_history,
    z_score,
)


@dataclass
class ExplosivePlayMatchupConstants:
    decay_factor: float
    regression_weight: float
    last_year_emphasis: float
    league_avg_pass_off: float
    league_std_pass_off: float
    league_avg_run_off: float
    league_std_run_off: float
    league_avg_deep_pass_allowed: float
    league_std_deep_pass_allowed: float
    league_avg_yac_allowed: float
    league_std_yac_allowed: float
    pass_prevention_w_explosive_pass_allowed: float  # C136
    pass_prevention_w_deep_pass_allowed: float          # C137
    pass_prevention_w_yac_allowed: float                 # C138


@dataclass
class ExplosivePlayMatchupTeamHistory:
    team: str
    pass_off_y1: float
    pass_off_y2: float
    pass_off_y3: float
    pass_off_league_baseline_y1: float
    run_off_y1: float
    run_off_y2: float
    run_off_y3: float
    run_off_league_baseline_y1: float
    deep_pass_allowed_y1: float
    deep_pass_allowed_y2: float
    deep_pass_allowed_y3: float
    deep_pass_allowed_league_baseline_y1: float
    yac_allowed_y1: float
    yac_allowed_y2: float
    yac_allowed_y3: float
    yac_allowed_league_baseline_y1: float
    # Already-resolved given inputs, live-referenced from the already-ported Pass/Run Defense
    # Matchup engines' own Section 5 (that tab's z_scores["explosive_pass"]/["explosive_run"]).
    explosive_pass_allowed_z_ref: float
    explosive_run_allowed_z_ref: float


@dataclass
class ExplosivePlayMatchupResult:
    team: str
    pass_off_weighted_avg: float
    pass_off_team_history: float
    pass_off_proj_baseline: float
    pass_off_z: float
    run_off_weighted_avg: float
    run_off_team_history: float
    run_off_proj_baseline: float
    run_off_z: float
    deep_pass_allowed_weighted_avg: float
    deep_pass_allowed_team_history: float
    deep_pass_allowed_proj_baseline: float
    deep_pass_allowed_z: float
    yac_allowed_weighted_avg: float
    yac_allowed_team_history: float
    yac_allowed_proj_baseline: float
    yac_allowed_z: float
    pass_prevention_composite_z: float
    run_prevention_z: float


def compute_explosive_play_matchup(
    history: ExplosivePlayMatchupTeamHistory, constants: ExplosivePlayMatchupConstants,
) -> ExplosivePlayMatchupResult:
    def _chain(y1, y2, y3, league_baseline_y1):
        wavg = decay_weighted_average(y1, y2, y3, constants.decay_factor)
        th = team_history(y1, wavg, constants.last_year_emphasis)
        pb = projected_baseline(th, league_baseline_y1, constants.regression_weight)
        return wavg, th, pb

    pass_off_wavg, pass_off_th, pass_off_pb = _chain(
        history.pass_off_y1, history.pass_off_y2, history.pass_off_y3,
        history.pass_off_league_baseline_y1,
    )
    pass_off_z = z_score(pass_off_pb, constants.league_avg_pass_off, constants.league_std_pass_off)

    run_off_wavg, run_off_th, run_off_pb = _chain(
        history.run_off_y1, history.run_off_y2, history.run_off_y3,
        history.run_off_league_baseline_y1,
    )
    run_off_z = z_score(run_off_pb, constants.league_avg_run_off, constants.league_std_run_off)

    deep_pass_wavg, deep_pass_th, deep_pass_pb = _chain(
        history.deep_pass_allowed_y1, history.deep_pass_allowed_y2,
        history.deep_pass_allowed_y3, history.deep_pass_allowed_league_baseline_y1,
    )
    deep_pass_z = -z_score(
        deep_pass_pb, constants.league_avg_deep_pass_allowed,
        constants.league_std_deep_pass_allowed,
    )  # inverted -- lower is better for the defense

    yac_wavg, yac_th, yac_pb = _chain(
        history.yac_allowed_y1, history.yac_allowed_y2, history.yac_allowed_y3,
        history.yac_allowed_league_baseline_y1,
    )
    yac_z = -z_score(
        yac_pb, constants.league_avg_yac_allowed, constants.league_std_yac_allowed,
    )  # inverted -- lower is better for the defense

    pass_prevention_composite_z = (
        history.explosive_pass_allowed_z_ref * constants.pass_prevention_w_explosive_pass_allowed
        + deep_pass_z * constants.pass_prevention_w_deep_pass_allowed
        + yac_z * constants.pass_prevention_w_yac_allowed
    )
    run_prevention_z = history.explosive_run_allowed_z_ref  # direct passthrough, no blending

    return ExplosivePlayMatchupResult(
        team=history.team,
        pass_off_weighted_avg=pass_off_wavg, pass_off_team_history=pass_off_th,
        pass_off_proj_baseline=pass_off_pb, pass_off_z=pass_off_z,
        run_off_weighted_avg=run_off_wavg, run_off_team_history=run_off_th,
        run_off_proj_baseline=run_off_pb, run_off_z=run_off_z,
        deep_pass_allowed_weighted_avg=deep_pass_wavg,
        deep_pass_allowed_team_history=deep_pass_th,
        deep_pass_allowed_proj_baseline=deep_pass_pb, deep_pass_allowed_z=deep_pass_z,
        yac_allowed_weighted_avg=yac_wavg, yac_allowed_team_history=yac_th,
        yac_allowed_proj_baseline=yac_pb, yac_allowed_z=yac_z,
        pass_prevention_composite_z=pass_prevention_composite_z,
        run_prevention_z=run_prevention_z,
    )


def explosive_play_matchup_adj(
    home_pass_off_z: float, away_pass_prevention_z: float,
    away_pass_off_z: float, home_pass_prevention_z: float,
    home_run_off_z: float, away_run_prevention_z: float,
    away_run_off_z: float, home_run_prevention_z: float,
    pass_conversion: float, run_conversion: float,
) -> tuple[float, float]:
    """Season Matchups CO/CP: each side's own Explosive Pass/Run Rate (Off) Z matched up
    against the OPPONENT's Pass/Run Prevention composite. Returns (home_adj, away_adj)."""
    home_pass_diff = home_pass_off_z - away_pass_prevention_z
    away_pass_diff = away_pass_off_z - home_pass_prevention_z
    home_run_diff = home_run_off_z - away_run_prevention_z
    away_run_diff = away_run_off_z - home_run_prevention_z

    home_adj = home_pass_diff * pass_conversion + home_run_diff * run_conversion
    away_adj = away_pass_diff * pass_conversion + away_run_diff * run_conversion
    return home_adj, away_adj
