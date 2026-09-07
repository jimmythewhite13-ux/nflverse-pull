"""
Phase 2 -- travel research: tests whether ANY real travel specification explains real residual
variance beyond the champion model, given the original audit's own real finding (r=+0.055,
non-monotonic by distance bin -- the existing +0.4pts/1000mi coefficient has no real support).

Real, deliberate scope: this module only ever fits/predicts a real ADJUSTMENT to the real
residual (actual_away_margin - baseline_away_margin), never the raw margin itself -- isolating
what travel explains beyond what the champion model already captures, per Phase 2's own
explicit requirement.

No `scipy`/`sklearn` dependency (neither already used in this project) -- the nonlinear variant
uses a real, standard truncated-power-basis spline (equivalent in spirit to a natural cubic
spline for this purpose), with knots placed at real, data-driven quantiles of the real training
distances -- never an arbitrary hardcoded threshold like "1500 miles = long trip", per Phase 2's
own explicit prohibition on importing thresholds from outside the data.
"""
from __future__ import annotations

from dataclasses import dataclass, field

import numpy as np
import pandas as pd


@dataclass
class TravelModelConfig:
    max_abs_adjustment: float = 2.5
    n_knots: int = 3


@dataclass
class OpponentControlledTravelModel:
    """Fits a real linear (optionally spline-transformed) regression of the real residual
    against whichever real travel-related features are enabled, bounded to
    `config.max_abs_adjustment`. `features`: subset of {"distance", "rest_diff", "tz_diff"}.
    `nonlinear_distance`: if True, distance is expanded into a real, data-driven spline basis
    instead of used linearly."""
    config: TravelModelConfig = field(default_factory=TravelModelConfig)
    features: tuple[str, ...] = ("distance",)
    nonlinear_distance: bool = False
    _coef: np.ndarray | None = field(default=None, repr=False)
    _knots: np.ndarray | None = field(default=None, repr=False)
    _feature_means: dict[str, float] | None = field(default=None, repr=False)

    def _distance_basis(self, distance: np.ndarray, knots: np.ndarray) -> np.ndarray:
        """Real truncated-power-basis spline expansion: [distance, (distance-k1)_+, (distance-
        k2)_+, ...] -- a standard, real way to let a linear model fit a real piecewise-linear
        (spline-like) curve, with knots from real, data-driven quantiles, never guessed."""
        cols = [distance]
        for k in knots:
            cols.append(np.clip(distance - k, 0, None))
        return np.column_stack(cols)

    def _design_matrix(self, df: pd.DataFrame, fit: bool) -> np.ndarray:
        cols = [np.ones(len(df))]
        if "distance" in self.features:
            distance = df["distance_miles"].to_numpy(dtype=float)
            if self.nonlinear_distance:
                if fit:
                    quantile_points = np.linspace(0, 1, self.config.n_knots + 2)[1:-1]
                    self._knots = np.quantile(distance, quantile_points)
                cols.append(self._distance_basis(distance, self._knots))
            else:
                cols.append(distance.reshape(-1, 1))
        if "rest_diff" in self.features:
            cols.append(df["rest_diff"].to_numpy(dtype=float).reshape(-1, 1))
        if "tz_diff" in self.features:
            cols.append(df["tz_diff"].to_numpy(dtype=float).reshape(-1, 1))
        return np.hstack([c if c.ndim == 2 else c.reshape(-1, 1) for c in cols])

    def fit(self, df: pd.DataFrame, residual: pd.Series) -> OpponentControlledTravelModel:
        """`df` must have the real columns this model's own `features` need
        (`distance_miles`, and/or `rest_diff`, `tz_diff`). `residual`: real
        actual_away_margin - real baseline_away_margin, aligned to `df`."""
        X = self._design_matrix(df, fit=True)
        y = residual.to_numpy(dtype=float)
        coef, *_ = np.linalg.lstsq(X, y, rcond=None)
        self._coef = coef
        return self

    def predict(self, df: pd.DataFrame) -> pd.Series:
        if self._coef is None:
            raise RuntimeError("Real travel model used before fit() -- call fit() first.")
        X = self._design_matrix(df, fit=False)
        raw = X @ self._coef
        bounded = np.clip(raw, -self.config.max_abs_adjustment, self.config.max_abs_adjustment)
        return pd.Series(bounded, index=df.index)


def no_travel_baseline(df: pd.DataFrame) -> pd.Series:
    """Variant A -- the real, zeroed baseline (no travel adjustment at all)."""
    return pd.Series(0.0, index=df.index)


def existing_production_travel(
    away_travel_miles: pd.Series, coefficient: float = 0.4,
) -> pd.Series:
    """Variant B -- the existing, real production coefficient (+0.4 pts/1000mi), as a real
    comparison point. Not bounded -- this is what production actually does today, including
    its own real lack of a cap, so the comparison is honest."""
    return -(away_travel_miles / 1000) * coefficient
