"""
Tests for prediction_audit/historical/stadium_locations.py -- verified against v35's own real
ground-truth manifests (already extracted from the frozen workbook), not just spot-checked.
"""
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.historical.stadium_locations import (  # noqa: E402
    STADIUM_COORDS,
    TEAM_UTC_OFFSET,
    haversine_miles,
    resolve_game_venue_team,
    resolve_travel_direction_offsets,
    resolve_travel_effect_miles,
)

MANIFESTS = Path(__file__).resolve().parent.parent / "prediction_audit" / "manifests"


def _load(name: str) -> dict:
    with open(MANIFESTS / name, encoding="utf-8") as f:
        return json.load(f)


TRAVEL_MILES_GROUND_TRUTH = _load("v35_hfa_delta_travel_fatigue_ground_truth.json")
TRAVEL_DIRECTION_GROUND_TRUTH = _load("v35_travel_direction_ground_truth.json")


def test_all_32_teams_have_stadium_coords():
    assert len(STADIUM_COORDS) == 32


def test_all_32_teams_have_utc_offsets():
    assert len(TEAM_UTC_OFFSET) == 32


@pytest.mark.parametrize(
    "game", TRAVEL_MILES_GROUND_TRUTH["games"],
    ids=[f"wk{g['week']}_{g['away']}@{g['home']}" for g in TRAVEL_MILES_GROUND_TRUTH["games"]],
)
def test_resolve_travel_effect_miles_matches_real_v35_ground_truth(game):
    """Real haversine distance from these individually-sourced coordinates reproduces v35's
    own real away_travel_miles for every one of a real full season's 272 games -- confirms
    both the coordinates and that v35's own formula is plain great-circle distance."""
    computed = resolve_travel_effect_miles(game["away"], game["home"])
    assert computed == pytest.approx(game["away_travel_miles"], abs=0.5), (
        f"{game['away']}@{game['home']}: real={game['away_travel_miles']}, "
        f"computed={computed}"
    )


@pytest.mark.parametrize(
    "game", TRAVEL_DIRECTION_GROUND_TRUTH["games"],
    ids=[
        f"wk{g['week']}_{g['away']}@{g['home']}" for g in TRAVEL_DIRECTION_GROUND_TRUTH["games"]
    ],
)
def test_resolve_travel_direction_offsets_matches_real_v35_ground_truth(game):
    home_offset, away_offset = resolve_travel_direction_offsets(game["home"], game["away"])
    assert home_offset == game["home_utc_offset"]
    assert away_offset == game["away_utc_offset"]


def test_haversine_miles_zero_for_same_point():
    assert haversine_miles((40.0, -75.0), (40.0, -75.0)) == pytest.approx(0.0, abs=1e-9)


def test_haversine_miles_known_short_hop():
    # New York Giants and New York Jets share MetLife Stadium -- real, exact 0 distance.
    d = haversine_miles(STADIUM_COORDS["New York Giants"], STADIUM_COORDS["New York Jets"])
    assert d == pytest.approx(0.0, abs=1e-9)


def test_resolve_game_venue_team_defaults_to_home_for_no_row():
    assert resolve_game_venue_team(None, "Miami Dolphins") == "Miami Dolphins"


def test_resolve_game_venue_team_verifies_neutral_site_against_real_alias():
    row = {"location": "Neutral", "stadium": "Acrisure Stadium"}
    assert resolve_game_venue_team(row, "Pittsburgh Steelers") == "Pittsburgh Steelers"


def test_resolve_game_venue_team_handles_real_shared_building_alias():
    # A real 2025 case: MetLife Stadium aliases to "New York Jets" in the lookup table, but a
    # real Neutral game hosted by the Giants at the same real building must still resolve
    # (coordinate equality, not name equality).
    row = {"location": "Neutral", "stadium": "MetLife Stadium"}
    assert resolve_game_venue_team(row, "New York Giants") == "New York Giants"


def test_resolve_game_venue_team_raises_for_unresolved_neutral_site():
    # A real true international venue (e.g. Wembley Stadium) this table deliberately does not
    # cover (out of the composer's real reachable season range) -- must raise, never guess.
    row = {"location": "Neutral", "stadium": "Wembley Stadium"}
    with pytest.raises(ValueError, match="unresolved real venue"):
        resolve_game_venue_team(row, "Jacksonville Jaguars")
