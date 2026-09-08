"""
Shared real logging helper for every ingestion job -- Section 4's failure-handling rule applies
uniformly: a genuinely unavailable source writes a real `MISSING` row (source=NULL), never a
skipped/silent gap and never a fabricated value. Every job in this package calls
`run_job()` as its single entry point so this discipline can't be bypassed per-job.
"""
from __future__ import annotations

import sqlite3
import traceback
from collections.abc import Callable
from datetime import UTC, datetime

from prediction_audit.db.schema import DEFAULT_DB_PATH, create_database


def run_job(
    job_name: str, source: str, fn: Callable[[sqlite3.Connection, int], int],
    db_path: str | None = None,
) -> dict:
    """Runs `fn(conn, ingestion_id)` -- `fn` must return the real number of rows it wrote, and
    must itself decide SUCCESS vs MISSING (e.g. by raising `SourceUnavailable` when a real pull
    returns nothing). Any other exception is logged as a real FAILURE (with the real traceback
    in `detail`) rather than crashing the whole scheduled workflow silently."""
    conn = create_database(db_path or DEFAULT_DB_PATH)
    run_timestamp = datetime.now(UTC).isoformat()
    cur = conn.execute(
        "INSERT INTO ingestion_runs (job_name, run_timestamp, status, source, rows_written) "
        "VALUES (?, ?, 'SUCCESS', ?, 0)",
        (job_name, run_timestamp, source),
    )
    ingestion_id = cur.lastrowid
    conn.commit()

    try:
        rows_written = fn(conn, ingestion_id)
        conn.execute(
            "UPDATE ingestion_runs SET status='SUCCESS', rows_written=? WHERE ingestion_id=?",
            (rows_written, ingestion_id),
        )
        conn.commit()
        result = {"job_name": job_name, "status": "SUCCESS", "rows_written": rows_written,
                   "ingestion_id": ingestion_id}
    except CadenceSkip as e:
        # A deliberate, healthy skip (e.g. the market-lines cadence gate) -- distinct from
        # MISSING (a real, unhealthy gap), so a dashboard/query can't confuse "chose not to
        # call" with "the source was unavailable."
        conn.execute(
            "UPDATE ingestion_runs SET status='SKIPPED', detail=? WHERE ingestion_id=?",
            (str(e), ingestion_id),
        )
        conn.commit()
        result = {"job_name": job_name, "status": "SKIPPED", "rows_written": 0,
                   "ingestion_id": ingestion_id, "detail": str(e)}
    except SourceUnavailable as e:
        conn.execute(
            "UPDATE ingestion_runs SET status='MISSING', source=NULL, detail=? "
            "WHERE ingestion_id=?",
            (str(e), ingestion_id),
        )
        conn.commit()
        result = {"job_name": job_name, "status": "MISSING", "rows_written": 0,
                   "ingestion_id": ingestion_id, "detail": str(e)}
    except Exception:
        tb = traceback.format_exc()
        conn.execute(
            "UPDATE ingestion_runs SET status='FAILURE', detail=? WHERE ingestion_id=?",
            (tb, ingestion_id),
        )
        conn.commit()
        result = {"job_name": job_name, "status": "FAILURE", "rows_written": 0,
                   "ingestion_id": ingestion_id, "detail": tb}
    finally:
        conn.close()
    return result


class SourceUnavailable(Exception):
    """Raise this, never silently return an empty result, when a real data source is
    genuinely unreachable or returns nothing real to write -- `run_job()` converts it into a
    real, visible MISSING row rather than a silent gap."""


class CadenceSkip(Exception):
    """Raise this for a deliberate, healthy 'not due yet' skip (e.g. the market-lines cadence
    gate) -- distinct from SourceUnavailable, which means the source itself was unreachable."""
