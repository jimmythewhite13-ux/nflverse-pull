"""
Structural verification of the real Step 5 ingestion (prediction_audit/ingest_step5_market_lines.py)
against the committed prediction_audit.sqlite3. Deliberately does NOT hard-code specific real
odds/line values -- those are live market data that legitimately changes every time the
ingestion script is re-run (lines move, more weeks populate as the season progresses). Instead
checks the structural invariants the ingestion promises: every market line it writes is real,
sourced, and honestly labeled -- never a fabricated placeholder.
"""
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.db.schema import DEFAULT_DB_PATH  # noqa: E402
from prediction_audit.market_data import REAL_SOURCE_NAME  # noqa: E402


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def test_db_file_exists():
    assert Path(DEFAULT_DB_PATH).exists()


def test_at_least_272_prediction_runs_for_v35():
    conn = _conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM prediction_runs WHERE model_version = 'v35.0'"
    ).fetchone()[0]
    assert n >= 272


def test_python_model_engine_runs_cover_all_272_real_games():
    conn = _conn()
    n = conn.execute(
        "SELECT COUNT(*) FROM prediction_runs "
        "WHERE data_version = 'python_model_engine_full_reconstruction_2026'"
    ).fetchone()[0]
    assert n == 272


def test_every_prediction_has_a_valid_win_probability():
    conn = _conn()
    rows = conn.execute(
        "SELECT home_win_probability, away_win_probability FROM predictions "
        "JOIN prediction_runs USING (run_id) "
        "WHERE data_version = 'python_model_engine_full_reconstruction_2026'"
    ).fetchall()
    assert len(rows) == 272
    for home_wp, away_wp in rows:
        assert 0.0 <= home_wp <= 1.0
        assert 0.0 <= away_wp <= 1.0
        assert abs((home_wp + away_wp) - 1.0) < 1e-9


def test_every_market_line_is_verified_and_sourced():
    conn = _conn()
    rows = conn.execute(
        "SELECT market_data_status, source, line_stage, market_type, line_value "
        "FROM market_lines"
    ).fetchall()
    assert len(rows) > 0, "expected at least some real market lines to be ingested"
    for status, source, stage, market_type, value in rows:
        # Every row this project's own ingestion writes is real and verified -- never a
        # fabricated placeholder or a silently-defaulted MISSING row inserted just to fill
        # a slot.
        assert status == "VERIFIED"
        assert source == REAL_SOURCE_NAME
        assert stage == "prediction_time"
        assert market_type in ("spread", "total")
        assert value is not None


def test_market_lines_come_in_matched_spread_total_pairs_per_game():
    conn = _conn()
    rows = conn.execute(
        "SELECT run_id, market_type FROM market_lines"
    ).fetchall()
    by_run: dict[int, set[str]] = {}
    for run_id, market_type in rows:
        by_run.setdefault(run_id, set()).add(market_type)
    for run_id, types in by_run.items():
        assert types == {"spread", "total"}, (
            f"run_id {run_id} has an incomplete spread/total pair: {types}"
        )


def test_v_clv_and_v_prediction_errors_views_are_queryable():
    # No real closing line or real result exists yet for the 2026 season in progress -- both
    # views correctly return zero rows rather than erroring or fabricating one.
    conn = _conn()
    conn.execute("SELECT COUNT(*) FROM v_clv").fetchone()
    conn.execute("SELECT COUNT(*) FROM v_prediction_errors").fetchone()
