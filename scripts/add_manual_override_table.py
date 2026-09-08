"""
Builds Part 2 of claude_code_spec_current_roster_fix.md: a manual Starter/Backup override
input table on the "QB Index" tab. Blank = use the pulled current-roster data (Part 1).
Filled in = takes precedence -- real news (a beat-writer report, a surprise trade, a camp
competition outcome) moves faster than any pull job.

GENERALIZED per claude_code_spec_consolidated_fixes.md Part 2: originally QB Index-only
(and hardcoded to the Starter/Backup pair) -- `build()` now takes a `sheet_name` and the
real `role_labels` that position uses (e.g. ["Starter", "Backup"] for QB/RB, ["WR1", "WR2",
"WR3", "TE1"] for the combined WR-TE tab, ["K1"] for Kicking, ["LT", "LG", "C", "RG", "RT"]
for Offensive Line), building one "Manual {role} Override" column per real role instead of
always exactly two -- matches current_roster.resolve_scored_population's own generalized
override-column convention exactly (see that function's docstring), so a table built here
is directly consumable by it with no translation layer.

This table is standalone infrastructure only for whichever tab's build script doesn't yet
read it back into its own population resolution -- each tab's own build script is what
actually consumes it (see e.g. build_qb_index.py's _read_existing_overrides()).

Requires the target sheet to already exist.

Usage (QB Index, the original call site -- other tabs call build() directly from Python,
see main.py):
    uv run python scripts/add_manual_override_table.py "C:\\path\\to\\NFL_Prediction_Model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

TITLE_FONT = Font(name="Arial", size=10, bold=True)
TITLE_FILL = PatternFill("solid", fgColor="FFD9E1F2")
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="FF1F4E78")
HEADER_ALIGN = Alignment(wrap_text=True, horizontal="center", vertical="center")
INPUT_FONT = Font(name="Arial", size=10, color="FF0000FF")
NOTE_FONT = Font(name="Arial", size=9, color="FF808080")

TEAM_ORDER = [
    "Buffalo Bills", "Miami Dolphins", "New England Patriots", "New York Jets",
    "Baltimore Ravens", "Cincinnati Bengals", "Cleveland Browns", "Pittsburgh Steelers",
    "Houston Texans", "Indianapolis Colts", "Jacksonville Jaguars", "Tennessee Titans",
    "Denver Broncos", "Kansas City Chiefs", "Las Vegas Raiders", "Los Angeles Chargers",
    "Dallas Cowboys", "New York Giants", "Philadelphia Eagles", "Washington Commanders",
    "Chicago Bears", "Detroit Lions", "Green Bay Packers", "Minnesota Vikings",
    "Atlanta Falcons", "Carolina Panthers", "New Orleans Saints", "Tampa Bay Buccaneers",
    "Arizona Cardinals", "Los Angeles Rams", "San Francisco 49ers", "Seattle Seahawks",
]

SHEET_NAME = "QB Index"
DEFAULT_ROLE_LABELS = ["Starter", "Backup"]
SECTION_MARKER = "Section 7 \u2014 Manual Roster Override"


def read_existing_overrides(
    wb: openpyxl.Workbook, sheet_name: str, role_labels: list[str]
) -> pd.DataFrame:
    """
    Reads Section 7's Manual Roster Override table back from `sheet_name` (if present)
    BEFORE that tab's own build script deletes and rebuilds the whole sheet -- so any values
    a user has already filled in survive a re-run rather than being silently wiped along
    with the rest of the sheet. Shared by every tab's build script (claude_code_spec_
    consolidated_fixes.md Part 2) instead of each reimplementing this lookup.

    Output columns: Team | Manual {role} Override... (one per `role_labels`, matching
    current_roster.resolve_scored_population's own generalized override-column convention).
    A sheet with no Section 7 yet (first-ever build) returns an empty DataFrame with the
    right columns, not an error.
    """
    columns = ["Team"] + [f"Manual {role} Override" for role in role_labels]
    if sheet_name not in wb.sheetnames:
        return pd.DataFrame(columns=columns)
    ws = wb[sheet_name]

    title_row = None
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and v.startswith(SECTION_MARKER):
            title_row = r
            break
    if title_row is None:
        return pd.DataFrame(columns=columns)

    header_row = title_row + 1
    first_data_row = header_row + 1
    rows = []
    r = first_data_row
    while ws.cell(row=r, column=1).value is not None:
        rows.append({
            col: ws.cell(row=r, column=c).value for c, col in enumerate(columns, start=1)
        })
        r += 1
    return pd.DataFrame(rows, columns=columns) if rows else pd.DataFrame(columns=columns)


def build(
    workbook_path: str,
    sheet_name: str = SHEET_NAME,
    role_labels: list[str] = DEFAULT_ROLE_LABELS,
) -> None:
    wb = openpyxl.load_workbook(workbook_path)
    ws = wb[sheet_name]

    headers = ["Team"] + [f"Manual {role} Override" for role in role_labels]
    last_col = len(headers)

    # Idempotent: if this section already exists (a re-run), clear it and its data below
    # before rebuilding, rather than appending a second copy further down the sheet.
    existing_title_row = None
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and v.startswith(SECTION_MARKER):
            existing_title_row = r
            break
    if existing_title_row is not None:
        for r in range(existing_title_row, ws.max_row + 1):
            for c in range(1, ws.max_column + 1):
                ws.cell(row=r, column=c, value=None)
        title_row = existing_title_row
    else:
        # Find the first fully-blank row after all existing content, with a one-row gap.
        title_row = ws.max_row + 2

    ws.merge_cells(start_row=title_row, start_column=1, end_row=title_row, end_column=last_col)
    t = ws.cell(row=title_row, column=1, value=(
        f"{SECTION_MARKER} (blank = use the pulled current-roster data; filled in = takes "
        "precedence over it -- a beat-writer report or camp-competition outcome will always "
        "be more current than the last pull. See claude_code_spec_consolidated_fixes.md "
        "Part 2 -- this tab's own build script reads this table back before rebuilding the "
        "sheet and feeds it to current_roster.resolve_scored_population.)"
    ))
    t.font = TITLE_FONT
    t.fill = TITLE_FILL

    header_row = title_row + 1
    ws.row_dimensions[header_row].height = 20
    for col, label in enumerate(headers, start=1):
        c = ws.cell(row=header_row, column=col, value=label)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = HEADER_ALIGN

    first_data_row = header_row + 1
    for i, team in enumerate(TEAM_ORDER):
        row = first_data_row + i
        ws.cell(row=row, column=1, value=team).font = INPUT_FONT
        for col in range(2, last_col + 1):
            ws.cell(row=row, column=col, value=None).font = INPUT_FONT
    last_data_row = first_data_row + len(TEAM_ORDER) - 1

    wb.save(workbook_path)
    print(f"Built '{SECTION_MARKER}' on '{sheet_name}' ({', '.join(role_labels)}): "
          f"rows {first_data_row}-{last_data_row}.")
    print(f"Saved to {workbook_path}")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: uv run python scripts/add_manual_override_table.py "path/to/workbook.xlsx"')
        sys.exit(1)
    build(sys.argv[1])
