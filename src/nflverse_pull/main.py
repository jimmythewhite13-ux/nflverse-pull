"""
Single entry point for the full nflverse-pull pipeline: writes fresh PPG and efficiency
data into the workbook's placeholder tables (update_workbook.py), then emails a results
summary (email_results.py). This is what scripts/run_scheduled_update.ps1 -- and so the
two Windows Scheduled Tasks -- should invoke; run it yourself any time you want the same
on-demand refresh:

    uv run python -m nflverse_pull.main "C:\\path\\to\\NFL_Prediction_Model.xlsx"

The email step is optional and non-fatal: if NFLVERSE_SMTP_FROM_EMAIL /
NFLVERSE_SMTP_APP_PASSWORD aren't set (see email_results.py), this logs that it's
skipping the email rather than failing the whole run -- the workbook is already updated
by that point regardless.
"""
from __future__ import annotations

import argparse

from nflverse_pull.email_results import build_report_csv, send_report_email
from nflverse_pull.update_workbook import EFFICIENCY_SHEET, YOY_SHEET, update_workbook

DEFAULT_YEARS = [2023, 2024, 2025]


def run(workbook_path: str, years: list[int] | None = None) -> None:
    years = years or DEFAULT_YEARS

    result = update_workbook(workbook_path, years)
    print(
        f"Updated {result['yoy_rows']} rows in '{YOY_SHEET}' and "
        f"{result['efficiency_rows']} rows in '{EFFICIENCY_SHEET}'."
    )

    try:
        csv_text, out = build_report_csv(years)
        send_report_email(csv_text, len(out))
        print(f"Emailed a results summary for {len(out)} teams.")
    except RuntimeError as exc:
        print(f"Skipped the email step: {exc}")


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
