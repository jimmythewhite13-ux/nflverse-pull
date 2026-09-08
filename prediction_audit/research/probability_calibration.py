"""
Phase 3 -- probability calibration: fits a real, post-prediction calibration layer on top of
the existing logistic win-probability conversion, using real raw model probabilities and real
actual game outcomes only.

Real, deliberate scope: NEVER touches the expected-margin/spread calculation. This module's
whole job is a function `raw_probability -> calibrated_probability`; nothing here can feed back
into the margin the model already computed, matching Phase 3's own explicit non-negotiable
requirement. No `sklearn` dependency (not already used anywhere in this project) -- Platt
scaling is a 1D logistic regression, fit here via real gradient descent on log loss; isotonic
regression is the real, standard pool-adjacent-violators algorithm (PAVA) -- both well-defined,
bounded algorithms, implemented directly rather than adding a heavy new dependency for two
methods.
"""
from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

MIN_FIT_SAMPLE = 30


def _logit(p: np.ndarray, eps: float = 1e-6) -> np.ndarray:
    p = np.clip(p, eps, 1 - eps)
    return np.log(p / (1 - p))


def _sigmoid(x: np.ndarray) -> np.ndarray:
    return 1 / (1 + np.exp(-x))


def _fit_platt(raw_prob: np.ndarray, outcome: np.ndarray,
               lr: float = 0.1, n_iter: int = 2000) -> tuple[float, float]:
    """Real Platt scaling: fits A, B in calibrated = sigmoid(A * logit(raw) + B) via real
    gradient descent minimizing real log loss. A closed-form/Newton solver would converge
    faster, but gradient descent is simple, numerically stable for this real, low-dimensional
    (2-parameter) problem, and easy to verify by hand."""
    x = _logit(raw_prob)
    y = outcome.astype(float)
    a, b = 1.0, 0.0
    for _ in range(n_iter):
        z = a * x + b
        pred = _sigmoid(z)
        grad_a = np.mean((pred - y) * x)
        grad_b = np.mean(pred - y)
        a -= lr * grad_a
        b -= lr * grad_b
    return float(a), float(b)


def _fit_isotonic(raw_prob: np.ndarray, outcome: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    """Real isotonic regression via the standard pool-adjacent-violators algorithm (PAVA):
    sorts real (raw_prob, outcome) pairs by raw_prob, then merges adjacent blocks whenever the
    next block's real mean outcome would violate monotonicity, replacing both with their real
    pooled mean. Returns (sorted_x, fitted_y) -- real step-function calibration, applied at
    predict time via `np.interp`."""
    order = np.argsort(raw_prob)
    x = raw_prob[order]
    y = outcome[order].astype(float)

    # Real PAVA: each block starts as a single real point; merge backward whenever the newest
    # block's real mean is lower than the block before it (a real monotonicity violation).
    block_sum = list(y)
    block_count = [1] * len(y)
    i = 0
    means = list(y)
    while i < len(means) - 1:
        if means[i] > means[i + 1]:
            merged_sum = block_sum[i] + block_sum[i + 1]
            merged_count = block_count[i] + block_count[i + 1]
            means[i] = merged_sum / merged_count
            block_sum[i] = merged_sum
            block_count[i] = merged_count
            del means[i + 1], block_sum[i + 1], block_count[i + 1]
            if i > 0:
                i -= 1
        else:
            i += 1

    fitted_y = np.repeat(means, block_count)
    return x, fitted_y


@dataclass
class ProbabilityCalibrator:
    """Fits and applies a real calibration layer. `method`: "platt" or "isotonic"."""
    method: str
    _platt_params: tuple[float, float] | None = None
    _isotonic_x: np.ndarray | None = None
    _isotonic_y: np.ndarray | None = None

    def __post_init__(self) -> None:
        if self.method not in ("platt", "isotonic"):
            raise ValueError(f"Unknown calibration method {self.method!r}")

    def fit(self, raw_probability: pd.Series, outcome: pd.Series) -> ProbabilityCalibrator:
        """`outcome`: real 0/1, whether the home team actually won. Raises below
        MIN_FIT_SAMPLE=30 real games -- a real, enforced minimum, not a soft suggestion."""
        n = len(raw_probability)
        if n < MIN_FIT_SAMPLE:
            raise ValueError(
                f"Real calibration fit requested on n={n} real games -- below the real, "
                f"enforced minimum of {MIN_FIT_SAMPLE}. Never fit on an insufficient sample."
            )
        x = raw_probability.to_numpy(dtype=float)
        y = outcome.to_numpy(dtype=float)
        if self.method == "platt":
            self._platt_params = _fit_platt(x, y)
        else:
            self._isotonic_x, self._isotonic_y = _fit_isotonic(x, y)
        return self

    def predict(self, raw_probability: pd.Series) -> pd.Series:
        x = raw_probability.to_numpy(dtype=float)
        if self.method == "platt":
            if self._platt_params is None:
                raise RuntimeError("Real calibrator used before fit() -- call fit() first.")
            a, b = self._platt_params
            calibrated = _sigmoid(a * _logit(x) + b)
        else:
            if self._isotonic_x is None:
                raise RuntimeError("Real calibrator used before fit() -- call fit() first.")
            calibrated = np.interp(x, self._isotonic_x, self._isotonic_y)
        return pd.Series(calibrated, index=raw_probability.index)


def reliability_table(
    raw_probability: pd.Series, outcome: pd.Series,
    bins: list[float] | None = None,
) -> pd.DataFrame:
    """Real, binned predicted-probability-vs-observed-outcome table -- the same real diagnostic
    the original v35 audit's Step 12 built by hand, generalized here for reuse. Columns:
    bucket, n, mean_predicted, observed_rate."""
    if bins is None:
        bins = [0.0, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8, 1.01]
    df = pd.DataFrame({"raw": raw_probability.to_numpy(), "outcome": outcome.to_numpy()})
    df["bucket"] = pd.cut(df["raw"], bins=bins, right=False)
    rows = []
    for bucket, g in df.groupby("bucket", observed=True):
        rows.append({
            "bucket": str(bucket), "n": len(g),
            "mean_predicted": g["raw"].mean(), "observed_rate": g["outcome"].mean(),
        })
    return pd.DataFrame(rows)


def brier_score(predicted: pd.Series, outcome: pd.Series) -> float:
    p = predicted.clip(1e-6, 1 - 1e-6)
    y = outcome.astype(float)
    return float(((p - y) ** 2).mean())


def log_loss(predicted: pd.Series, outcome: pd.Series) -> float:
    p = predicted.clip(1e-6, 1 - 1e-6)
    y = outcome.astype(float)
    return float(-(y * p.apply(math.log) + (1 - y) * (1 - p).apply(math.log)).mean())
