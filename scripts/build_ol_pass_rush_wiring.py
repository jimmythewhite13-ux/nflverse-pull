"""
Builds claude_code_spec_ol_vs_pass_rush_matchup.md's core piece: the OL vs. Pass Rush
Matchup differential on "Week 1 Matchups" -- Offensive Line Index's real Pass Protection
Z-score vs. the opponent's real Pass Rush Generation Score (Z), computed separately per team
per game and ADDED alongside (never replacing) the existing Model Home/Away Score formula,
same architectural category as the Defensive Matchup Engine's Pass/Run Matchup Differential
(build_defensive_matchup_wiring.py) -- this is a genuinely different matchup dimension
(protection quality vs. pressure generation), not a duplicate of the QB-vs-PassDefense
differential.

THIS TOUCHES THE CORE PREDICTION FORMULA -- same caution as build_defensive_matchup_wiring.py:
  - Requires "Offensive Line Index" and "Pass Rush Generation Index" to already exist.
  - Uses append_term_once() (imported from build_replacement_value.py, NOT reimplemented) to
    append the new term to Z/AA's EXISTING formula rather than overwrite it.
  - Does NOT overwrite the base blend or any prior adjustment -- the new Home/Away OL
    Pressure Matchup Adjustment (pts) columns are independently visible, mirroring exactly
    how Home/Away Phase-Matchup Adjustment are already structured.

Real per-team-per-game differential, in Z-UNITS (not two points-scale Section-5 Scores
subtracted the way Pass/Run Matchup Differential work -- Offensive Line Index's own Section 5
Team OL Score already blends THREE metrics (Pass Protection + Run Blocking + Sack-Free Rate),
so using it here would contaminate a pass-rush-specific matchup with run-blocking quality;
instead this references JUST Offensive Line Index's own Pass Protection Z column directly):
    Home OL Pressure Matchup Differential (Z) = Home OL Protection Z (Off. Line Index, Section
                                                 5, col B)
                                                 - Away Pass Rush Generation Score (Z)
                                                   (Pass Rush Generation Index, Section 5)
    Away OL Pressure Matchup Differential (Z) = Away OL Protection Z - Home Pass Rush
                                                 Generation Score (Z)

Converted to points via ONE NEW, dedicated conversion constant (Model Assumptions) -- NOT
reused from any other tab's conversion factor (not QB's, not RB's, not the Defensive Matchup
Engine's pass/run constants) -- this measures a structurally different quantity.

Designed to feed the (separately-specced, not-yet-built) Effective QB Rating spec as an
environmental modifier -- NOT wired up here, since that spec hasn't landed. This differential
lives in clearly-labeled, independently-visible columns (Home/Away OL Pressure Matchup
Differential, cols BK/BN) specifically so it can be referenced later without rework.

The position-specific version (LT vs. this specific EDGE rusher) was NOT attempted -- no
free data attributes individual blocker-rusher matchups (same finding Offensive Line Index's
own closing note already states).

NOT YET VALIDATED: same disclaimer as every tab in the Defensive Matchup Engine family.

Usage:
    uv run python scripts/build_ol_pass_rush_wiring.py "C:\\path\\to\\model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_replacement_value import append_term_once  # noqa: E402

OL_INDEX_SHEET = "Offensive Line Index"
PASS_RUSH_GEN_SHEET = "Pass Rush Generation Index"
MATCHUPS_SHEET = "Season Matchups"

# Real Section 5 ranges on each source tab, verified against the live workbook before writing
# this (each tab's own build script already fixes these; documented here since this script
# reads them, not writes them).
OL_SEC5_RANGE = (150, 181)
OL_SCORE_COL, OL_TEAM_COL = "B", "A"  # col B = Pass Protection Z specifically, NOT the
# 3-metric blended Team OL Score (col F) -- deliberate, see module docstring.
PASS_RUSH_GEN_SEC5_RANGE = (150, 181)
PASS_RUSH_GEN_SCORE_COL, PASS_RUSH_GEN_TEAM_COL = "E", "A"

TITLE_FONT = Font(name="Arial", size=10, bold=True)
TITLE_FILL = PatternFill("solid", fgColor="FFD9E1F2")
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="FF1F4E78")
HEADER_ALIGN = Alignment(wrap_text=True, horizontal="center", vertical="center")
FORMULA_FONT = Font(name="Arial", size=10, color="FF000000")
LINK_FONT = Font(name="Arial", size=10, color="FF008000")
NOTE_FONT = Font(name="Arial", size=9, color="FF808080")
ASSUMPTION_FILL = PatternFill("solid", fgColor="FFFFFF00")
INPUT_FONT = Font(name="Arial", size=10, color="FF0000FF")


def add_model_assumptions_weights(wb: openpyxl.Workbook) -> None:
    ws = wb["Model Assumptions"]
    title_row = 122
    ws.merge_cells(f"A{title_row}:D{title_row}")
    title = ws.cell(row=title_row, column=1, value=(
        "OL vs. Pass Rush Matchup Wiring (Week 1 Matchups; pts per pt of Z-score "
        "differential -- see 'Week 1 Matchups' tab)"
    ))
    title.font = HEADER_FONT
    title.fill = HEADER_FILL

    row = 123
    ws.cell(row=row, column=2, value="OL Pressure Matchup Points-to-Game-Points Conversion")
    c = ws.cell(row=row, column=3, value=0.05)
    c.font = INPUT_FONT
    c.fill = ASSUMPTION_FILL
    c.number_format = "0.00"
    n = ws.cell(row=row, column=4, value=(
        "A starting guess, like every other coefficient in this model -- a structurally "
        "different, dedicated constant, NOT reused from any other tab's conversion factor "
        "(not QB's C37/C38 scale, not the Defensive Matchup Engine's pass/run constants "
        "C101/C102). Converts (OL Protection Z - opponent Pass Rush Generation Score Z) "
        "into real game points. Weighted lower than Pass Matchup Differential's own "
        "conversion (C101=0.08) -- this is a supplementary refinement on top of the "
        "QB-vs-Pass-Defense differential, which already captures most of the real pass-"
        "game matchup signal; OL-vs-pass-rush adds a genuinely different but narrower "
        "dimension (protection quality specifically, not overall pass-game outcome). NOT "
        "YET VALIDATED against real outcomes -- see 'Week 1 Matchups' own closing note "
        "and claude_code_spec_ol_vs_pass_rush_matchup.md."
    ))
    n.font = NOTE_FONT
    n.alignment = Alignment(wrap_text=True, vertical="top")


def build(workbook_path: str) -> dict:
    wb = openpyxl.load_workbook(workbook_path)
    for required in (OL_INDEX_SHEET, PASS_RUSH_GEN_SHEET, MATCHUPS_SHEET):
        if required not in wb.sheetnames:
            raise ValueError(
                f"'{required}' not found -- run its own build script first (see this "
                "script's own module docstring for the required order)."
            )

    add_model_assumptions_weights(wb)
    wm = wb[MATCHUPS_SHEET]

    game_rows = []
    row = 3
    while wm.cell(row=row, column=1).value is not None:
        game_rows.append(row)
        row += 1

    ol_score_range = (
        f"'{OL_INDEX_SHEET}'!${OL_SCORE_COL}${OL_SEC5_RANGE[0]}:${OL_SCORE_COL}${OL_SEC5_RANGE[1]}"
    )
    ol_team_range = (
        f"'{OL_INDEX_SHEET}'!${OL_TEAM_COL}${OL_SEC5_RANGE[0]}:${OL_TEAM_COL}${OL_SEC5_RANGE[1]}"
    )
    prg_score_range = (
        f"'{PASS_RUSH_GEN_SHEET}'!${PASS_RUSH_GEN_SCORE_COL}${PASS_RUSH_GEN_SEC5_RANGE[0]}:"
        f"${PASS_RUSH_GEN_SCORE_COL}${PASS_RUSH_GEN_SEC5_RANGE[1]}"
    )
    prg_team_range = (
        f"'{PASS_RUSH_GEN_SHEET}'!${PASS_RUSH_GEN_TEAM_COL}${PASS_RUSH_GEN_SEC5_RANGE[0]}:"
        f"${PASS_RUSH_GEN_TEAM_COL}${PASS_RUSH_GEN_SEC5_RANGE[1]}"
    )

    headers = [
        (61, "Home OL Protection\nZ (ref)"), (62, "Away Pass Rush Gen.\nScore (Z, ref)"),
        (63, "Home OL Pressure\nMatchup Diff. (Z)"),
        (64, "Away OL Protection\nZ (ref)"), (65, "Home Pass Rush Gen.\nScore (Z, ref)"),
        (66, "Away OL Pressure\nMatchup Diff. (Z)"),
        (67, "Home OL Pressure\nMatchup Adj. (pts)"), (68, "Away OL Pressure\nMatchup Adj. (pts)"),
    ]
    for col, label in headers:
        c = wm.cell(row=2, column=col, value=label)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = HEADER_ALIGN

    for r in game_rows:
        # ---- Home OL Protection vs. Away Pass Rush Generation --------------------------
        bi = wm.cell(row=r, column=61, value=(
            f'=IFERROR(INDEX({ol_score_range},MATCH(D{r},{ol_team_range},0)),"")'
        ))
        bj = wm.cell(row=r, column=62, value=(
            f'=IFERROR(INDEX({prg_score_range},MATCH(C{r},{prg_team_range},0)),"")'
        ))
        bk = wm.cell(row=r, column=63, value=f'=IF(OR(BI{r}="",BJ{r}=""),"",BI{r}-BJ{r})')

        # ---- Away OL Protection vs. Home Pass Rush Generation --------------------------
        bl = wm.cell(row=r, column=64, value=(
            f'=IFERROR(INDEX({ol_score_range},MATCH(C{r},{ol_team_range},0)),"")'
        ))
        bm = wm.cell(row=r, column=65, value=(
            f'=IFERROR(INDEX({prg_score_range},MATCH(D{r},{prg_team_range},0)),"")'
        ))
        bn = wm.cell(row=r, column=66, value=f'=IF(OR(BL{r}="",BM{r}=""),"",BL{r}-BM{r})')

        for cell in (bi, bj, bl, bm):
            cell.font = LINK_FONT
            cell.number_format = "0.00;(0.00)"
        for cell in (bk, bn):
            cell.font = FORMULA_FONT
            cell.number_format = "0.00;(0.00)"

        # ---- Converted to points, independently visible (acceptance item #4) ------------
        bo = wm.cell(row=r, column=67, value=(
            f"=IF(BK{r}=\"\",0,BK{r}*'Model Assumptions'!$C$123)"
        ))
        bp = wm.cell(row=r, column=68, value=(
            f"=IF(BN{r}=\"\",0,BN{r}*'Model Assumptions'!$C$123)"
        ))
        bo.font = FORMULA_FONT
        bp.font = FORMULA_FONT
        bo.number_format = "0.00;(0.00)"
        bp.number_format = "0.00;(0.00)"

        # Append to the EXISTING Model Home/Away Score formulas (Z/AA) -- idempotent,
        # never overwrites the base blend or any prior adjustment.
        z_cell = wm.cell(row=r, column=26)  # Z
        aa_cell = wm.cell(row=r, column=27)  # AA
        z_cell.value = append_term_once(z_cell.value, f"+BO{r}")
        aa_cell.value = append_term_once(aa_cell.value, f"+BP{r}")

    # Own note row, placed a few rows below the Defensive Matchup Engine's Part C note (at
    # max(game_rows)+3) so both are visible without one script's rebuild ever touching the
    # other's cell -- each stays independently idempotent regardless of pipeline order.
    note_row_wm = max(game_rows) + 5
    wm.merge_cells(start_row=note_row_wm, start_column=1, end_row=note_row_wm, end_column=20)
    wm_note = wm.cell(row=note_row_wm, column=1, value=(
        "claude_code_spec_ol_vs_pass_rush_matchup.md. Adds a further, independent Home/Away "
        "OL Pressure Matchup Adjustment (BO/BP) to the same Z/AA Model Home/Away Score "
        "formulas the Defensive Matchup Engine's Part C also appends to (see the note "
        "above) -- Offensive Line Index's real Pass Protection Z (Section 5, col B there -- "
        "NOT its 3-metric blended Team OL Score, to avoid contaminating a pass-rush-"
        "specific matchup with run-blocking quality) minus the opponent's real Pass Rush "
        "Generation Score (Z), a new composite built from Pass Defense Matchup's own Sack "
        "Rate/Pressure Proxy/Blitz Rate reference columns (see 'Pass Rush Generation "
        "Index'). NOT YET VALIDATED against real outcomes -- same disclaimer as every tab "
        "in the Defensive Matchup Engine family; this is real, verified-correct plumbing, "
        "not a proven improvement. The position-specific version (LT vs. this specific EDGE "
        "rusher) was NOT attempted anywhere -- no free data attributes individual blocker-"
        "rusher matchups (same finding Offensive Line Index's own closing note states). "
        "Designed to feed a future Effective QB Rating spec as an environmental modifier -- "
        "not wired up yet, since that spec hasn't landed; this differential is independently "
        "visible and clearly labeled (Home/Away OL Pressure Matchup Differential, BK/BN) so "
        "it can be referenced later without rework."
    ))
    wm_note.font = NOTE_FONT
    wm_note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Wired OL vs. Pass Rush Matchup into '{MATCHUPS_SHEET}' (cols BI-BP, "
        f"{len(game_rows)} games)."
    )
    print(f"Saved to {workbook_path}")
    return {"game_rows": game_rows}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: uv run python scripts/build_ol_pass_rush_wiring.py "path/to/workbook.xlsx"')
        sys.exit(1)
    build(sys.argv[1])
