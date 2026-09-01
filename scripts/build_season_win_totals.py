"""
Builds "Season Win Totals" -- claude_code_spec_season_win_total_moneyline.md Part A.
Dependency check (per the spec's own explicit instruction): requires Full Season Matchups
(Season Matchups, all 18 real weeks) and the Win Probability output from the Market/
Confidence Engine spec (Market Comparison & Confidence's own real per-game Win Probability
column) -- both already built and delivered earlier this session; verified live before
building this rather than assumed.

Standard, well-established technique, not reinvented: a team's Expected Win Total is the SUM
of its own real per-game win probability across all 18 games -- pure aggregation of numbers
that already exist, no new prediction logic. For a HOME game, that's Market Comparison &
Confidence's own Win Probability (Home) column directly; for an AWAY game, it's 1 minus that
same column (the home team's own win probability implies the away team's complement). A real
SUMPRODUCT over Season Matchups' own real Home/Away Team columns handles both sides without
a helper column per team.

HONESTY NOTE, stated on the tab itself per the spec's own explicit instruction: this
projection is currently built almost entirely from preseason/historical-baseline data (every
team's real Games Played this season is 0 before Week 1 kicks off, so claude_code_spec_
current_season_blending.md's own Blend Weight is 0 everywhere right now) -- it is closer to a
true PRESEASON projection than an in-season one. Team Ratings' own real Current-Season Blend
Weight (col I) is referenced directly here as a real, checkable "how much current-season
data has actually been blended in yet" signal, not a fabricated maturity score -- re-running
this script later in the season, once real games accumulate, will reflect real in-season
performance more and more automatically, without any code change.

Usage:
    uv run python scripts/build_season_win_totals.py "C:\\path\\to\\NFL_Prediction_Model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

SEASON_SHEET = "Season Matchups"
MARKET_SHEET = "Market Comparison & Confidence"
TEAM_RATINGS_SHEET = "Team Ratings"
SHEET_NAME = "Season Win Totals"

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

TITLE_FONT = Font(name="Arial", size=10, bold=True)
TITLE_FILL = PatternFill("solid", fgColor="FFD9E1F2")
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="FF1F4E78")
HEADER_ALIGN = Alignment(wrap_text=True, horizontal="center", vertical="center")
INPUT_FONT = Font(name="Arial", size=10, color="FF0000FF")
FORMULA_FONT = Font(name="Arial", size=10, color="FF000000")
LINK_FONT = Font(name="Arial", size=10, color="FF008000")
NOTE_FONT = Font(name="Arial", size=9, color="FF808080")
NEEDS_UPDATE_FILL = PatternFill("solid", fgColor="FFFFA500")


def _find_col(ws, row: int, header_text: str) -> int:
    for c in range(1, ws.max_column + 1):
        if ws.cell(row=row, column=c).value == header_text:
            return c
    raise ValueError(f"Could not find column {header_text!r} on row {row} of '{ws.title}'.")


def build(workbook_path: str) -> dict:
    wb = openpyxl.load_workbook(workbook_path)
    for required in (SEASON_SHEET, MARKET_SHEET, TEAM_RATINGS_SHEET):
        if required not in wb.sheetnames:
            raise ValueError(
                f"'{required}' not found -- run its own build script first (see this "
                "script's own module docstring for the required dependency check)."
            )

    market = wb[MARKET_SHEET]
    mk_home_col = _find_col(market, 2, "Home Team")
    mk_away_col = _find_col(market, 2, "Away Team")
    mk_wp_col = _find_col(market, 2, "Win Probability\n(Home)")
    mk_first, mk_last = 3, 3
    while market.cell(row=mk_last + 1, column=1).value is not None:
        mk_last += 1
    from openpyxl.utils import get_column_letter
    mk_home_letter = get_column_letter(mk_home_col)
    mk_away_letter = get_column_letter(mk_away_col)
    mk_wp_letter = get_column_letter(mk_wp_col)
    mk_home_range = f"'{MARKET_SHEET}'!${mk_home_letter}${mk_first}:${mk_home_letter}${mk_last}"
    mk_away_range = f"'{MARKET_SHEET}'!${mk_away_letter}${mk_first}:${mk_away_letter}${mk_last}"
    mk_wp_range = f"'{MARKET_SHEET}'!${mk_wp_letter}${mk_first}:${mk_wp_letter}${mk_last}"

    # Read back any existing real sportsbook win-total lines before rebuilding.
    readback: dict[str, float] = {}
    if SHEET_NAME in wb.sheetnames:
        old = wb[SHEET_NAME]
        line_col = None
        for c in range(1, old.max_column + 1):
            if old.cell(row=2, column=c).value == "Sportsbook Win\nTotal Line":
                line_col = c
                break
        if line_col:
            r = 3
            while old.cell(row=r, column=1).value is not None:
                v = old.cell(row=r, column=line_col).value
                if v not in (None, ""):
                    readback[old.cell(row=r, column=1).value] = v
                r += 1
        del wb[SHEET_NAME]

    ws = wb.create_sheet(SHEET_NAME, index=wb.sheetnames.index(MARKET_SHEET) + 1)
    ws.column_dimensions["A"].width = 22.0

    ws.merge_cells("A1:H1")
    t = ws.cell(row=1, column=1, value=(
        "Season Win Totals -- claude_code_spec_season_win_total_moneyline.md Part A. "
        "Expected Win Total = real SUM of a team's own per-game Win Probability across "
        "all 18 real games (Market Comparison & Confidence's own real column) -- pure "
        "aggregation, no new prediction logic."
    ))
    t.font = Font(name="Arial", size=12, bold=True)

    _section_row = 3
    ws.merge_cells(start_row=_section_row, start_column=1, end_row=_section_row, end_column=6)
    sec = ws.cell(row=_section_row, column=1, value=(
        "Section 1 — Real Expected Win Total per Team, vs. the Sportsbook's Posted Season "
        "Win Total Line"
    ))
    sec.font = TITLE_FONT
    sec.fill = TITLE_FILL

    header_row = _section_row + 1
    headers = [
        "Team", "Expected Win\nTotal (real, sum of\nWin Probability)",
        "Sportsbook Win\nTotal Line", "Win Total\nEdge", "Current-Season\nBlend Weight (ref)",
        "Projection Maturity",
    ]
    ws.row_dimensions[header_row].height = 32
    for col, htext in enumerate(headers, start=1):
        c = ws.cell(row=header_row, column=col, value=htext)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = HEADER_ALIGN

    first_row = header_row + 1
    for i, team in enumerate(TEAM_ORDER):
        row = first_row + i
        tc = ws.cell(row=row, column=1, value=team)
        tc.font = FORMULA_FONT

        expected = ws.cell(row=row, column=2, value=(
            f'=SUMPRODUCT(({mk_home_range}=A{row})*{mk_wp_range})+'
            f'SUMPRODUCT(({mk_away_range}=A{row})*(1-{mk_wp_range}))'
        ))
        expected.font = LINK_FONT
        expected.number_format = "0.0"

        line = ws.cell(row=row, column=3, value=readback.get(team))
        line.font = INPUT_FONT
        line.fill = NEEDS_UPDATE_FILL
        line.number_format = "0.0"

        edge = ws.cell(row=row, column=4, value=f'=IF(C{row}="","",B{row}-C{row})')
        edge.font = FORMULA_FONT
        edge.number_format = "0.0;(0.0)"

        blend = ws.cell(row=row, column=5, value=(
            f"=IFERROR(INDEX('{TEAM_RATINGS_SHEET}'!$I$3:$I$34,"
            f"MATCH(A{row},'{TEAM_RATINGS_SHEET}'!$A$3:$A$34,0)),0)"
        ))
        blend.font = LINK_FONT
        blend.number_format = "0.00"

        maturity = ws.cell(row=row, column=6, value=(
            f'=IF(E{row}=0,"Preseason baseline only (0 real games played this season)",'
            f'IF(E{row}<0.4,"Early season -- mostly historical/preseason baseline",'
            f'IF(E{row}<0.7,"Mid-season -- meaningful blend of history and real current '
            f'performance","Late season -- mostly real current-season performance")))'
        ))
        maturity.font = FORMULA_FONT

    last_row = first_row + len(TEAM_ORDER) - 1

    note_row = last_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=8)
    note = ws.cell(row=note_row, column=1, value=(
        "claude_code_spec_season_win_total_moneyline.md Part A. Expected Win Total is a "
        "real SUM of that team's own real per-game Win Probability (Market Comparison & "
        "Confidence's own column) across all 18 real 2026 games -- no new prediction logic, "
        "pure aggregation. HONESTY NOTE (per the spec's own explicit instruction): this "
        "projection is currently built almost entirely from preseason/historical-baseline "
        "data -- Team Ratings' own real Current-Season Blend Weight (col I, referenced "
        "directly in col E here) is 0 for every team before Week 1 kicks off, so today this "
        "is closer to a true preseason projection than an in-season one. Re-running this "
        "script later in the season, once real games accumulate and claude_code_spec_"
        "current_season_blending.md's own Blend Weight rises, will make this reflect real "
        "in-season performance more and more automatically, without any code change -- the "
        "Projection Maturity column (F) states plainly, per row, which regime a team's own "
        "projection is currently in."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(f"Built '{SHEET_NAME}': {len(TEAM_ORDER)} teams.")
    print(f"Saved to {workbook_path}")
    return {"first_row": first_row, "last_row": last_row}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: uv run python scripts/build_season_win_totals.py "path/to/workbook.xlsx"')
        sys.exit(1)
    build(sys.argv[1])
