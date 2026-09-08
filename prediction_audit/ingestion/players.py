"""
Daily refresh Job 1, step 2: real current depth-chart / roster snapshot. Reuses
`nflverse_pull.current_roster.fetch_depth_charts()` + `compute_current_starters()` -- the same
real depth-chart pull and transform this project's own Starter/Backup resolution already uses
-- rather than a new pull or a new ranking logic.

Usage:
    uv run python -m prediction_audit.ingestion.players --season 2026
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from nflverse_pull.current_roster import (  # noqa: E402
    compute_current_starters,
    fetch_depth_charts,
)
from prediction_audit.ingestion.log import SourceUnavailable, run_job  # noqa: E402

SOURCE = "nflverse (nfl_data_py.import_depth_charts)"


def _write(conn: sqlite3.Connection, ingestion_id: int, season: int) -> int:
    depth_charts = fetch_depth_charts([season])
    if depth_charts is None or depth_charts.empty:
        raise SourceUnavailable(
            f"Real fetch_depth_charts([{season}]) returned no real rows -- genuinely "
            f"unavailable right now."
        )
    starters = compute_current_starters(depth_charts)
    pulled_at = datetime.now(UTC).isoformat()
    # Real, occasional gap in nflverse's own depth-chart data: a real slot with no player name
    # recorded (e.g. a genuinely vacant depth-chart position). Skipped, not fabricated -- real,
    # visible count reported rather than crashing the whole job on 2-3 real bad rows out of
    # ~1400.
    missing_name = starters["Player Name"].isna()
    if missing_name.any():
        print(f"  Real, skipped {missing_name.sum()} real row(s) with no player name recorded "
              f"upstream: "
              f"{starters.loc[missing_name, ['Team', 'Position']].to_dict('records')}")
    starters = starters[~missing_name]
    rows = [
        (
            ingestion_id, season, row["Team"], row["Player Name"], row["Position"],
            int(row["Depth Order"]), row["Source"], pulled_at, SOURCE,
        )
        for _, row in starters.iterrows()
    ]
    conn.executemany(
        "INSERT INTO raw_roster_snapshots (ingestion_id, season, team, player_name, "
        "position, depth_rank, roster_status, pulled_at, source) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        rows,
    )
    conn.commit()
    return len(rows)


def main(season: int) -> dict:
    result = run_job("rosters", SOURCE, lambda conn, iid: _write(conn, iid, season))
    print(f"rosters job: {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    main(args.season)
