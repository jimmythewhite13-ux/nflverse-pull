"""
Builds "Team-Specific HFA" -- claude_code_spec_game_environment_upgrades.md Part A.
Replaces the single flat Home Field Advantage constant (Model Assumptions C3, currently
applied to every team equally) with each team's own REAL home scoring margin minus away
scoring margin, over the SAME 3-year decay-weighted window already used everywhere else in
this project -- structurally identical to the YoY Baseline Engine's own PPG treatment, just
applied to home/away margin splits instead of season-over-season PPG.

REUSES the existing shared Decay Factor (C20) / Carryover Weight (C21) / Current Season
(C18) assumptions directly -- NOT new constants, per the spec's own explicit instruction.
Section 3's "Projected 3-Yr Baseline" here IS the real, regressed team-specific HFA: the
SAME two-stage regression-toward-mean mechanic (Team History blend via C22, then League
Baseline blend via C21) every other tab's Section 3 already uses is exactly the "regress
toward the league-average HFA, don't let one weird year produce an extreme number"
mechanism the spec calls for -- no new Section 4/5 Z-score composite is needed here, since
this feeds a direct points-value substitute for C3, not a matchup Z-score differential.

Verified live before building this: real 2025 league-wide average HFA (Home Margin - Away
Margin, single season, unregressed) is 4.18 points -- meaningfully higher than the model's
flat 2.0pt assumption, illustrating exactly why a single season's raw HFA shouldn't be
trusted at face value (real variance the 3-yr decay-weighted regression is meant to correct
for).

Also carries a small, real reference table (Section 4: Team | Stadium UTC Offset) feeding
Part C's travel-direction signal on Week 1 Matchups (build_game_environment_wiring.py) --
kept here rather than duplicated onto that sheet directly, since this tab is Team-Ratings-
adjacent, real-data-driven infrastructure other tabs cross-reference, same role Front Seven
Index's own Section 1 already plays for Pass Defense Matchup.

NOT wired into Team Ratings -- HFA is inherently a per-GAME, per-MATCHUP factor (which team
is playing at home this specific week), not a standing team-quality rating; it's referenced
directly by Week 1 Matchups' wiring instead (build_game_environment_wiring.py).

Usage:
    uv run python scripts/build_team_specific_hfa.py "C:\\path\\to\\NFL_Prediction_Model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nflverse_pull.availability import STADIUM_TIMEZONE_UTC_OFFSET  # noqa: E402
from nflverse_pull.pull import (  # noqa: E402
    TEAM_NAMES,
    compute_team_season_home_away_splits,
    fetch_schedules,
)

HISTORICAL_YEARS = [2023, 2024, 2025]
SHEET_NAME = "Team-Specific HFA"
SECONDARY_INDEX_SHEET = "Secondary Index"

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
NOTE_FONT = Font(name="Arial", size=9, color="FF808080")


def _section_title(ws, row: int, last_col: int, text: str) -> None:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = TITLE_FONT
    cell.fill = TITLE_FILL


def _header_row(ws, row: int, headers: list[str], height: float = 28) -> None:
    ws.row_dimensions[row].height = height
    for col, text in enumerate(headers, start=1):
        cell = ws.cell(row=row, column=col, value=text)
        cell.font = HEADER_FONT
        cell.fill = HEADER_FILL
        cell.alignment = HEADER_ALIGN


def _pull_data():
    print(f"Pulling {HISTORICAL_YEARS} schedule data for team-specific HFA...")
    sched = fetch_schedules(HISTORICAL_YEARS)
    splits = compute_team_season_home_away_splits(sched)
    splits = splits.copy()
    splits["HFA"] = splits["Home Margin"] - splits["Away Margin"]
    return splits


def build(workbook_path: str) -> dict:
    season_stats = _pull_data()

    wb = openpyxl.load_workbook(workbook_path)

    if SHEET_NAME in wb.sheetnames:
        del wb[SHEET_NAME]
    for candidate in ("Pass Rush Generation Index", SECONDARY_INDEX_SHEET):
        if candidate in wb.sheetnames:
            insert_after = candidate
            break
    else:
        insert_after = wb.sheetnames[0]
    ws = wb.create_sheet(SHEET_NAME, index=wb.sheetnames.index(insert_after) + 1)
    ws.column_dimensions["A"].width = 20.0

    ws.merge_cells("A1:H1")
    t = ws.cell(row=1, column=1, value=(
        "Team-Specific HFA -- Real 3-Yr Decay-Weighted, Regressed Home/Away Scoring Margin "
        "Split (replaces the flat Home Field Advantage constant, Model Assumptions C3, with "
        "a team-specific one). Reuses the SAME shared Decay Factor (C20) / Carryover Weight "
        "(C21) / Current Season (C18) assumptions -- no new constants."
    ))
    t.font = Font(name="Arial", size=12, bold=True)

    # ==== Section 1: Raw 3-year home/away margin split ======================================
    sec1_first_row = 5
    sec1_last_row = sec1_first_row + len(season_stats) - 1
    _section_title(
        ws, 3, 5,
        "Section 1 — Raw 3-Year Home/Away Scoring Margin Split (real home_score/"
        "away_score from nflverse schedules). HFA (E) = Home Margin - Away Margin, the "
        "raw, UNREGRESSED single-season signal -- Section 3 regresses this toward the "
        "league average, do not use E directly as a team's real HFA.",
    )
    _header_row(ws, 4, ["Team", "Season", "Home Margin", "Away Margin", "HFA (raw)"])
    for i, r in enumerate(season_stats.to_dict("records")):
        row = sec1_first_row + i
        values = [r["Team"], int(r["Season"]), float(r["Home Margin"]), float(r["Away Margin"]),
                  float(r["HFA"])]
        for col, v in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.font = INPUT_FONT
            if col in (3, 4, 5):
                cell.number_format = "0.00"

    team_range = f"$A${sec1_first_row}:$A${sec1_last_row}"
    season_range = f"$B${sec1_first_row}:$B${sec1_last_row}"
    hfa_range = f"$E${sec1_first_row}:$E${sec1_last_row}"

    # ==== Section 2: League average HFA per season ==========================================
    sec2_title_row = sec1_last_row + 2
    sec2_header_row = sec2_title_row + 1
    season_rows = {yr: sec2_header_row + 1 + i for i, yr in enumerate(HISTORICAL_YEARS)}

    _section_title(
        ws, sec2_title_row, 2,
        "Section 2 — League Average HFA per Season (simple average across all 32 teams)",
    )
    _header_row(ws, sec2_header_row, ["Season", "League Avg HFA"], height=20)
    for yr in HISTORICAL_YEARS:
        row = season_rows[yr]
        c = ws.cell(row=row, column=1, value=yr)
        c.font = INPUT_FONT
        f = ws.cell(row=row, column=2, value=f"=AVERAGEIF({season_range},{yr},{hfa_range})")
        f.font = FORMULA_FONT
        f.number_format = "0.00"

    # ==== Section 3: Per-team 3-Yr decay-weighted, regressed HFA baseline ==================
    sec3_title_row = season_rows[HISTORICAL_YEARS[-1]] + 2
    sec3_header_row = sec3_title_row + 1
    sec3_first_row = sec3_header_row + 1
    n_teams = len(TEAM_ORDER)
    sec3_last_row = sec3_first_row + n_teams - 1

    _section_title(
        ws, sec3_title_row, 8,
        "Section 3 — Per-Team 3-Yr Decay-Weighted, Regressed HFA (this IS the real, "
        "team-specific HFA a wiring script should reference -- col H, \"Regressed Team-"
        "Specific HFA\"). A missing year substitutes THAT season's own Section 2 league "
        "average. Uses the SAME Team History blend (C22) and League Baseline blend (C21) "
        "every other tab's Section 3 already uses -- the identical regression-to-mean "
        "mechanism the spec calls for, not a new one.",
    )
    _header_row(ws, sec3_header_row, [
        "Team", "HFA Y-1", "HFA Y-2", "HFA Y-3", "Weighted HFA\nAvg (3-Yr decay)",
        "Team History\nHFA", "League Baseline\nHFA (Y-1)", "Regressed Team-\nSpecific HFA",
    ])
    for i, team in enumerate(TEAM_ORDER):
        row = sec3_first_row + i
        ws.cell(row=row, column=1, value=team).font = FORMULA_FONT

        def _ysub(offset: int, row=row) -> str:
            season_avg_lookup = (
                f"INDEX($B${season_rows[HISTORICAL_YEARS[0]]}:"
                f"$B${season_rows[HISTORICAL_YEARS[-1]]},"
                f"MATCH('Model Assumptions'!$C$18-{offset},"
                f"$A${season_rows[HISTORICAL_YEARS[0]]}:"
                f"$A${season_rows[HISTORICAL_YEARS[-1]]},0))"
            )
            return (
                f"=IF(COUNTIFS({team_range},$A{row},{season_range},"
                f"'Model Assumptions'!$C$18-{offset})=0,{season_avg_lookup},"
                f"SUMIFS({hfa_range},{team_range},$A{row},{season_range},"
                f"'Model Assumptions'!$C$18-{offset}))"
            )

        y1, y2, y3, wavg, th, lb, pb = (get_column_letter(c) for c in range(2, 9))
        f_y1 = ws.cell(row=row, column=2, value=_ysub(1))
        f_y2 = ws.cell(row=row, column=3, value=_ysub(2))
        f_y3 = ws.cell(row=row, column=4, value=_ysub(3))
        f_wavg = ws.cell(row=row, column=5, value=(
            f"=({y1}{row}*1+{y2}{row}*'Model Assumptions'!$C$20+"
            f"{y3}{row}*('Model Assumptions'!$C$20^2))/"
            f"(1+'Model Assumptions'!$C$20+'Model Assumptions'!$C$20^2)"
        ))
        f_th = ws.cell(row=row, column=6, value=(
            f"={y1}{row}*'Model Assumptions'!$C$22+{wavg}{row}*(1-'Model Assumptions'!$C$22)"
        ))
        f_lb = ws.cell(row=row, column=7, value=(
            f"=INDEX($B${season_rows[HISTORICAL_YEARS[0]]}:$B${season_rows[HISTORICAL_YEARS[-1]]},"
            f"MATCH('Model Assumptions'!$C$18-1,$A${season_rows[HISTORICAL_YEARS[0]]}:"
            f"$A${season_rows[HISTORICAL_YEARS[-1]]},0))"
        ))
        f_pb = ws.cell(row=row, column=8, value=(
            f"={th}{row}*'Model Assumptions'!$C$21+{lb}{row}*(1-'Model Assumptions'!$C$21)"
        ))
        for cell in (f_y1, f_y2, f_y3, f_wavg, f_th, f_lb, f_pb):
            cell.font = FORMULA_FONT
            cell.number_format = "0.00"

    # ==== Section 4: Real Stadium UTC Offset reference table (Part C travel direction) =====
    sec4_title_row = sec3_last_row + 2
    sec4_header_row = sec4_title_row + 1
    sec4_first_row = sec4_header_row + 1
    sec4_last_row = sec4_first_row + n_teams - 1

    _section_title(
        ws, sec4_title_row, 2,
        "Section 4 — Real Stadium UTC Offset (standard time; public, unchanging facts) -- "
        "feeds Part C's travel-direction signal on Week 1 Matchups "
        "(build_game_environment_wiring.py). See availability.py's own module docstring "
        "for the real-data reasoning and Arizona's documented DST simplification.",
    )
    _header_row(ws, sec4_header_row, ["Team", "Stadium UTC\nOffset (Standard Time)"], height=20)
    abbr_of = {v: k for k, v in TEAM_NAMES.items()}
    for i, team in enumerate(TEAM_ORDER):
        row = sec4_first_row + i
        ws.cell(row=row, column=1, value=team).font = INPUT_FONT
        offset_cell = ws.cell(
            row=row, column=2, value=int(STADIUM_TIMEZONE_UTC_OFFSET[abbr_of[team]])
        )
        offset_cell.font = INPUT_FONT
        offset_cell.number_format = "0"

    # ---- Closing note --------------------------------------------------------------------
    note_row = sec4_last_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=8)
    note = ws.cell(row=note_row, column=1, value=(
        "claude_code_spec_game_environment_upgrades.md Part A (+ Part C's reference table "
        "in Section 4). Verified live before building this: real 2025 league-wide average "
        "HFA (Home Margin - Away Margin, single season, UNREGRESSED) is 4.18 points, "
        "meaningfully higher than the model's own flat 2.0pt Home Field Advantage constant "
        "(Model Assumptions C3, which stays in place as the model-wide fallback/reference "
        "-- not deleted) -- real illustration of why a single season's raw HFA shouldn't be "
        "trusted at face value. Section 3's Regressed Team-Specific HFA (col H) reuses the "
        "IDENTICAL Team-History-blend (C22) + League-Baseline-blend (C21) regression-to-"
        "mean mechanism every other tab's own Section 3 already uses -- no new constants, "
        "per the spec's own explicit instruction. NOT wired into Team Ratings -- HFA is "
        "inherently a per-game factor (whichever team is playing at home this specific "
        "week), referenced directly by Week 1 Matchups' own wiring instead."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Built '{SHEET_NAME}': Section 1 {len(season_stats)} rows, Section 3/4 {n_teams} "
        "teams. NOT wired into Team Ratings -- feeds Week 1 Matchups' game-environment "
        "wiring directly."
    )
    print(f"Saved to {workbook_path}")
    return {
        "sec3_range": (sec3_first_row, sec3_last_row),
        "sec4_range": (sec4_first_row, sec4_last_row),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: uv run python scripts/build_team_specific_hfa.py "path/to/workbook.xlsx"')
        sys.exit(1)
    build(sys.argv[1])
