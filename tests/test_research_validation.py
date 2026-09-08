"""Tests for prediction_audit/research/validation.py -- the shared leakage/metrics framework
Phases 2-6 all depend on."""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.research.validation import (  # noqa: E402
    challenger_delta,
    evaluate_predictions,
    leakage_check,
)


def test_leakage_check_passes_for_real_temporal_split():
    train = pd.DataFrame({"kickoff": ["2023-01-01", "2023-06-01"]})
    test = pd.DataFrame({"kickoff": ["2024-01-01"]})
    assert leakage_check(train, test, "kickoff") is True


def test_leakage_check_fails_for_overlapping_dates():
    train = pd.DataFrame({"kickoff": ["2023-01-01", "2024-06-01"]})
    test = pd.DataFrame({"kickoff": ["2024-01-01"]})
    assert leakage_check(train, test, "kickoff") is False


def test_leakage_check_false_for_empty_frames():
    empty = pd.DataFrame({"kickoff": []})
    non_empty = pd.DataFrame({"kickoff": ["2024-01-01"]})
    assert leakage_check(empty, non_empty, "kickoff") is False
    assert leakage_check(non_empty, empty, "kickoff") is False


def test_evaluate_predictions_perfect_predictions():
    margin = pd.Series([7.0, -3.0, 10.0])
    actual = pd.Series([7.0, -3.0, 10.0])
    prob = pd.Series([0.9, 0.2, 0.95])
    won = pd.Series([1, 0, 1])
    result = evaluate_predictions(margin, actual, prob, won)
    assert result.n == 3
    assert result.mae == pytest.approx(0.0)
    assert result.rmse == pytest.approx(0.0)
    assert result.winner_accuracy == pytest.approx(1.0)


def test_evaluate_predictions_rejects_empty_input():
    empty = pd.Series([], dtype=float)
    with pytest.raises(ValueError, match="0 real games"):
        evaluate_predictions(empty, empty, empty, empty)


def test_challenger_delta_flags_real_improvement():
    champion = evaluate_predictions(
        pd.Series([5.0, -5.0]), pd.Series([10.0, -10.0]),
        pd.Series([0.6, 0.4]), pd.Series([1, 0]),
    )
    challenger = evaluate_predictions(
        pd.Series([9.0, -9.0]), pd.Series([10.0, -10.0]),
        pd.Series([0.9, 0.1]), pd.Series([1, 0]),
    )
    delta = challenger_delta(champion, challenger)
    assert delta.mae_delta < 0
    assert delta.brier_delta < 0
    assert delta.improved is True


def test_challenger_delta_does_not_claim_improvement_on_worse_mae():
    champion = evaluate_predictions(
        pd.Series([9.0, -9.0]), pd.Series([10.0, -10.0]),
        pd.Series([0.6, 0.4]), pd.Series([1, 0]),
    )
    challenger = evaluate_predictions(
        pd.Series([5.0, -5.0]), pd.Series([10.0, -10.0]),
        pd.Series([0.6, 0.4]), pd.Series([1, 0]),
    )
    delta = challenger_delta(champion, challenger)
    assert delta.mae_delta > 0
    assert delta.improved is False
