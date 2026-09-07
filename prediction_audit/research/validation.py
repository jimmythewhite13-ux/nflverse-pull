"""
Shared validation framework for Phases 2-6 research (travel, probability calibration, SOS,
HFA) -- built once here since every phase's own kickoff prompt references it as common
infrastructure, rather than reimplementing leakage checks/metrics per phase.

Real, deliberate design: every function here takes real, already-computed model outputs and
real, already-known game outcomes as input -- it never fits or predicts anything itself. That
work belongs to each phase's own model module (travel_model.py, probability_calibration.py,
sos_model.py); this module only ever measures.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import pandas as pd


def leakage_check(train_df: pd.DataFrame, test_df: pd.DataFrame, date_col: str) -> bool:
    """Real, strict temporal-split check: every real train-set date must be strictly earlier
    than every real test-set date. Returns False (never raises) so callers can enforce "stop
    and report the failure" themselves, per every phase's own explicit requirement -- a check
    that raises would make it easy to accidentally catch-and-ignore the real violation instead
    of surfacing it.

    Real, honest scope: this checks train/test SEPARATION only (no test-set date precedes any
    train-set date) -- it does not itself verify that a given feature's own real value was
    computed using only pre-cutoff data (that's each historical resolver's own job, already
    enforced throughout Steps 6-7's real walk-forward design).
    """
    if train_df.empty or test_df.empty:
        return False
    train_dates = pd.to_datetime(train_df[date_col])
    test_dates = pd.to_datetime(test_df[date_col])
    return bool(train_dates.max() < test_dates.min())


@dataclass
class EvaluationResult:
    """Real, computed metrics for one real set of predictions vs. real outcomes. `n` is the
    real sample size actually used -- always report this alongside the metrics themselves,
    since a metric computed on a real, small n deserves less trust than the same metric on a
    real, large n (the original audit's own "n=4, too small to trust" finding)."""
    n: int
    mae: float
    rmse: float
    winner_accuracy: float
    brier: float
    log_loss: float


def evaluate_predictions(
    projected_margin: pd.Series, actual_margin: pd.Series,
    home_win_probability: pd.Series, home_won: pd.Series,
) -> EvaluationResult:
    """Real MAE/RMSE/winner-accuracy/Brier/log-loss from real projected margins + real actual
    results. All four Series must already be aligned (same real games, same real order) --
    this function does not itself join or reindex, to avoid silently matching the wrong rows
    across two differently-sourced real DataFrames."""
    n = len(projected_margin)
    if n == 0:
        raise ValueError("Real evaluation requested on 0 real games -- never fabricated.")
    margin_error = projected_margin - actual_margin
    mae = margin_error.abs().mean()
    rmse = math.sqrt((margin_error**2).mean())
    winner_accuracy = ((projected_margin > 0) == (actual_margin > 0)).mean()

    p = home_win_probability.clip(1e-6, 1 - 1e-6)
    y = home_won.astype(float)
    brier = ((p - y) ** 2).mean()
    log_loss = -(y * p.apply(math.log) + (1 - y) * (1 - p).apply(math.log)).mean()

    return EvaluationResult(
        n=n, mae=float(mae), rmse=float(rmse), winner_accuracy=float(winner_accuracy),
        brier=float(brier), log_loss=float(log_loss),
    )


@dataclass
class ChallengerDelta:
    """Real, signed deltas (challenger - champion) per metric. For MAE/RMSE/Brier/log_loss,
    negative = the challenger really improved on the champion (lower error). For
    winner_accuracy, positive = real improvement (higher accuracy)."""
    champion: EvaluationResult
    challenger: EvaluationResult
    mae_delta: float
    rmse_delta: float
    winner_accuracy_delta: float
    brier_delta: float
    log_loss_delta: float

    @property
    def improved(self) -> bool:
        """Real, simple improvement rule: MAE and Brier both improve (this project's own two
        real headline metrics from Steps 7/12) -- a challenger that trades one for the other
        is NOT unambiguously better and should not be called `improved` without the real,
        specific tradeoff being stated explicitly by the caller."""
        return self.mae_delta < 0 and self.brier_delta < 0


def challenger_delta(champion: EvaluationResult, challenger: EvaluationResult) -> ChallengerDelta:
    """Real, direct comparison of two already-computed EvaluationResults -- does not itself
    re-run any model, just diffs the real numbers each one already reports."""
    return ChallengerDelta(
        champion=champion, challenger=challenger,
        mae_delta=challenger.mae - champion.mae,
        rmse_delta=challenger.rmse - champion.rmse,
        winner_accuracy_delta=challenger.winner_accuracy - champion.winner_accuracy,
        brier_delta=challenger.brier - champion.brier,
        log_loss_delta=challenger.log_loss - champion.log_loss,
    )
