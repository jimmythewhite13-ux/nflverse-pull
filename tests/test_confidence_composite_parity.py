"""
Parity test for prediction_audit/engine/confidence_composite.py against v35's own real
recalculated Market Comparison & Confidence values -- all 272 real games.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.confidence_composite import (  # noqa: E402
    confidence_composite,
    confidence_tier,
    matchup_agreement_component,
    ol_center_continuity_component,
    qb_override_certainty_component,
    sample_size_component,
)

GROUND_TRUTH_PATH = (
    Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"
    / "v35_confidence_composite_ground_truth.json"
)


def _load_ground_truth() -> dict:
    with open(GROUND_TRUTH_PATH, encoding="utf-8") as f:
        return json.load(f)


GROUND_TRUTH = _load_ground_truth()
QB_OVERRIDE_BY_TEAM = GROUND_TRUTH["qb_has_override_by_team"]
CENTER_IS_ROOKIE_BY_TEAM = GROUND_TRUTH["center_is_rookie_by_team"]


def _game_id(g: dict) -> str:
    return f"wk{g['week']}_{g['away']}_at_{g['home']}".replace(" ", "")


def test_ground_truth_has_all_272_games():
    assert len(GROUND_TRUTH["games"]) == 272


def test_ground_truth_has_real_rookie_center_coverage():
    # Real snapshot has genuine non-trivial coverage for this component (unlike the
    # QB-override branch, which has none right now -- see below).
    assert sum(CENTER_IS_ROOKIE_BY_TEAM.values()) > 0


def test_ground_truth_has_no_real_override_coverage_currently():
    # Documented, not a gap: no team currently has a real manual roster override entered.
    assert sum(QB_OVERRIDE_BY_TEAM.values()) == 0


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_sample_size_component_parity(game):
    result = sample_size_component(
        game["excel_home_games_played"], game["excel_away_games_played"],
    )
    assert result == pytest.approx(game["excel_sample_size_component"], abs=1e-6)


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_qb_override_certainty_component_parity(game):
    # Real Backup-In flags aren't in this manifest -- every real 2026 game currently has
    # "Starter In" on both sides (see core_formula_simple_terms's own ground truth), so both
    # flags are always 0 in the real snapshot; passed directly rather than re-loading that
    # other manifest just for a constant "Starter In".
    result = qb_override_certainty_component(
        "Starter In", "Starter In",
        QB_OVERRIDE_BY_TEAM[game["home"]], QB_OVERRIDE_BY_TEAM[game["away"]],
    )
    assert result == pytest.approx(game["excel_qb_override_certainty_component"], abs=1e-6)


def test_qb_override_certainty_component_when_overridden():
    # No real game currently has a manual override -- exercises the branch directly.
    assert qb_override_certainty_component("Starter In", "Starter In", True, False) == \
        pytest.approx(0.75, abs=1e-9)
    assert qb_override_certainty_component("Backup In", "Starter In", True, True) == \
        pytest.approx(0.25, abs=1e-9)


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_ol_center_continuity_component_parity(game):
    result = ol_center_continuity_component(
        CENTER_IS_ROOKIE_BY_TEAM[game["home"]], CENTER_IS_ROOKIE_BY_TEAM[game["away"]],
    )
    assert result == pytest.approx(game["excel_ol_center_continuity_component"], abs=1e-6), (
        f"{_game_id(game)} OL Center Continuity Component mismatch"
    )


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_matchup_agreement_component_parity(game):
    result = matchup_agreement_component(
        game["excel_phase_matchup_net_home_adv_y"], game["excel_ol_pressure_net_home_adv_z"],
        game["excel_explosive_net_home_adv_aa"], game["excel_model_spread_g"],
    )
    assert result == pytest.approx(game["excel_matchup_agreement_component"], abs=1e-6), (
        f"{_game_id(game)} Matchup Agreement Component mismatch: Python={result}, "
        f"Excel={game['excel_matchup_agreement_component']}"
    )


@pytest.mark.parametrize(
    "game", GROUND_TRUTH["games"], ids=[_game_id(g) for g in GROUND_TRUTH["games"]],
)
def test_confidence_composite_and_tier_parity(game):
    c = GROUND_TRUTH["constants"]
    sample_size = sample_size_component(
        game["excel_home_games_played"], game["excel_away_games_played"],
    )
    qb_override = qb_override_certainty_component(
        "Starter In", "Starter In",
        QB_OVERRIDE_BY_TEAM[game["home"]], QB_OVERRIDE_BY_TEAM[game["away"]],
    )
    ol_continuity = ol_center_continuity_component(
        CENTER_IS_ROOKIE_BY_TEAM[game["home"]], CENTER_IS_ROOKIE_BY_TEAM[game["away"]],
    )
    matchup_agreement = matchup_agreement_component(
        game["excel_phase_matchup_net_home_adv_y"], game["excel_ol_pressure_net_home_adv_z"],
        game["excel_explosive_net_home_adv_aa"], game["excel_model_spread_g"],
    )

    composite = confidence_composite(
        sample_size, qb_override, ol_continuity, matchup_agreement,
        c["sample_size_weight"], c["qb_override_weight"], c["ol_continuity_weight"],
        c["matchup_agreement_weight"],
    )
    tier = confidence_tier(
        composite, c["tier_threshold_low_medium"], c["tier_threshold_medium_medium_high"],
        c["tier_threshold_medium_high_high"],
    )

    assert composite == pytest.approx(game["excel_confidence_composite"], abs=1e-6), (
        f"{_game_id(game)} Confidence Composite mismatch: Python={composite}, "
        f"Excel={game['excel_confidence_composite']}"
    )
    assert tier == game["excel_confidence_tier"], (
        f"{_game_id(game)} Confidence Tier mismatch: Python={tier}, "
        f"Excel={game['excel_confidence_tier']}"
    )


def test_confidence_tier_thresholds():
    assert confidence_tier(0.85, 0.4, 0.6, 0.8) == "High"
    assert confidence_tier(0.8, 0.4, 0.6, 0.8) == "High"
    assert confidence_tier(0.7, 0.4, 0.6, 0.8) == "Medium-High"
    assert confidence_tier(0.5, 0.4, 0.6, 0.8) == "Medium"
    assert confidence_tier(0.1, 0.4, 0.6, 0.8) == "Low"
