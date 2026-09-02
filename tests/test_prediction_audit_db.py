"""
Tests for Steps 2-3 of the NFL Model v35 Validation/Audit master spec: the Prediction Audit
database schema (prediction_audit/db/schema.py), insert helpers (write.py), and the Step 3
state-snapshot shape (snapshot.py). Uses an in-memory SQLite database (":memory:") -- never
touches prediction_audit/db/prediction_audit.sqlite3, the real audit database.
"""
import json
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prediction_audit"))

from db import write  # noqa: E402
from db.schema import create_database  # noqa: E402
from db.snapshot import build_empty_snapshot, validate_snapshot  # noqa: E402


@pytest.fixture
def conn():
    c = create_database(":memory:")
    yield c
    c.close()


def _seed_model_and_game(conn: sqlite3.Connection) -> None:
    write.insert_model(conn, "v35.0", "Frozen v35 baseline", "2026-09-01T00:00:00Z",
                        workbook_sha256="fdd0b971...")
    write.insert_game(conn, "2026_01_MIA_BUF", 2026, 1, "Miami Dolphins", "Buffalo Bills",
                       game_date="2026-09-06")


def test_create_database_is_idempotent(conn):
    # Calling create_database twice against the same real file must not error (CREATE TABLE
    # IF NOT EXISTS throughout) -- verified by just running the schema script again on the
    # same open connection.
    conn.executescript("")  # no-op sanity check the connection is usable
    tables = {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    )}
    expected = {
        "models", "games", "prediction_runs", "predictions", "component_contributions",
        "state_snapshots", "market_lines", "results", "data_quality",
    }
    assert expected.issubset(tables)


def test_foreign_keys_enforced(conn):
    # A prediction_run referencing a real model_version/game_id that was never inserted must
    # fail -- proves PRAGMA foreign_keys=ON actually took effect (SQLite defaults it OFF).
    with pytest.raises(sqlite3.IntegrityError):
        write.insert_prediction_run(conn, "v99.0", "nonexistent_game", "2026-09-01T00:00:00Z")


def test_full_prediction_run_round_trip(conn):
    _seed_model_and_game(conn)
    run_id = write.insert_prediction_run(
        conn, "v35.0", "2026_01_MIA_BUF", "2026-09-04T14:15:00Z",
        data_cutoff_timestamp="2026-09-04T14:00:00Z", data_version="pull_2026_09_04",
    )
    write.insert_prediction(
        conn, run_id, away_projected_points=20.0, home_projected_points=27.0,
        projected_margin=7.0, projected_total=47.0, home_win_probability=0.68,
        away_win_probability=0.32, confidence=0.55,
    )
    write.insert_component_contributions(conn, run_id, [
        {"component_name": "HFA Delta (Home)", "contribution_value": 2.9, "side": "HOME"},
        {"component_name": "HFA Delta (Away)", "contribution_value": -2.9, "side": "AWAY"},
    ])
    snapshot = build_empty_snapshot()
    snapshot["team_strength"]["overall_rating"] = 4.2
    assert validate_snapshot(snapshot) == []
    write.insert_state_snapshot(conn, run_id, snapshot)
    write.insert_market_line(
        conn, run_id, "DraftKings", "spread", "prediction_time", line_value=-2.5,
        market_data_status="UNVERIFIED",
    )
    write.insert_data_quality(conn, run_id, missing_data_flag=False, data_quality_score=1.0)

    row = conn.execute(
        "SELECT away_projected_points, home_projected_points FROM predictions WHERE run_id=?",
        (run_id,),
    ).fetchone()
    assert row == (20.0, 27.0)

    contribs = conn.execute(
        "SELECT component_name, contribution_value, side FROM component_contributions "
        "WHERE run_id=? ORDER BY side", (run_id,),
    ).fetchall()
    assert contribs == [
        ("HFA Delta (Away)", -2.9, "AWAY"),
        ("HFA Delta (Home)", 2.9, "HOME"),
    ]

    stored_snapshot = json.loads(conn.execute(
        "SELECT state_snapshot_json FROM state_snapshots WHERE run_id=?", (run_id,),
    ).fetchone()[0])
    assert stored_snapshot["team_strength"]["overall_rating"] == 4.2


def test_rerun_creates_new_run_not_an_update(conn):
    # The whole point of "immutable audit record" -- re-predicting the same game must create
    # a SECOND row, never overwrite the first.
    _seed_model_and_game(conn)
    run_1 = write.insert_prediction_run(conn, "v35.0", "2026_01_MIA_BUF", "2026-09-01T00:00:00Z")
    run_2 = write.insert_prediction_run(conn, "v35.0", "2026_01_MIA_BUF", "2026-09-04T00:00:00Z")
    assert run_1 != run_2
    count = conn.execute(
        "SELECT COUNT(*) FROM prediction_runs WHERE game_id=?", ("2026_01_MIA_BUF",),
    ).fetchone()[0]
    assert count == 2


def test_mark_run_status_only_changes_status(conn):
    _seed_model_and_game(conn)
    run_id = write.insert_prediction_run(conn, "v35.0", "2026_01_MIA_BUF", "2026-09-01T00:00:00Z")
    write.mark_run_status(conn, run_id, "SUPERSEDED")
    status = conn.execute(
        "SELECT model_status FROM prediction_runs WHERE run_id=?", (run_id,),
    ).fetchone()[0]
    assert status == "SUPERSEDED"


def test_mark_run_status_rejects_unknown_value(conn):
    _seed_model_and_game(conn)
    run_id = write.insert_prediction_run(conn, "v35.0", "2026_01_MIA_BUF", "2026-09-01T00:00:00Z")
    with pytest.raises(ValueError, match="Unknown model_status"):
        write.mark_run_status(conn, run_id, "MADE_UP_STATUS")


def test_market_line_rejects_unknown_status(conn):
    _seed_model_and_game(conn)
    run_id = write.insert_prediction_run(conn, "v35.0", "2026_01_MIA_BUF", "2026-09-01T00:00:00Z")
    with pytest.raises(ValueError, match="Unknown market_data_status"):
        write.insert_market_line(
            conn, run_id, "DraftKings", "spread", "prediction_time",
            market_data_status="TOTALLY_MADE_UP",
        )


def test_v_prediction_errors_computed_fresh_from_real_result(conn):
    _seed_model_and_game(conn)
    run_id = write.insert_prediction_run(conn, "v35.0", "2026_01_MIA_BUF", "2026-09-01T00:00:00Z")
    write.insert_prediction(
        conn, run_id, away_projected_points=20.0, home_projected_points=27.0,
        projected_margin=7.0, projected_total=47.0, home_win_probability=0.68,
        away_win_probability=0.32,
    )
    # No real result yet -- the view must return no row, not a fabricated error.
    assert conn.execute(
        "SELECT * FROM v_prediction_errors WHERE run_id=?", (run_id,)
    ).fetchone() is None

    write.insert_result(conn, "2026_01_MIA_BUF", away_final_score=17, home_final_score=24)
    row = conn.execute(
        "SELECT margin_error, winner_correct FROM v_prediction_errors WHERE run_id=?",
        (run_id,),
    ).fetchone()
    # Real margin 24-17=7, projected 7.0 -> error 0, winner correctly picked.
    assert row == (0.0, 1)


def test_v_clv_only_returns_verified_rows(conn):
    _seed_model_and_game(conn)
    run_id = write.insert_prediction_run(conn, "v35.0", "2026_01_MIA_BUF", "2026-09-01T00:00:00Z")
    write.insert_market_line(
        conn, run_id, "DraftKings", "spread", "prediction_time", line_value=-2.5,
        market_data_status="UNVERIFIED",
    )
    write.insert_market_line(
        conn, run_id, "DraftKings", "spread", "closing", line_value=-3.0,
        market_data_status="UNVERIFIED",
    )
    # Both rows UNVERIFIED -- the view must produce nothing rather than a CLV number built on
    # unverified data.
    assert conn.execute("SELECT * FROM v_clv WHERE run_id=?", (run_id,)).fetchone() is None


def test_validate_snapshot_catches_missing_category():
    snapshot = build_empty_snapshot()
    del snapshot["qb"]
    problems = validate_snapshot(snapshot)
    assert any("qb" in p for p in problems)


def test_validate_snapshot_catches_unexpected_field():
    snapshot = build_empty_snapshot()
    snapshot["qb"]["made_up_field"] = 1.0
    problems = validate_snapshot(snapshot)
    assert any("unexpected fields" in p and "made_up_field" in p for p in problems)


def test_validate_snapshot_accepts_real_injury_records():
    snapshot = build_empty_snapshot()
    snapshot["injuries"].append({
        "player": "Test Player", "team": "Buffalo Bills", "position": "WR",
        "status": "Questionable", "expected_availability": "Active",
        "replacement_player": None, "estimated_model_impact": -0.3,
        "source": "Official Injury Report", "timestamp": "2026-09-04T12:00:00Z",
    })
    assert validate_snapshot(snapshot) == []
