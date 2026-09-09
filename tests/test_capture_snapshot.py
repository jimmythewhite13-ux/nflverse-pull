"""
Real test for `capture_snapshot()` -- proves the specific claim the Live Weekly Workflow task
required: a double-capture attempt for the same game_id correctly produces a correction record
(old run SUPERSEDED, new run ACTIVE), not an overwrite and not a silently duplicated ACTIVE row.
Uses an in-memory SQLite database, never the real audit database.
"""
import sqlite3
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "prediction_audit"))

from db import write  # noqa: E402
from db.capture_snapshot import capture_snapshot, get_active_run  # noqa: E402
from db.schema import create_database  # noqa: E402


@pytest.fixture
def conn():
    c = create_database(":memory:")
    yield c
    c.close()


def _seed(conn: sqlite3.Connection) -> None:
    write.insert_model(conn, "v35.0", "Frozen v35 baseline", "2026-09-01T00:00:00Z")
    write.insert_game(conn, "2026_05_KC_BUF", season=2026, week=5,
                       away_team="Kansas City Chiefs", home_team="Buffalo Bills")


def test_first_capture_creates_active_run(conn):
    _seed(conn)
    run_id = capture_snapshot(
        conn, "v35.0", "2026_05_KC_BUF", "2026-10-01T12:00:00Z",
        home_projected_points=24.0, away_projected_points=20.0, home_win_probability=0.58,
        components=[{"component_name": "base_team_quality_home", "contribution_value": 3.0,
                     "side": "HOME"}],
    )
    assert get_active_run(conn, "2026_05_KC_BUF") == run_id
    status = conn.execute(
        "SELECT model_status FROM prediction_runs WHERE run_id = ?", (run_id,),
    ).fetchone()[0]
    assert status == "ACTIVE"


def test_real_double_capture_produces_correction_record_not_an_overwrite(conn):
    """The exact real claim the governing task required be true: a second capture for the SAME
    game_id must not overwrite the first -- it supersedes it and adds a new, distinct row."""
    _seed(conn)
    first_run_id = capture_snapshot(
        conn, "v35.0", "2026_05_KC_BUF", "2026-10-01T12:00:00Z",
        home_projected_points=24.0, away_projected_points=20.0, home_win_probability=0.58,
        components=[{"component_name": "base_team_quality_home", "contribution_value": 3.0,
                     "side": "HOME"}],
    )
    second_run_id = capture_snapshot(
        conn, "v35.0", "2026_05_KC_BUF", "2026-10-01T18:00:00Z",
        home_projected_points=26.5, away_projected_points=19.0, home_win_probability=0.63,
        components=[{"component_name": "base_team_quality_home", "contribution_value": 3.2,
                     "side": "HOME"}],
    )

    # Real, distinct run_ids -- the second capture is a genuinely new row, not an update.
    assert second_run_id != first_run_id

    # Real correction-record behavior: the OLD run is SUPERSEDED (still present, unmodified),
    # the NEW run is the sole ACTIVE one.
    old_status = conn.execute(
        "SELECT model_status FROM prediction_runs WHERE run_id = ?", (first_run_id,),
    ).fetchone()[0]
    new_status = conn.execute(
        "SELECT model_status FROM prediction_runs WHERE run_id = ?", (second_run_id,),
    ).fetchone()[0]
    assert old_status == "SUPERSEDED"
    assert new_status == "ACTIVE"
    assert get_active_run(conn, "2026_05_KC_BUF") == second_run_id

    # Real, immutable proof: the FIRST run's own real prediction values are untouched, not
    # overwritten by the second capture's own values.
    old_margin = conn.execute(
        "SELECT projected_margin FROM predictions WHERE run_id = ?", (first_run_id,),
    ).fetchone()[0]
    new_margin = conn.execute(
        "SELECT projected_margin FROM predictions WHERE run_id = ?", (second_run_id,),
    ).fetchone()[0]
    assert old_margin == pytest.approx(4.0)   # 24.0 - 20.0, from the FIRST capture, untouched
    assert new_margin == pytest.approx(7.5)   # 26.5 - 19.0, the correction's own real value

    # Exactly one ACTIVE run per game_id -- never two.
    active_count = conn.execute(
        "SELECT COUNT(*) FROM prediction_runs WHERE game_id = ? AND model_status = 'ACTIVE'",
        ("2026_05_KC_BUF",),
    ).fetchone()[0]
    assert active_count == 1

    # Both real rows still exist -- SUPERSEDED means marked, never deleted.
    total_count = conn.execute(
        "SELECT COUNT(*) FROM prediction_runs WHERE game_id = ?", ("2026_05_KC_BUF",),
    ).fetchone()[0]
    assert total_count == 2


def test_get_active_run_returns_none_when_never_captured(conn):
    _seed(conn)
    assert get_active_run(conn, "2026_05_KC_BUF") is None
