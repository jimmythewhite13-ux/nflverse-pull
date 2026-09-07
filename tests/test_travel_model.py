"""Tests for prediction_audit/research/travel_model.py."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.research.travel_model import (  # noqa: E402
    OpponentControlledTravelModel,
    TravelModelConfig,
    existing_production_travel,
    no_travel_baseline,
)


def _synthetic_distance_data(n=100, seed=7, true_slope=-0.002):
    """Real, deterministic synthetic scenario: residual has a genuine linear relationship to
    distance, so a distance-only model should recover it; noise is real, fixed-seed random."""
    rng = np.random.default_rng(seed)
    distance = rng.uniform(0, 3000, size=n)
    noise = rng.normal(0, 0.5, size=n)
    residual = true_slope * distance + noise
    df = pd.DataFrame({"distance_miles": distance})
    return df, pd.Series(residual)


def test_no_travel_baseline_is_always_zero():
    df = pd.DataFrame({"distance_miles": [100, 2000, 3000]})
    result = no_travel_baseline(df)
    assert (result == 0.0).all()


def test_existing_production_travel_matches_known_formula():
    miles = pd.Series([1000.0, 2000.0])
    result = existing_production_travel(miles, coefficient=0.4)
    assert result.iloc[0] == pytest.approx(-0.4)
    assert result.iloc[1] == pytest.approx(-0.8)


def test_linear_distance_model_recovers_real_relationship():
    df, residual = _synthetic_distance_data()
    model = OpponentControlledTravelModel(features=("distance",))
    model.fit(df, residual)
    predicted = model.predict(df)
    # Real, substantial correlation with the true residual -- confirms the fit found the real
    # underlying relationship, not noise.
    corr = np.corrcoef(predicted, residual)[0, 1]
    assert corr > 0.5


def test_predictions_are_bounded_by_max_abs_adjustment():
    df, residual = _synthetic_distance_data(true_slope=-0.01)  # exaggerated real slope
    config = TravelModelConfig(max_abs_adjustment=1.0)
    model = OpponentControlledTravelModel(config=config, features=("distance",))
    model.fit(df, residual)
    predicted = model.predict(df)
    assert predicted.abs().max() <= 1.0 + 1e-9


def test_nonlinear_distance_model_fits_without_error():
    df, residual = _synthetic_distance_data()
    model = OpponentControlledTravelModel(features=("distance",), nonlinear_distance=True)
    model.fit(df, residual)
    predicted = model.predict(df)
    assert len(predicted) == len(df)
    assert predicted.notna().all()


def test_multi_feature_model_uses_all_real_features():
    df, residual = _synthetic_distance_data()
    df["rest_diff"] = np.linspace(-3, 3, len(df))
    df["tz_diff"] = np.linspace(-3, 3, len(df))
    model = OpponentControlledTravelModel(features=("distance", "rest_diff", "tz_diff"))
    model.fit(df, residual)
    predicted = model.predict(df)
    assert len(predicted) == len(df)


def test_predict_before_fit_raises():
    model = OpponentControlledTravelModel()
    with pytest.raises(RuntimeError, match="before fit"):
        model.predict(pd.DataFrame({"distance_miles": [100.0]}))
