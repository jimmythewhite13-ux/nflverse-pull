"""
Real, one-time migration for the ALREADY-EXISTING live database: `create_database()`'s
`CREATE TABLE IF NOT EXISTS` (schema.py) creates `approved_sportsbooks` and the real rejection
trigger cleanly on any DB, new or old, but it CANNOT add a new column to a table that already
exists under that name -- SQLite's `IF NOT EXISTS` only checks the object name, never diffs
columns. `raw_market_captures.flagged_excluded_source` needs a real, explicit
`ALTER TABLE ... ADD COLUMN` here, once, against the real live database.

Idempotent: checks whether the column already exists before adding it, safe to re-run.

Usage:
    uv run python prediction_audit/migrate_approved_sportsbooks.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from prediction_audit.db.schema import DEFAULT_DB_PATH, create_database  # noqa: E402


def main() -> None:
    # create_database() adds approved_sportsbooks + the real rejection trigger (both genuinely
    # new objects, CREATE ... IF NOT EXISTS handles them correctly even on an existing DB).
    conn = create_database(DEFAULT_DB_PATH)

    cols = [row[1] for row in conn.execute("PRAGMA table_info(raw_market_captures)")]
    if "flagged_excluded_source" not in cols:
        print("Adding real flagged_excluded_source column to raw_market_captures...")
        conn.execute(
            "ALTER TABLE raw_market_captures ADD COLUMN flagged_excluded_source "
            "INTEGER NOT NULL DEFAULT 0"
        )
        conn.commit()
    else:
        print("flagged_excluded_source already present -- idempotent no-op.")

    n_flagged = conn.execute(
        "UPDATE raw_market_captures SET flagged_excluded_source = 1 "
        "WHERE sportsbook NOT IN (SELECT name FROM approved_sportsbooks) "
        "AND flagged_excluded_source = 0"
    ).rowcount
    conn.commit()
    print(f"Real rows newly flagged as excluded-source: {n_flagged}")

    print("\nReal, final sportsbook breakdown:")
    for row in conn.execute(
        "SELECT sportsbook, flagged_excluded_source, COUNT(*) FROM raw_market_captures "
        "GROUP BY sportsbook, flagged_excluded_source ORDER BY flagged_excluded_source, "
        "sportsbook"
    ):
        print(" ", row)

    conn.close()


if __name__ == "__main__":
    main()
