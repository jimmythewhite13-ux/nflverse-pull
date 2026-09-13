"""
Real, one-time migration for the ALREADY-EXISTING live database (apply_epl_findings.md Part D,
2026-09-13): `create_database()`'s `CREATE TABLE IF NOT EXISTS` (schema.py) adds the new
`is_closeable` column cleanly on a fresh DB, but cannot add a column to a `prediction_audit_
metrics` table that already exists under that name -- SQLite's `IF NOT EXISTS` only checks the
object name, never diffs columns (same real gap `migrate_approved_sportsbooks.py` already
documented and fixed for `raw_market_captures.flagged_excluded_source`). Needs a real, explicit
`ALTER TABLE ... ADD COLUMN` here, once, against the real live database.

Idempotent: checks whether the column already exists before adding it, safe to re-run.

Usage:
    uv run python prediction_audit/migrate_is_closeable.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from prediction_audit.db.schema import DEFAULT_DB_PATH, create_database  # noqa: E402


def main() -> None:
    conn = create_database(DEFAULT_DB_PATH)

    cols = [row[1] for row in conn.execute("PRAGMA table_info(prediction_audit_metrics)")]
    if "is_closeable" not in cols:
        print("Adding real is_closeable column to prediction_audit_metrics...")
        conn.execute(
            "ALTER TABLE prediction_audit_metrics ADD COLUMN is_closeable INTEGER"
        )
        conn.commit()
    else:
        print("is_closeable already present -- idempotent no-op.")

    print("\nReal, current prediction_audit_metrics is_closeable breakdown:")
    for row in conn.execute(
        "SELECT is_closeable, COUNT(*) FROM prediction_audit_metrics GROUP BY is_closeable"
    ):
        print(" ", row)

    conn.close()


if __name__ == "__main__":
    main()
