"""
Populates the real Prediction Audit database with every real v35 game (272 real Season
Matchups rows) and ONE fully-populated real prediction (all tables exercised end to end) --
proves Steps 2-3's schema against real data rather than only the synthetic in-memory tests in
tests/test_prediction_audit_db.py.

Deliberately NOT a full historical backfill -- that's Step 6 (walk-forward reconstruction
2021-2025), a much larger separate undertaking. This script only ever reads the frozen,
already-recalculated v35 copy; it never touches the live workbook or re-triggers a pipeline
run.

Usage:
    uv run python prediction_audit/seed_v35_demo.py "path/to/recalculated_v35.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl

sys.path.insert(0, str(Path(__file__).resolve().parent))
from db import write  # noqa: E402
from db.schema import DEFAULT_DB_PATH, create_database  # noqa: E402
from db.snapshot import build_empty_snapshot, validate_snapshot  # noqa: E402

FROZEN_SHA256 = "fdd0b971df91cae905e8884258d99d4a562ebdbf8c2122259b02a54955ec3c17"


def main(recalculated_xlsx_path: str) -> None:
    wb = openpyxl.load_workbook(recalculated_xlsx_path, data_only=True)
    sm = wb["Season Matchups"]
    tr = wb["Team Ratings"]
    mc = wb["Market Comparison & Confidence"]

    conn = create_database(DEFAULT_DB_PATH)
    write.insert_model(
        conn, "v35.0", "Frozen v35 baseline (pre-HFA-direct-wiring, pre-RB-Section-5-fix, "
        "pre-1H/2H split -- see prediction_audit/manifests/v35_step1_findings.md for known "
        "limitations carried into this specific frozen version)",
        frozen_at="2026-09-01T13:02:00Z", workbook_sha256=FROZEN_SHA256,
    )

    # ---- Every real game (272 rows) --------------------------------------------------------
    n_games = 0
    row = 3
    while sm.cell(row=row, column=1).value is not None:
        week = int(sm.cell(row=row, column=1).value)
        date = sm.cell(row=row, column=2).value
        away = sm.cell(row=row, column=3).value
        home = sm.cell(row=row, column=4).value
        stadium = sm.cell(row=row, column=5).value
        game_id = f"2026_{week:02d}_{away}_{home}".replace(" ", "")
        write.insert_game(
            conn, game_id, season=2026, week=week, away_team=away, home_team=home,
            game_date=str(date) if date else None, stadium=stadium,
        )
        n_games += 1
        row += 1
    print(f"Inserted {n_games} real games from v35's own Season Matchups.")

    # ---- One fully-populated real prediction (row 3 = Week 1's first game) ----------------
    demo_row = 3
    week = int(sm.cell(row=demo_row, column=1).value)
    away = sm.cell(row=demo_row, column=3).value
    home = sm.cell(row=demo_row, column=4).value
    game_id = f"2026_{week:02d}_{away}_{home}".replace(" ", "")

    home_score = sm.cell(row=demo_row, column=26).value   # Z
    away_score = sm.cell(row=demo_row, column=27).value   # AA
    model_total = sm.cell(row=demo_row, column=28).value  # AB
    model_margin = sm.cell(row=demo_row, column=29).value  # AC

    run_id = write.insert_prediction_run(
        conn, "v35.0", game_id, prediction_timestamp="2026-09-01T13:02:00Z",
        data_cutoff_timestamp="2026-09-01T13:02:00Z",
        data_version="pipeline_run_2026-09-01",
    )
    # Real Win Probability, read directly from Market Comparison & Confidence's own row for
    # this exact game (row 4 there = row 3 here, same 272-game order) -- not recomputed.
    home_wp = mc.cell(row=4, column=13).value
    write.insert_prediction(
        conn, run_id, away_projected_points=away_score, home_projected_points=home_score,
        projected_margin=model_margin, projected_total=model_total,
        home_win_probability=home_wp, away_win_probability=1 - home_wp,
    )

    # Real component contributions -- evaluated directly from v35's own real recalculated
    # cell values for this exact game, matching v35_core_formula_components.csv's own
    # Component_Name list.
    contributions = []
    home_terms = {
        "Rest Effect (Home)": (15, 0.5), "Weather Adj (Home)": (21, 0.5),
        "Home Injury Adj": (22, 1.0), "Division Adj (Home)": (25, 0.5),
        "QB Status/Replacement Adj (Home)": (45, 1.0), "Phase Matchup Adj (Home)": (59, 1.0),
        "OL Pressure Adj (Home)": (67, 1.0), "Explosive Play Adj (Home)": (93, 1.0),
        "HFA Delta (Home)": (96, 1.0), "Road Fatigue Adj (Home)": (100, 1.0),
    }
    for name, (col, sign) in home_terms.items():
        v = sm.cell(row=demo_row, column=col).value
        if isinstance(v, (int, float)):
            contributions.append({
                "component_name": name, "contribution_value": v * sign, "side": "HOME",
            })
    if contributions:
        write.insert_component_contributions(conn, run_id, contributions)

    # Real (partial) state snapshot -- team strength + real environment fields readily
    # available from Team Ratings/Season Matchups; everything else left None per this
    # module's own honesty convention (a full per-player QB/OL/RB/WR-TE/Defense snapshot for
    # every historical game is Step 6's job, not this demo's).
    snapshot = build_empty_snapshot()
    for r in range(3, tr.max_row + 1):
        if tr.cell(row=r, column=1).value == home:
            snapshot["team_strength"]["overall_rating"] = tr.cell(row=r, column=14).value
            break
    snapshot["environment"]["hfa"] = sm.cell(row=demo_row, column=95).value  # CQ, real HFA
    snapshot["environment"]["rest"] = sm.cell(row=demo_row, column=13).value  # Home Rest
    snapshot["environment"]["temperature"] = sm.cell(row=demo_row, column=18).value
    snapshot["environment"]["wind"] = sm.cell(row=demo_row, column=19).value
    problems = validate_snapshot(snapshot)
    if problems:
        raise ValueError(f"Snapshot shape invalid: {problems}")
    write.insert_state_snapshot(conn, run_id, snapshot)

    write.insert_data_quality(
        conn, run_id, missing_data_flag=True,
        data_quality_status="PARTIAL_DEMO -- only team_strength/environment populated, "
        "see this script's own docstring",
    )

    print(f"Demo prediction_run {run_id} for real game {away} @ {home} (Week {week}):")
    print(f"  Home {home_score:.1f} - Away {away_score:.1f}, Model Margin {model_margin:+.1f}, "
          f"Model Total {model_total:.1f}")
    print(f"  {len(contributions)} real component contributions recorded.")
    conn.close()
    print(f"Saved to {DEFAULT_DB_PATH}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: uv run python prediction_audit/seed_v35_demo.py '
              '"path/to/recalculated_v35.xlsx"')
        sys.exit(1)
    main(sys.argv[1])
