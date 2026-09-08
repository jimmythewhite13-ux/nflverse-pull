"""
First piece of the "Python Model Engine" the validation/audit master spec's own roadmap ends
with (VALIDATED MODEL SPECIFICATION -> PYTHON MODEL ENGINE -> ...) -- and, just as
importantly, the engine Step 6 (walk-forward historical reconstruction) needs to actually run
the model programmatically at scale, since re-entering data by hand for thousands of
historical game-weeks isn't practical. Built once, used for both.

This module re-implements, as pure Python functions, the SAME 3-Yr decay-weighted-baseline ->
current-season-blend -> Z-score -> weighted-composite arithmetic that every position-index
tab's own Section 3/4/5 Excel formulas already compute -- not a redesign, a literal port.
Every function here is validated for EXACT numeric parity against v35's own real recalculated
values (see tests/test_qb_index_parity.py, which runs every one of these functions against
all 64 real current-roster QBs and checks each intermediate value, not just the final Score).

Deliberately scoped to the ARITHMETIC only, not the data sourcing: these functions take
already-resolved real per-player Y-1/Y-2/Y-3 values as arguments (however those were
resolved -- real historical data, or Section 2B's own real rookie substitution logic, which
this module does NOT re-implement in this first pass). This isolates "does the calculation
logic match Excel" from "does the data pull match Excel" as two genuinely separate questions,
proven independently rather than conflated into one pass/fail.
"""
from __future__ import annotations


def decay_weighted_average(y1: float, y2: float, y3: float, decay_factor: float) -> float:
    """
    Excel: =(Y1*1 + Y2*decay + Y3*decay^2) / (1 + decay + decay^2)
    Every position-index tab's own Section 3 uses this exact same shape -- e.g. QB Index's
    real J173: `=(G173*1+H173*'Model Assumptions'!$C$20+I173*('Model Assumptions'!$C$20^2))
    /(1+'Model Assumptions'!$C$20+'Model Assumptions'!$C$20^2)`.
    """
    return (
        (y1 * 1 + y2 * decay_factor + y3 * (decay_factor ** 2))
        / (1 + decay_factor + decay_factor ** 2)
    )


def team_history(y1: float, weighted_avg: float, last_year_emphasis: float) -> float:
    """
    Excel: =Y1*last_year_emphasis + WeightedAvg*(1-last_year_emphasis)
    "Team History" -- blends the most recent real season more heavily against the full 3-Yr
    decay-weighted average, per the model's own "last year matters most" design choice.
    """
    return y1 * last_year_emphasis + weighted_avg * (1 - last_year_emphasis)


def projected_baseline(
    team_history_value: float, league_baseline: float, regression_weight: float,
) -> float:
    """
    Excel: =TeamHistory*regression_weight + LeagueBaseline*(1-regression_weight)
    Regresses a team/player's own real history toward the real league-wide baseline --
    "Carryover Weight" in Model Assumptions' own label, C21 in every tab that uses it.
    """
    return (
        team_history_value * regression_weight + league_baseline * (1 - regression_weight)
    )


def blend_weight(games_played: int, base: float, per_game: float, cap: float) -> float:
    """
    Excel: =IF(GamesPlayed=0,0,MIN(cap, base+(per_game*(GamesPlayed-1))))
    The EXACT SAME real formula shape Team Ratings' own PPG blend originally established
    (Model Assumptions C12/C13/C14), reused identically by current_season_blend.py across
    every position-index tab -- not a tab-specific variant.
    """
    if games_played == 0:
        return 0.0
    return min(cap, base + (per_game * (games_played - 1)))


def blended_value(
    proj_baseline: float, current_season_value: float, weight: float,
) -> float:
    """Excel: =ProjectedBaseline*(1-weight) + CurrentSeasonValue*weight"""
    return proj_baseline * (1 - weight) + current_season_value * weight


def z_score(value: float, league_avg: float, league_std: float) -> float:
    """
    Excel: =(Value-LeagueAvg)/LeagueStdDev
    LeagueStdDev is always computed via STDEVP (population std. dev.), never STDEV.S, per
    this project's own formatting/safety convention -- see the ground-truth extraction script
    for confirmation the real league_std values used here came from a real STDEVP cell.
    """
    return (value - league_avg) / league_std


def weighted_composite_score(
    z_scores: dict[str, float], weights: dict[str, float], baseline: float,
    points_per_sd: float,
) -> tuple[float, float]:
    """
    Excel: WeightedZSum = sum(Z_i * weight_i); Score = baseline + WeightedZSum*points_per_sd.
    `z_scores` and `weights` must share the same keys. Returns (weighted_zsum, score).
    """
    weighted_zsum = sum(z_scores[k] * weights[k] for k in z_scores)
    score = baseline + weighted_zsum * points_per_sd
    return weighted_zsum, score
