"""
Real, ONE-TIME backfill: SQLite's real, validated Phase 1 (2025, 224 games) + Phase 8 (2024,
220 games) reconstructions -> Postgres, for the new Historical/backtest PWA tab
(historical_backtest_view.md). Deliberately NOT part of sync_sqlite_to_postgres.py's own
recurring hourly sync -- that script's own docstring is explicit this research data is out of
scope for the live weekly sync ("irrelevant to a live weekly display"). This data is different:
it's a real, frozen, one-time reconstruction that never changes once computed, so a one-time
backfill is the correct real pattern, not a recurring job re-syncing static data forever.

Real, explicit scope -- exactly the two CORRECTED model_versions this project's own audit trail
identifies as the valid, current numbers (see PROGRESS.md's "Real bug found and fixed", the HFA
raw-estimator factor-of-2 fix, 2026-09-09), not the older, superseded pre-fix runs also still
sitting in the same SQLite tables:
  - 'v35.0-hfa-raw-estimator-fix'                                (season 2025, Phase 1, 224 games)
  - 'v35.0-degraded-ol-2024-secondary-check-hfa-raw-estimator-fix' (season 2024, Phase 8, 220 games)

Usage (run once; re-running is safe/idempotent via ON CONFLICT upserts, but this data never
changes so there should be no real reason to run it again):
    uv run python prediction_audit/sync_historical_to_postgres.py
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

import psycopg

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.db.schema import DEFAULT_DB_PATH  # noqa: E402

# Real, explicit -- see module docstring for why exactly these two, not every model_version.
REAL_HISTORICAL_MODEL_VERSIONS = [
    "v35.0-hfa-raw-estimator-fix",
    "v35.0-degraded-ol-2024-secondary-check-hfa-raw-estimator-fix",
]


def _load_database_url() -> str:
    env_value = os.environ.get("DATABASE_URL")
    if env_value:
        return env_value
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text(encoding="utf-8").splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("Real DATABASE_URL not available.")


def main() -> None:
    database_url = _load_database_url()
    sq_conn = sqlite3.connect(DEFAULT_DB_PATH)
    sq_conn.row_factory = sqlite3.Row

    with psycopg.connect(database_url, connect_timeout=15) as pg_conn:
        with pg_conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sports (name) VALUES ('NFL') "
                "ON CONFLICT (name) DO UPDATE SET name = EXCLUDED.name RETURNING id;"
            )
            sport_id = cur.fetchone()[0]

            total_games = total_runs = total_results = 0
            for model_version in REAL_HISTORICAL_MODEL_VERSIONS:
                # Real model metadata, straight from the SQLite `models` table -- not fabricated.
                model_row = sq_conn.execute(
                    "SELECT model_version, notes FROM models WHERE model_version = ?",
                    (model_version,),
                ).fetchone()
                notes = model_row["notes"] if model_row else None

                cur.execute(
                    "INSERT INTO model_versions (sport_id, version_name, status, notes) "
                    "VALUES (%s, %s, 'RESEARCH', %s) "
                    "ON CONFLICT (sport_id, version_name) DO UPDATE SET notes = EXCLUDED.notes "
                    "RETURNING id;",
                    (sport_id, model_version, notes),
                )
                model_version_id = cur.fetchone()[0]

                rows = sq_conn.execute(
                    """
                    SELECT g.game_id, g.season, g.week, g.game_date, g.kickoff_time,
                           g.away_team, g.home_team, g.neutral_site, g.stadium, g.surface,
                           g.timezone, pr.prediction_timestamp, pr.data_cutoff_timestamp,
                           pr.data_version, p.away_projected_points, p.home_projected_points,
                           p.projected_margin, p.projected_total, p.home_win_probability,
                           p.away_win_probability, p.confidence,
                           r.away_final_score, r.home_final_score
                    FROM predictions p
                    JOIN prediction_runs pr ON pr.run_id = p.run_id
                    JOIN games g ON g.game_id = pr.game_id
                    JOIN results r ON r.game_id = g.game_id
                    WHERE pr.model_version = ?
                    """,
                    (model_version,),
                ).fetchall()

                for row in rows:
                    cur.execute(
                        "INSERT INTO games (sport_id, game_id, season, week, game_date, "
                        "kickoff_time, away_team, home_team, neutral_site, stadium, surface, "
                        "timezone) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (game_id) DO NOTHING;",
                        (sport_id, row["game_id"], row["season"], row["week"], row["game_date"],
                         row["kickoff_time"], row["away_team"], row["home_team"],
                         bool(row["neutral_site"]), row["stadium"], row["surface"],
                         row["timezone"]),
                    )
                    total_games += cur.rowcount

                    # Real, deliberate skip-if-exists guard -- found live, 2026-09-12:
                    # `prediction_runs`/`predictions` have no natural real conflict target for
                    # ON CONFLICT (a real database-enforced immutability rule blocks DELETE
                    # outright, so this table can never be cleaned up after the fact), and this
                    # insert previously had no guard at all -- a real re-run (needed to also
                    # backfill player_prop_backtest) duplicated all 444 real rows before this
                    # fix. Checked first, real and explicit, rather than relying on a DB-level
                    # constraint that doesn't exist here.
                    cur.execute(
                        "SELECT pr.id FROM prediction_runs pr "
                        "WHERE pr.model_version_id = %s AND pr.game_id = %s;",
                        (model_version_id, row["game_id"]),
                    )
                    existing = cur.fetchone()
                    if existing:
                        continue
                    cur.execute(
                        "INSERT INTO prediction_runs (model_version_id, game_id, "
                        "prediction_timestamp, data_cutoff_timestamp, data_version, "
                        "model_status) VALUES (%s, %s, %s, %s, %s, 'ACTIVE') RETURNING id;",
                        (model_version_id, row["game_id"], row["prediction_timestamp"],
                         row["data_cutoff_timestamp"], row["data_version"]),
                    )
                    run_id = cur.fetchone()[0]
                    total_runs += 1

                    cur.execute(
                        "INSERT INTO predictions (run_id, away_projected_points, "
                        "home_projected_points, projected_margin, projected_total, "
                        "home_win_probability, away_win_probability, confidence) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s);",
                        (run_id, row["away_projected_points"], row["home_projected_points"],
                         row["projected_margin"], row["projected_total"],
                         row["home_win_probability"], row["away_win_probability"],
                         row["confidence"]),
                    )

                    cur.execute(
                        "INSERT INTO results (game_id, away_final_score, home_final_score) "
                        "VALUES (%s, %s, %s) ON CONFLICT (game_id) DO NOTHING;",
                        (row["game_id"], row["away_final_score"], row["home_final_score"]),
                    )
                    total_results += cur.rowcount

                print(f"  {model_version}: {len(rows)} real rows processed", flush=True)

            # Real player-prop backtest rows (historical_player_prop_backtest.md) -- same real,
            # one-time backfill pattern, keyed by (game_id, player_id, stat_type) so a re-run
            # (e.g. after fixing a real bug in the backtest script) safely replaces the old real
            # rows for that model_version rather than duplicating them.
            cur.execute(
                "DELETE FROM player_prop_backtest WHERE model_version = %s;",
                (REAL_HISTORICAL_MODEL_VERSIONS[0],),
            )
            backtest_rows = sq_conn.execute(
                "SELECT game_id, season, week, player_id, player_name, team, position, "
                "stat_type, projected_value, actual_value, model_version, created_at "
                "FROM player_prop_backtest WHERE model_version = ?",
                (REAL_HISTORICAL_MODEL_VERSIONS[0],),
            ).fetchall()
            if backtest_rows:
                cur.executemany(
                    "INSERT INTO player_prop_backtest (game_id, season, week, player_id, "
                    "player_name, team, position, stat_type, projected_value, actual_value, "
                    "model_version, created_at) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, "
                    "%s, %s, %s);",
                    [tuple(r) for r in backtest_rows],
                )
            print(f"  player_prop_backtest: {len(backtest_rows)} real rows processed", flush=True)

            pg_conn.commit()

    sq_conn.close()
    print(f"\nReal historical backfill complete: {total_games} new games, "
          f"{total_runs} new prediction_runs, {total_results} new results rows, "
          f"{len(backtest_rows)} real prop-backtest rows.")


if __name__ == "__main__":
    main()
