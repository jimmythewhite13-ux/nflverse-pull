"""
Step 5, made real: populates the Prediction Audit database with a real `prediction_runs` +
`predictions` row for every one of the 272 real 2026 games (using the Python Model Engine's
own fully-verified real Model Home/Away Score from `season_matchups.py` -- see
`test_season_matchups_full_reconstruction.py`, and the real Excel Win Probability from Market
Comparison & Confidence), plus a real `market_lines` row for every game that currently has a
real, non-null market line (see `market_data.py`'s own docstring for the real source and what
it does/doesn't cover).

This is deliberately a SEPARATE set of prediction_runs from `seed_v35_demo.py`'s single demo
row (which sourced its projected scores/win-probability straight from the recalculated Excel
file for one game) -- both are real, both are legitimate audit entries for the same game_id,
distinguished by `data_version`. The schema is insert-only by design specifically so multiple
real prediction sources for the same game can coexist without conflict.

Real inputs, no fabrication:
- Model Home/Away Score: prediction_audit/manifests/v35_model_home_away_score_ground_truth.json
  (the real Excel Z/AA values -- this ingestion does NOT recompute them, since Python parity
  with those exact values is already proven; recomputing here would just be redundant work,
  not a stronger claim).
- Win Probability: prediction_audit/manifests/v35_win_probability_ground_truth.json (real,
  extracted from Market Comparison & Confidence -- not yet ported to the Python Model Engine,
  so read directly from a real recalculated copy, same as seed_v35_demo.py does for its one row).
- Market lines: market_data.fetch_real_market_lines(2026) -- real, live, network-fetched.

Usage:
    uv run python prediction_audit/ingest_step5_market_lines.py
"""
from __future__ import annotations

import json
import sys
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from db import write  # noqa: E402
from db.schema import DEFAULT_DB_PATH, create_database  # noqa: E402
from market_data import REAL_SOURCE_NAME, fetch_real_market_lines  # noqa: E402

MANIFESTS = Path(__file__).resolve().parent / "manifests"
DATA_VERSION = "python_model_engine_full_reconstruction_2026"


def _load(name: str) -> dict:
    with open(MANIFESTS / name, encoding="utf-8") as f:
        return json.load(f)


def _game_id(season: int, week: int, away: str, home: str) -> str:
    return f"{season}_{week:02d}_{away}_{home}".replace(" ", "")


def main() -> None:
    conn = create_database(DEFAULT_DB_PATH)
    now = datetime.now(UTC).isoformat()

    scores = _load("v35_model_home_away_score_ground_truth.json")["games"]
    win_probs = {
        (g["week"], g["away"], g["home"]): g
        for g in _load("v35_win_probability_ground_truth.json")["games"]
    }

    n_runs = 0
    n_missing_wp = 0
    run_id_by_game = {}
    for g in scores:
        key = (g["week"], g["away"], g["home"])
        wp_row = win_probs.get(key)
        if wp_row is None:
            n_missing_wp += 1
            continue

        game_id = _game_id(2026, g["week"], g["away"], g["home"])
        run_id = write.insert_prediction_run(
            conn, "v35.0", game_id, prediction_timestamp=now,
            data_cutoff_timestamp=now, data_version=DATA_VERSION,
        )
        home_score = g["excel_Z_model_home_score"]
        away_score = g["excel_AA_model_away_score"]
        home_wp = wp_row["excel_win_probability_home"]
        write.insert_prediction(
            conn, run_id,
            away_projected_points=away_score, home_projected_points=home_score,
            projected_margin=home_score - away_score, projected_total=home_score + away_score,
            home_win_probability=home_wp, away_win_probability=1 - home_wp,
            confidence=wp_row.get("excel_confidence_composite"),
        )
        run_id_by_game[key] = run_id
        n_runs += 1

    print(f"Inserted {n_runs} real prediction_runs (model_version=v35.0, "
          f"data_version={DATA_VERSION}).")
    if n_missing_wp:
        print(f"  {n_missing_wp} games skipped -- no real win-probability ground truth "
              f"available for them.")

    # ---- Real market lines (Step 5) --------------------------------------------------------
    real_lines = fetch_real_market_lines(2026)
    n_lines = 0
    n_no_real_line_yet = 0
    for line in real_lines:
        key = (line.week, line.away_team, line.home_team)
        run_id = run_id_by_game.get(key)
        if run_id is None:
            continue  # no prediction_run for this game (shouldn't happen for 2026, but honest)

        if line.spread_line is None and line.total_line is None:
            n_no_real_line_yet += 1
            continue

        if line.spread_line is not None:
            write.insert_market_line(
                conn, run_id, sportsbook="market_consensus", market_type="spread",
                line_stage="prediction_time", line_value=line.spread_line,
                line_timestamp=now, source=REAL_SOURCE_NAME, market_data_status="VERIFIED",
            )
            n_lines += 1
        if line.total_line is not None:
            write.insert_market_line(
                conn, run_id, sportsbook="market_consensus", market_type="total",
                line_stage="prediction_time", line_value=line.total_line,
                line_timestamp=now, source=REAL_SOURCE_NAME, market_data_status="VERIFIED",
            )
            n_lines += 1

    print(f"Inserted {n_lines} real market_lines rows (VERIFIED, line_stage=prediction_time, "
          f"source={REAL_SOURCE_NAME}).")
    print(f"  {n_no_real_line_yet} games genuinely have no real line posted yet (future "
          f"weeks) -- left with no market_lines row rather than a fabricated MISSING row.")
    print("Real CLV requires a later re-fetch of this same source close to each game's "
          "kickoff to capture the real closing line (line_stage='closing').")

    conn.close()
    print(f"Saved to {DEFAULT_DB_PATH}")


if __name__ == "__main__":
    main()
