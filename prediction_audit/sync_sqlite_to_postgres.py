"""
Real, one-way sync: SQLite (the live agent's actual source of truth, unaffected by this script)
-> Postgres (a read-only replica, for the PWA/API to display). Never the other direction --
the live agent never reads from or depends on Postgres in any way.

Real scope, per the governing task: game_workflow_status, raw_injury_reports,
raw_roster_snapshots, raw_market_captures -- all scoped to season=2026, the live season this
PWA is meant to show. Historical research data (Phase 1/8's real 2025/2024 reconstructions, the
273 real Part A rows) is deliberately NOT synced -- irrelevant to a live weekly display and
would just be confusing noise.

Real prerequisite tables the governing task's own list didn't mention, but the actual Postgres
schema requires (checked directly, not assumed): `games` (game_workflow_status's own real FK
target) needs a real `sports` row to reference first; `raw_injury_reports`/`raw_roster_
snapshots`/`raw_market_captures` all have a mandatory FK to `ingestion_runs`. Synced first, in
real dependency order.

Real, deliberate UPSERT design, NOT truncate-and-reload -- caught before shipping: TRUNCATE
CASCADE on `games` would also wipe any real prediction data that later references those same
game_ids once Phase 11 starts populating real 2026 predictions (~2026-09-29+), which is
completely outside this sync's real, explicit scope ("does NOT include predictions or audit
results"). UPSERT-by-real-id/game_id never deletes a row, so it stays safe indefinitely, not
just for today's empty-of-predictions state.

Usage:
    uv run python prediction_audit/sync_sqlite_to_postgres.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import psycopg  # noqa: E402

from prediction_audit.db.schema import DEFAULT_DB_PATH  # noqa: E402

SEASON = 2026


def _load_database_url() -> str:
    for line in (Path(__file__).resolve().parent.parent / ".env").read_text(
        encoding="utf-8"
    ).splitlines():
        if line.startswith("DATABASE_URL="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("Real DATABASE_URL not found in .env.")


def _ensure_real_nfl_sport(pg_cur) -> int:
    pg_cur.execute(
        "INSERT INTO sports (name) VALUES ('NFL') "
        "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id;"
    )
    return pg_cur.fetchone()[0]


def _sync_games(sq_conn, pg_cur, sport_id: int) -> int:
    # Real, deliberate INNER JOIN on game_workflow_status -- `games` also holds the real,
    # pre-existing Part A reconstruction dataset (full team names) for the SAME season=2026 as
    # the live agent's real games (abbreviated team names). Only real, live-tracked games ever
    # get a game_workflow_status row (confirmed directly: 272/272 vs 0/272), so this is the
    # same, already-established filter used to keep these two legitimate datasets apart --
    # syncing only the real, live schedule this PWA is meant to show.
    rows = sq_conn.execute(
        "SELECT g.game_id, g.season, g.week, g.game_date, g.kickoff_time, g.away_team, "
        "g.home_team, g.neutral_site, g.stadium, g.surface, g.timezone "
        "FROM games g JOIN game_workflow_status gws ON gws.game_id = g.game_id "
        "WHERE g.season = ?", (SEASON,),
    ).fetchall()
    for r in rows:
        pg_cur.execute(
            "INSERT INTO games (sport_id, game_id, season, week, game_date, kickoff_time, "
            "away_team, home_team, neutral_site, stadium, surface, timezone) "
            "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (game_id) DO UPDATE SET "
            "week=EXCLUDED.week, game_date=EXCLUDED.game_date, "
            "kickoff_time=EXCLUDED.kickoff_time, away_team=EXCLUDED.away_team, "
            "home_team=EXCLUDED.home_team, neutral_site=EXCLUDED.neutral_site, "
            "stadium=EXCLUDED.stadium, surface=EXCLUDED.surface, timezone=EXCLUDED.timezone;",
            (sport_id, r[0], r[1], r[2], r[3], r[4], r[5], r[6], bool(r[7]), r[8], r[9], r[10]),
        )
    return len(rows)


def _sync_game_workflow_status(sq_conn, pg_cur) -> int:
    rows = sq_conn.execute(
        "SELECT gws.game_id, gws.status, gws.status_reason, gws.updated_at "
        "FROM game_workflow_status gws JOIN games g ON g.game_id = gws.game_id "
        "WHERE g.season = ?", (SEASON,),
    ).fetchall()
    for r in rows:
        pg_cur.execute(
            "INSERT INTO game_workflow_status (game_id, status, status_reason, updated_at) "
            "VALUES (%s, %s, %s, %s) "
            "ON CONFLICT (game_id) DO UPDATE SET status=EXCLUDED.status, "
            "status_reason=EXCLUDED.status_reason, updated_at=EXCLUDED.updated_at;",
            r,
        )
    return len(rows)


def _sync_ingestion_runs(sq_conn, pg_cur) -> int:
    rows = sq_conn.execute(
        "SELECT ingestion_id, job_name, run_timestamp, status, source, rows_written, detail "
        "FROM ingestion_runs",
    ).fetchall()
    for r in rows:
        pg_cur.execute(
            "INSERT INTO ingestion_runs (id, job_name, run_timestamp, status, source, "
            "rows_written, detail) VALUES (%s, %s, %s, %s, %s, %s, %s) "
            "ON CONFLICT (id) DO UPDATE SET status=EXCLUDED.status, "
            "rows_written=EXCLUDED.rows_written, detail=EXCLUDED.detail;",
            r,
        )
    if rows:
        pg_cur.execute(
            "SELECT setval(pg_get_serial_sequence('ingestion_runs', 'id'), %s);",
            (max(r[0] for r in rows),),
        )
    return len(rows)


# Real SQLite-INTEGER-vs-Postgres-BOOLEAN columns needing explicit coercion -- SQLite has no
# native boolean type (stores 0/1 as INTEGER), Postgres does and rejects a bare smallint for a
# real BOOLEAN column (caught by this script's own first real run, not assumed).
_BOOLEAN_COLUMNS = {"flagged_excluded_source"}


def _sync_raw_table(sq_conn, pg_cur, table: str, columns: list[str],
                     season_filter: bool, exclude_flagged_sources: bool = False) -> int:
    col_list = ", ".join(columns)
    query = f"SELECT {col_list} FROM {table}"
    where_clauses = []
    params: list = []
    if season_filter:
        where_clauses.append("season = ?")
        params.append(SEASON)
    if exclude_flagged_sources:
        # Real, deliberate exclusion -- these are the rows Part D's offshore-books fix flagged
        # (bovada/mybookieag/betonlineag/betrivers/betus/lowvig). Postgres's own
        # reject_unapproved_sportsbook trigger (hosted_env/schema.sql) correctly refuses to
        # accept them, so the sync must filter them out itself rather than let every one of
        # them abort the sync's single transaction (caught by this script's own real second
        # run, not assumed).
        where_clauses.append("flagged_excluded_source = 0")
    if where_clauses:
        query += " WHERE " + " AND ".join(where_clauses)
    rows = sq_conn.execute(query, params).fetchall()
    bool_idx = [i for i, c in enumerate(columns) if c in _BOOLEAN_COLUMNS]
    if bool_idx:
        rows = [
            tuple(bool(v) if i in bool_idx else v for i, v in enumerate(r))
            for r in rows
        ]
    placeholders = ", ".join(["%s"] * len(columns))
    update_cols = [c for c in columns if c != "id"]
    update_clause = ", ".join(f"{c}=EXCLUDED.{c}" for c in update_cols)
    for r in rows:
        pg_cur.execute(
            f"INSERT INTO {table} ({col_list}) VALUES ({placeholders}) "
            f"ON CONFLICT (id) DO UPDATE SET {update_clause};",
            r,
        )
    if rows:
        id_idx = columns.index("id")
        pg_cur.execute(
            f"SELECT setval(pg_get_serial_sequence('{table}', 'id'), %s);",
            (max(r[id_idx] for r in rows),),
        )
    return len(rows)


def main() -> None:
    database_url = _load_database_url()
    sq_conn = sqlite3.connect(DEFAULT_DB_PATH)

    with psycopg.connect(database_url, connect_timeout=15) as pg_conn:
        with pg_conn.cursor() as pg_cur:
            # Real, before counts -- for the required real reconciliation evidence.
            before = {}
            for t in ("games", "game_workflow_status", "ingestion_runs",
                      "raw_injury_reports", "raw_roster_snapshots", "raw_market_captures"):
                pg_cur.execute(f"SELECT COUNT(*) FROM {t};")
                before[t] = pg_cur.fetchone()[0]

            sport_id = _ensure_real_nfl_sport(pg_cur)
            print(f"Real 'NFL' sports.id = {sport_id}")

            src_counts = {}
            src_counts["games"] = _sync_games(sq_conn, pg_cur, sport_id)
            src_counts["game_workflow_status"] = _sync_game_workflow_status(sq_conn, pg_cur)
            src_counts["ingestion_runs"] = _sync_ingestion_runs(sq_conn, pg_cur)
            src_counts["raw_injury_reports"] = _sync_raw_table(
                sq_conn, pg_cur, "raw_injury_reports",
                ["id", "ingestion_id", "season", "week", "team", "player_name", "position",
                 "report_status", "practice_status", "pulled_at", "source"],
                season_filter=True,
            )
            src_counts["raw_roster_snapshots"] = _sync_raw_table(
                sq_conn, pg_cur, "raw_roster_snapshots",
                ["id", "ingestion_id", "season", "team", "player_name", "position",
                 "depth_rank", "roster_status", "pulled_at", "source"],
                season_filter=True,
            )
            src_counts["raw_market_captures"] = _sync_raw_table(
                sq_conn, pg_cur, "raw_market_captures",
                ["id", "ingestion_id", "game_id", "sportsbook", "market_type", "line_value",
                 "odds", "captured_at", "kickoff_time", "source", "market_data_status",
                 "flagged_excluded_source"],
                season_filter=False, exclude_flagged_sources=True,
            )
            pg_conn.commit()

            after = {}
            for t in before:
                pg_cur.execute(f"SELECT COUNT(*) FROM {t};")
                after[t] = pg_cur.fetchone()[0]

    sq_conn.close()

    print("\n=== Real sync reconciliation ===")
    for t in before:
        print(f"  {t:25s} postgres_before={before[t]:5d}  sqlite_source_rows="
              f"{src_counts[t]:5d}  postgres_after={after[t]:5d}")


if __name__ == "__main__":
    main()
