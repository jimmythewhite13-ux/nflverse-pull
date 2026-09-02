"""
Step 3 of the NFL Model v35 Validation/Audit master spec: the full model-state snapshot
schema. Defines exactly what "what did the model know at prediction time" means structurally
-- not just the final prediction, but every real category of input that fed it, matching the
spec's own field list category-for-category.

This module defines SHAPE, not data: SNAPSHOT_CATEGORIES documents every real field this
project's own tabs already compute (or explicitly does not have -- see the honesty note
below) per category; build_empty_snapshot() returns a real dict with every field present and
set to None, ready for a caller to fill in with real values before calling
write.insert_state_snapshot(); validate_snapshot() checks a filled-in snapshot against this
same shape so a caller can't silently drop a whole category.

Honesty note, per the spec's own "do not invent data" principle: several fields the spec asks
for do not have a real source anywhere in this project as of v35 (marked NOT_AVAILABLE_V35
below, with the reason). A caller populating a real historical snapshot must leave those as
None, not a guessed value -- the whole point of this schema existing is to make a genuinely
missing input visible and queryable, not to paper over it.
"""
from __future__ import annotations

# Team Strength -- all real, already computed on Team Ratings / YoY Baseline Engine.
TEAM_STRENGTH_FIELDS = [
    "overall_rating", "offensive_rating", "defensive_rating", "home_rating", "away_rating",
    "recent_form", "strength_of_schedule",
]

# Quarterback -- real (QB Index / QB Environment Model), except injury/backup fields which
# ARE real (Availability Index / Replacement Value) but keyed by TEAM in this project, not
# stored as a per-QB "expected_availability" field the way the spec phrases it -- caller
# derives per-QB availability from that team-level real data at snapshot time.
QB_FIELDS = [
    "qb_identity", "qb_rating", "epa", "success_rate", "completion_percentage",
    "yards_per_attempt", "pressure_performance", "injury_status", "backup_qb",
    "expected_qb_availability",
]

OL_FIELDS = [
    "pass_protection", "pressure_allowed", "sack_rate", "run_blocking",
    "starter_availability", "injury_status",
]

RB_FIELDS = ["efficiency", "workload", "explosive_runs", "receiving_contribution", "availability"]

WR_TE_FIELDS = ["receiving_efficiency", "target_share", "explosive_rate", "matchup", "availability"]

DEFENSE_FIELDS = [
    "epa", "success_rate", "pressure", "sacks", "pass_defense", "run_defense",
    "explosive_plays_allowed", "coverage", "secondary_availability",
]

MATCHUP_FIELDS = [
    "ol_vs_pass_rush", "qb_vs_pass_defense", "wr_te_vs_secondary", "run_off_vs_run_def",
    "explosive_matchup", "game_script_effects",
]

# Environment -- all real EXCEPT international_travel, which this project has never modeled
# (no real international-game handling anywhere in Team-Specific HFA / the Game Environment
# Upgrades wiring) -- marked below, not silently included as if it were real.
ENVIRONMENT_FIELDS = [
    "hfa", "rest", "days_since_prior_game", "consecutive_road_games", "travel_distance",
    "timezone_difference", "west_to_east_travel", "international_travel", "temperature",
    "wind", "precipitation", "snow", "humidity", "surface",
]

REGRESSION_FIELDS = [
    "turnover_regression", "interception_regression", "fumble_regression",
    "red_zone_regression", "explosive_play_regression",
]

# Injuries -- a real LIST of real per-player injury records, not a fixed set of scalar
# fields (unlike every other category here) -- see build_empty_snapshot()'s own handling.
INJURY_RECORD_FIELDS = [
    "player", "team", "position", "status", "expected_availability", "replacement_player",
    "estimated_model_impact", "source", "timestamp",
]

SNAPSHOT_CATEGORIES: dict[str, list[str]] = {
    "team_strength": TEAM_STRENGTH_FIELDS,
    "qb": QB_FIELDS,
    "ol": OL_FIELDS,
    "rb": RB_FIELDS,
    "wr_te": WR_TE_FIELDS,
    "defense": DEFENSE_FIELDS,
    "matchups": MATCHUP_FIELDS,
    "environment": ENVIRONMENT_FIELDS,
    "regression": REGRESSION_FIELDS,
}

# Fields the spec asks for that this project has no real source for as of v35. Populating
# these with anything other than None in a real snapshot would violate "do not invent data".
NOT_AVAILABLE_V35 = {
    "environment.international_travel": (
        "No real international-game handling anywhere in Team-Specific HFA or the Game "
        "Environment Upgrades wiring -- every real game modeled so far has been a domestic "
        "NFL stadium."
    ),
    "qb.pressure_performance": (
        "QB Environment Model tracks real pressure-rate CONTEXT (Effective QB Rating), but "
        "not a standalone per-QB 'pressure performance' scalar distinct from that -- a real "
        "caller should populate this from the same source and note the overlap rather than "
        "treat it as an independent field."
    ),
}


def build_empty_snapshot() -> dict:
    """Real dict, every category/field present, every value None -- a caller fills in real
    values (leaving NOT_AVAILABLE_V35 fields as None) before write.insert_state_snapshot()."""
    return {
        category: {field: None for field in fields}
        for category, fields in SNAPSHOT_CATEGORIES.items()
    } | {"injuries": []}  # a real list of per-player dicts, each shaped like INJURY_RECORD_FIELDS


def validate_snapshot(snapshot: dict) -> list[str]:
    """Pure function, no I/O. Returns a list of real problems found (empty list = valid) --
    every expected category present, no unexpected top-level keys, 'injuries' is a list of
    dicts each covering INJURY_RECORD_FIELDS. Does NOT require every leaf field to be
    non-None (a genuinely missing real value is valid; a missing CATEGORY or a field with an
    unexpected name is not)."""
    problems = []
    expected_top_keys = set(SNAPSHOT_CATEGORIES) | {"injuries"}
    actual_top_keys = set(snapshot)
    missing = expected_top_keys - actual_top_keys
    extra = actual_top_keys - expected_top_keys
    if missing:
        problems.append(f"Missing top-level categories: {sorted(missing)}")
    if extra:
        problems.append(f"Unexpected top-level categories: {sorted(extra)}")

    for category, fields in SNAPSHOT_CATEGORIES.items():
        if category not in snapshot:
            continue
        actual_fields = set(snapshot[category])
        expected_fields = set(fields)
        f_missing = expected_fields - actual_fields
        f_extra = actual_fields - expected_fields
        if f_missing:
            problems.append(f"{category}: missing fields {sorted(f_missing)}")
        if f_extra:
            problems.append(f"{category}: unexpected fields {sorted(f_extra)}")

    if "injuries" in snapshot:
        if not isinstance(snapshot["injuries"], list):
            problems.append("injuries: must be a list")
        else:
            for i, record in enumerate(snapshot["injuries"]):
                if not isinstance(record, dict):
                    problems.append(f"injuries[{i}]: must be a dict")
                    continue
                rec_missing = set(INJURY_RECORD_FIELDS) - set(record)
                rec_extra = set(record) - set(INJURY_RECORD_FIELDS)
                if rec_missing:
                    problems.append(f"injuries[{i}]: missing fields {sorted(rec_missing)}")
                if rec_extra:
                    problems.append(f"injuries[{i}]: unexpected fields {sorted(rec_extra)}")

    return problems
