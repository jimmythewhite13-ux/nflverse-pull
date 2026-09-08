"""
Daily refresh Job 1, step 1: real current-week injury report status. Reuses
`nflverse_pull.availability.fetch_injuries()` -- the same real `import_injuries()` call already
used for historical data -- rather than a new pull. Writes into `raw_injury_reports`, the real
standalone table `QB Status Auto-Suggestion`
(Downloads/claude_code_spec_dynamic_injury_feed.md) is meant to read from: this script closes
the "no network access to automate this" gap that spec's own suggestion-column design assumed
would eventually be filled by a human typing values in.

Real, explicit non-goal (per that same spec, section "How this interacts with the actual Status
field"): this script NEVER writes into the workbook's own `Starting QB Status` manual field --
only the source data a human (or that spec's own suggestion column) reads.

Usage:
    uv run python -m prediction_audit.ingestion.injuries --season 2026
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import pandas as pd  # noqa: E402

from nflverse_pull.availability import fetch_injuries  # noqa: E402
from prediction_audit.ingestion.log import SourceUnavailable, run_job  # noqa: E402

SOURCE = "nflverse (nfl_data_py.import_injuries)"


def _val(row: pd.Series, col: str):
    """Real NaN-safe field read -- returns None (never fabricates) for a genuinely missing
    real value rather than writing NaN into a TEXT column."""
    v = row.get(col)
    return None if v is None or v != v else v


def _write(conn: sqlite3.Connection, ingestion_id: int, season: int) -> int:
    df = fetch_injuries([season])
    if df is None or df.empty:
        raise SourceUnavailable(
            f"Real fetch_injuries([{season}]) returned no real rows -- genuinely unavailable "
            f"right now (e.g. off-season, or the real source itself has no current data)."
        )
    pulled_at = datetime.now(UTC).isoformat()
    rows = [
        (
            ingestion_id, int(row["season"]),
            int(row["week"]) if _val(row, "week") is not None else None,
            row["team"], row["full_name"], _val(row, "position"),
            _val(row, "report_status"), _val(row, "practice_status"),
            pulled_at, SOURCE,
        )
        for _, row in df.iterrows()
    ]
    conn.executemany(
        "INSERT INTO raw_injury_reports (ingestion_id, season, week, team, player_name, "
        "position, report_status, practice_status, pulled_at, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def main(season: int) -> dict:
    result = run_job("injuries", SOURCE, lambda conn, iid: _write(conn, iid, season))
    print(f"injuries job: {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    main(args.season)
