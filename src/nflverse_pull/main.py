"""
Single entry point for the nflverse-pull pipeline. Run it any time you want a full refresh:

    uv run python -m nflverse_pull.main "C:\\path\\to\\NFL_Prediction_Model.xlsx"

Two stages:
  1. update_workbook.py -- writes fresh PPG and efficiency data into YoY Baseline Engine /
     Advanced Efficiency Metrics Section 1 (fixed 96/32-row shape, values refreshed in
     place).
  2. QB Index / Replacement Value / Manual Override table / RB Value Index / WR-TE Value
     Index / Kicking Index / Offensive Line Index / Front Seven Index / Secondary Index /
     Special Teams Index / Availability Index -- fully REBUILT from scratch each run (not
     a Section-1-only value refresh), because their row counts are inherently dynamic:
     which players currently qualify as a Starter/Backup, how many games have been played
     this season, etc. Skipped, non-fatally, on a workbook that doesn't have 'Advanced
     Efficiency Metrics' yet (run scripts/build_efficiency_engine.py once first).

     Order matters here and is NOT arbitrary: build_qb_index.py deletes and recreates the
     whole 'QB Index' sheet, which wipes Section 6 (Replacement Value) and Section 7 (Manual
     Override) along with it -- those two must be rebuilt AFTER it, every run, or a scheduled
     run silently leaves the sheet missing its override input cells. This was a real bug
     (found while verifying the RB Value Index build): RB Value Index and the Section 7
     rebuild were never wired into this pipeline at all, so a scheduled run left Section 7
     gone and RB Value Index stale after the very first QB Index rebuild that followed it.

Emailing a results summary is not part of this pipeline -- it's not a required step. If you
want that on demand, run nflverse_pull.email_results directly (see its module docstring for
the Gmail App Password setup it needs).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import openpyxl

from nflverse_pull.update_workbook import EFFICIENCY_SHEET, YOY_SHEET, update_workbook

DEFAULT_YEARS = [2023, 2024, 2025]

# scripts/ isn't part of the installed package (it's one-off/dev tooling, per its own
# module docstrings) -- reached via sys.path, same trick those scripts use to reach src/.
# Only works running from within this project checkout via `uv run`, which is the only way
# this project is ever actually run; not meant to survive a real package install elsewhere.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"


def _rebuild_qb_and_availability(workbook_path: str) -> None:
    wb = openpyxl.load_workbook(workbook_path, read_only=True)
    has_efficiency_engine = EFFICIENCY_SHEET in wb.sheetnames
    wb.close()
    if not has_efficiency_engine:
        print(
            f"Skipped QB Index / RB Value Index / Availability Index: this workbook doesn't "
            f"have '{EFFICIENCY_SHEET}' yet (run scripts/build_efficiency_engine.py once "
            f"first)."
        )
        return

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import add_manual_override_table
    import build_availability_index
    import build_defense_index
    import build_kicking_index
    import build_oline_index
    import build_qb_index
    import build_rb_index
    import build_replacement_value
    import build_secondary_index
    import build_special_teams_index
    import build_wr_te_index

    # NOTE: these scripts each pull their own fixed [2023, 2024, 2025] internally -- the
    # `years` argument to this module's run()/main() does not (yet) override them.
    #
    # Order is load-bearing (see the module docstring): build_qb_index deletes/recreates the
    # whole 'QB Index' sheet, so Section 6 (Replacement Value) and Section 7 (Manual
    # Override) must be rebuilt immediately after it, every run. build_wr_te_index doesn't
    # touch 'Team Ratings' at all, so its position doesn't matter. build_rb_index,
    # build_kicking_index, build_oline_index, build_defense_index, build_secondary_index,
    # and build_special_teams_index, however, EACH rewrite Team Ratings' Net Power Rating
    # (column N) formula wholesale with whatever set of adjustment terms that script knows
    # about -- build_special_teams_index's version is the most complete (includes the QB/
    # RB/Kicking/OL/Front-7/Secondary/Special-Teams terms), so it must run LAST, after
    # build_secondary_index, or an older script's formula would win and silently drop
    # whichever column it doesn't know about (written, but never summed into N). If a
    # future phase adds another Team-Ratings-wired tab, update ITS Net Power Rating formula
    # to include every prior term too, and keep it last here.
    build_qb_index.build(workbook_path)
    build_replacement_value.build(workbook_path)
    add_manual_override_table.build(workbook_path)
    build_rb_index.build(workbook_path)
    build_wr_te_index.build(workbook_path)
    build_kicking_index.build(workbook_path)
    build_oline_index.build(workbook_path)
    build_defense_index.build(workbook_path)
    build_secondary_index.build(workbook_path)
    build_special_teams_index.build(workbook_path)
    build_availability_index.build(workbook_path)


def run(workbook_path: str, years: list[int] | None = None) -> None:
    years = years or DEFAULT_YEARS

    result = update_workbook(workbook_path, years)
    print(
        f"Updated {result['yoy_rows']} rows in '{YOY_SHEET}' and "
        f"{result['efficiency_rows']} rows in '{EFFICIENCY_SHEET}'."
    )

    _rebuild_qb_and_availability(workbook_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook_path", help="Path to the NFL Prediction Model .xlsx file")
    parser.add_argument(
        "--years", type=int, nargs="+", default=None,
        help="Seasons to pull, e.g. --years 2023 2024 2025 (default: 2023 2024 2025)",
    )
    args = parser.parse_args()
    run(args.workbook_path, args.years)


if __name__ == "__main__":
    main()
