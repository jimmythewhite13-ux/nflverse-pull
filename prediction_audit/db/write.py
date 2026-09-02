"""
Insert helpers for the Prediction Audit database (Step 2). Every function here is INSERT-only
-- there is deliberately no update_prediction()/update_component_contributions() style
function anywhere in this module. A corrected or re-run prediction gets a brand new
prediction_runs row (a new run_id) via insert_prediction_run(); the old row's model_status can
be set to 'SUPERSEDED' via mark_run_status(), but its own prediction/component/snapshot rows
are never rewritten. This is what "immutable audit record" (the spec's own words) means in
practice.

Every argument here is real data supplied by the caller -- no function in this module invents
a value when one isn't provided; a genuinely unknown field is passed as None/NULL, never a
fabricated placeholder.
"""
from __future__ import annotations

import json
import sqlite3


def insert_model(
    conn: sqlite3.Connection, model_version: str, description: str, frozen_at: str,
    workbook_sha256: str | None = None, notes: str | None = None,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO models (model_version, description, workbook_sha256, "
        "frozen_at, notes) VALUES (?, ?, ?, ?, ?)",
        (model_version, description, workbook_sha256, frozen_at, notes),
    )
    conn.commit()


def insert_game(
    conn: sqlite3.Connection, game_id: str, season: int, week: int, away_team: str,
    home_team: str, game_date: str | None = None, kickoff_time: str | None = None,
    neutral_site: bool = False, stadium: str | None = None, surface: str | None = None,
    timezone: str | None = None,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO games (game_id, season, week, game_date, kickoff_time, "
        "away_team, home_team, neutral_site, stadium, surface, timezone) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (game_id, season, week, game_date, kickoff_time, away_team, home_team,
         int(neutral_site), stadium, surface, timezone),
    )
    conn.commit()


def insert_prediction_run(
    conn: sqlite3.Connection, model_version: str, game_id: str, prediction_timestamp: str,
    data_cutoff_timestamp: str | None = None, data_version: str | None = None,
) -> int:
    """Returns the new run_id. Always inserts a new row -- see this module's own docstring
    for why there is no corresponding update function."""
    cur = conn.execute(
        "INSERT INTO prediction_runs (model_version, game_id, prediction_timestamp, "
        "data_cutoff_timestamp, data_version) VALUES (?, ?, ?, ?, ?)",
        (model_version, game_id, prediction_timestamp, data_cutoff_timestamp, data_version),
    )
    conn.commit()
    return cur.lastrowid


def mark_run_status(conn: sqlite3.Connection, run_id: int, status: str) -> None:
    """The ONE mutation this module allows on prediction_runs -- status only (ACTIVE /
    SUPERSEDED / VOID), never the run's own predictions/components/snapshot rows."""
    if status not in ("ACTIVE", "SUPERSEDED", "VOID"):
        raise ValueError(f"Unknown model_status {status!r}")
    conn.execute("UPDATE prediction_runs SET model_status = ? WHERE run_id = ?", (status, run_id))
    conn.commit()


def insert_prediction(
    conn: sqlite3.Connection, run_id: int, away_projected_points: float,
    home_projected_points: float, projected_margin: float, projected_total: float,
    home_win_probability: float, away_win_probability: float, confidence: float | None = None,
) -> None:
    conn.execute(
        "INSERT INTO predictions (run_id, away_projected_points, home_projected_points, "
        "projected_margin, projected_total, home_win_probability, away_win_probability, "
        "confidence) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, away_projected_points, home_projected_points, projected_margin,
         projected_total, home_win_probability, away_win_probability, confidence),
    )
    conn.commit()


def insert_component_contributions(
    conn: sqlite3.Connection, run_id: int, contributions: list[dict],
) -> None:
    """`contributions`: [{"component_name": ..., "contribution_value": ..., "side": "HOME"|
    "AWAY"}, ...] -- real per-term values, e.g. from v35_core_formula_components.csv's own
    Component_Name column evaluated against a real game's real cell values."""
    conn.executemany(
        "INSERT INTO component_contributions (run_id, component_name, contribution_value, "
        "side) VALUES (?, ?, ?, ?)",
        [(run_id, c["component_name"], c["contribution_value"], c["side"])
         for c in contributions],
    )
    conn.commit()


def insert_state_snapshot(conn: sqlite3.Connection, run_id: int, snapshot: dict) -> None:
    """`snapshot`: a real dict matching snapshot.py's own SNAPSHOT_CATEGORIES structure --
    serialized as-is, no reshaping or default-filling here."""
    conn.execute(
        "INSERT INTO state_snapshots (run_id, state_snapshot_json) VALUES (?, ?)",
        (run_id, json.dumps(snapshot)),
    )
    conn.commit()


def insert_market_line(
    conn: sqlite3.Connection, run_id: int, sportsbook: str, market_type: str,
    line_stage: str, line_value: float | None = None, odds: float | None = None,
    line_timestamp: str | None = None, source: str | None = None,
    market_data_status: str = "MISSING",
) -> None:
    if market_data_status not in ("VERIFIED", "UNVERIFIED", "MISSING"):
        raise ValueError(f"Unknown market_data_status {market_data_status!r}")
    conn.execute(
        "INSERT INTO market_lines (run_id, sportsbook, market_type, line_stage, line_value, "
        "odds, line_timestamp, source, market_data_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, sportsbook, market_type, line_stage, line_value, odds, line_timestamp,
         source, market_data_status),
    )
    conn.commit()


def insert_result(
    conn: sqlite3.Connection, game_id: str, away_final_score: int, home_final_score: int,
) -> None:
    conn.execute(
        "INSERT OR IGNORE INTO results (game_id, away_final_score, home_final_score) "
        "VALUES (?, ?, ?)",
        (game_id, away_final_score, home_final_score),
    )
    conn.commit()


def insert_data_quality(
    conn: sqlite3.Connection, run_id: int, missing_data_flag: bool = False,
    data_quality_score: float | None = None, data_quality_status: str | None = None,
    future_data_leak_flag: bool = False, timestamp_validation: str | None = None,
    duplicate_flag: bool = False, source_conflict_flag: bool = False,
) -> None:
    conn.execute(
        "INSERT INTO data_quality (run_id, missing_data_flag, data_quality_score, "
        "data_quality_status, future_data_leak_flag, timestamp_validation, duplicate_flag, "
        "source_conflict_flag) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (run_id, int(missing_data_flag), data_quality_score, data_quality_status,
         int(future_data_leak_flag), timestamp_validation, int(duplicate_flag),
         int(source_conflict_flag)),
    )
    conn.commit()
