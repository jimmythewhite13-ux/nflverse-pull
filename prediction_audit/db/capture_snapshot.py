"""
`capture_snapshot()` -- the real, named, tested immutable-capture mechanism the Live Weekly
Workflow task refers to. It did not exist under this name before (see PROGRESS.md's real
discrepancy note, 2026-09-08) -- this module is a thin, clearly-named wrapper around
functionality that DID already exist (`write.insert_prediction_run()`/`mark_run_status()`
already implement the real "immutable audit record, corrected re-run gets a new row" discipline
`write.py`'s own docstring describes), not a reimplementation.

Real semantics, exactly matching the task's own description: capturing a SECOND time for a
game_id that already has an ACTIVE run does not overwrite anything -- the old run is marked
SUPERSEDED (still fully present, queryable, immutable in its own right) and a brand-new run_id
is inserted as the current, ACTIVE "correction record". Calling code always reads the ACTIVE
run per game_id as the authoritative one.
"""
from __future__ import annotations

import sqlite3

from . import write


def capture_snapshot(
    conn: sqlite3.Connection, model_version: str, game_id: str, prediction_timestamp: str,
    home_projected_points: float, away_projected_points: float, home_win_probability: float,
    components: list[dict], data_cutoff_timestamp: str | None = None,
    data_version: str | None = None, confidence: float | None = None,
) -> int:
    """Freezes one real prediction for `game_id`. Returns the new run_id.

    Real correction-record behavior: if an ACTIVE run already exists for this game_id, it is
    marked SUPERSEDED first (never deleted, never overwritten) before the new one is inserted --
    confirmed by `tests/test_capture_snapshot.py`'s own real double-capture test, not assumed."""
    existing = conn.execute(
        "SELECT run_id FROM prediction_runs WHERE game_id = ? AND model_status = 'ACTIVE'",
        (game_id,),
    ).fetchall()
    for (old_run_id,) in existing:
        write.mark_run_status(conn, old_run_id, "SUPERSEDED")

    margin = home_projected_points - away_projected_points
    total = home_projected_points + away_projected_points
    run_id = write.insert_prediction_run(
        conn, model_version, game_id, prediction_timestamp,
        data_cutoff_timestamp=data_cutoff_timestamp, data_version=data_version,
    )
    write.insert_prediction(
        conn, run_id, away_projected_points=away_projected_points,
        home_projected_points=home_projected_points, projected_margin=margin,
        projected_total=total, home_win_probability=home_win_probability,
        away_win_probability=1 - home_win_probability, confidence=confidence,
    )
    write.insert_component_contributions(conn, run_id, components)
    return run_id


def get_active_run(conn: sqlite3.Connection, game_id: str) -> int | None:
    """Real, current ACTIVE run_id for a game_id, or None if never captured. The one function
    every downstream reader (results/audit) should use, rather than assuming the latest run_id
    is the active one (true today, but this is the real, explicit contract, not an inferred
    convention)."""
    row = conn.execute(
        "SELECT run_id FROM prediction_runs WHERE game_id = ? AND model_status = 'ACTIVE'",
        (game_id,),
    ).fetchone()
    return row[0] if row else None
