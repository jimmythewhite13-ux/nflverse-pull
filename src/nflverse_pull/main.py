"""
Single entry point for the nflverse-pull pipeline: writes fresh PPG and efficiency data
into the workbook's Section 1 input tables (update_workbook.py). This is what
scripts/run_scheduled_update.ps1 -- and so the two Windows Scheduled Tasks -- invoke; run
it yourself any time you want the same on-demand refresh:

    uv run python -m nflverse_pull.main "C:\\path\\to\\NFL_Prediction_Model.xlsx"

Emailing a results summary is no longer part of this pipeline -- it's not a required step.
If you want that on demand, run nflverse_pull.email_results directly (see its module
docstring for the Gmail App Password setup it needs).
"""
from __future__ import annotations

import argparse

from nflverse_pull.update_workbook import EFFICIENCY_SHEET, YOY_SHEET, update_workbook

DEFAULT_YEARS = [2023, 2024, 2025]


def run(workbook_path: str, years: list[int] | None = None) -> None:
    years = years or DEFAULT_YEARS

    result = update_workbook(workbook_path, years)
    print(
        f"Updated {result['yoy_rows']} rows in '{YOY_SHEET}' and "
        f"{result['efficiency_rows']} rows in '{EFFICIENCY_SHEET}'."
    )


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
