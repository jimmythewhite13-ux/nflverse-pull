"""Tests for prediction_audit/research/probability_calibration.py."""
import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.research.probability_calibration import (  # noqa: E402
    MIN_FIT_SAMPLE,
    ProbabilityCalibrator,
    brier_score,
    log_loss,
    reliability_table,
)


def _overconfident_synthetic_data(n=800, seed=42):
    """Real, deterministic synthetic scenario matching the audit's own finding: raw
    probabilities are systematically overconfident in the 50-70% band. Built from a fixed
    real random seed (not np.random with no seed -- reproducible test data), matching a known
    true win rate that's less extreme than the raw probability claims."""
    rng = np.random.default_rng(seed)
    raw = rng.uniform(0.5, 0.9, size=n)
    true_rate = 0.5 + (raw - 0.5) * 0.5  # true rate compresses toward 0.5 -- real overconfidence
    outcome = (rng.uniform(size=n) < true_rate).astype(int)
    return pd.Series(raw), pd.Series(outcome)


def test_platt_calibration_reduces_brier_on_overconfident_data():
    raw, outcome = _overconfident_synthetic_data()
    train_raw, train_out = raw.iloc[:150], outcome.iloc[:150]
    test_raw, test_out = raw.iloc[150:], outcome.iloc[150:]

    calibrator = ProbabilityCalibrator(method="platt").fit(train_raw, train_out)
    calibrated_test = calibrator.predict(test_raw)

    raw_brier = brier_score(test_raw, test_out)
    calibrated_brier = brier_score(calibrated_test, test_out)
    assert calibrated_brier < raw_brier


def test_isotonic_calibration_reduces_brier_on_overconfident_data():
    raw, outcome = _overconfident_synthetic_data()
    train_raw, train_out = raw.iloc[:600], outcome.iloc[:600]
    test_raw, test_out = raw.iloc[600:], outcome.iloc[600:]

    calibrator = ProbabilityCalibrator(method="isotonic").fit(train_raw, train_out)
    calibrated_test = calibrator.predict(test_raw)

    raw_brier = brier_score(test_raw, test_out)
    calibrated_brier = brier_score(calibrated_test, test_out)
    assert calibrated_brier < raw_brier


def test_isotonic_fit_is_monotonic():
    raw, outcome = _overconfident_synthetic_data()
    calibrator = ProbabilityCalibrator(method="isotonic").fit(raw, outcome)
    xs = np.linspace(0.5, 0.9, 20)
    ys = calibrator.predict(pd.Series(xs)).to_numpy()
    assert all(ys[i] <= ys[i + 1] + 1e-9 for i in range(len(ys) - 1))


def test_fit_rejects_sample_below_minimum():
    raw = pd.Series([0.6] * (MIN_FIT_SAMPLE - 1))
    outcome = pd.Series([1] * (MIN_FIT_SAMPLE - 1))
    with pytest.raises(ValueError, match="below the real, enforced minimum"):
        ProbabilityCalibrator(method="platt").fit(raw, outcome)


def test_predict_before_fit_raises():
    calibrator = ProbabilityCalibrator(method="platt")
    with pytest.raises(RuntimeError, match="before fit"):
        calibrator.predict(pd.Series([0.5, 0.6]))


def test_unknown_method_rejected():
    with pytest.raises(ValueError, match="Unknown calibration method"):
        ProbabilityCalibrator(method="made_up")


def test_reliability_table_real_bucket_counts():
    raw = pd.Series([0.45, 0.52, 0.58, 0.62, 0.71, 0.85])
    outcome = pd.Series([0, 1, 0, 1, 1, 1])
    table = reliability_table(raw, outcome)
    assert table["n"].sum() == 6
    # Every bucket's real mean_predicted must fall within [0, 1].
    assert table["mean_predicted"].between(0, 1).all()


def test_brier_score_known_value():
    predicted = pd.Series([1.0, 0.0])
    outcome = pd.Series([1, 0])
    assert brier_score(predicted, outcome) == pytest.approx(0.0, abs=1e-5)


def test_log_loss_known_value():
    predicted = pd.Series([0.5, 0.5])
    outcome = pd.Series([1, 0])
    # log_loss of a real, uninformative 50% prediction = -log(0.5) = ln(2).
    assert log_loss(predicted, outcome) == pytest.approx(np.log(2), abs=1e-4)
