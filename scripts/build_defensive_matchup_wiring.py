"""
Builds Part C of claude_code_spec_defensive_matchup_engine.md: the phase-specific matchup
differential on "Week 1 Matchups" -- pass offense vs. pass defense, run offense vs. run
defense, computed separately per team per game and added ALONGSIDE (never replacing) the
existing PPG-based Model Home/Away Score formula.

THIS TOUCHES THE CORE PREDICTION FORMULA -- treated with more caution than a typical
adjustment column, per the spec's own explicit instruction:
  - Requires "Pass Defense Matchup", "Run Defense Matchup", "QB Index", and "RB Value Index"
    to already exist (built by their own scripts first).
  - Uses append_term_once() (imported from build_replacement_value.py, NOT reimplemented --
    same idempotency bug that function was written to fix applies here too) to append the
    new term to Z/AA's EXISTING formula rather than overwrite it, so every prior adjustment
    (rest/travel/weather/injury/division/QB Replacement Value) stays intact.
  - Does NOT overwrite the base Home Off (PPG) vs. Away Def (PPG allowed) blend -- the new
    Home/Away Phase-Matchup Adjustment (pts) columns are independently visible new columns,
    exactly so a future backtest can compare "PPG-only" against "PPG + phase-matchup"
    directly (see claude_code_spec_defensive_matchup_engine.md's own reasoning for why this
    comparison must stay possible).

Real per-team-per-game differentials (using CURRENT team ratings, i.e. each source tab's own
live, recalculating Section 5 Score -- not a historical snapshot):
    Home Pass Matchup Differential = Home Starter's QB Index Score
                                      - Away Pass Defense Matchup Score
    Away Pass Matchup Differential = Away Starter's QB Index Score
                                      - Home Pass Defense Matchup Score
    Home Run Matchup Differential  = Home Starter's RB Index Score
                                      - Away Run Defense Matchup Score
    Away Run Matchup Differential  = Away Starter's RB Index Score
                                      - Home Run Defense Matchup Score

"Home Starter" / "Away Starter" are looked up via QB Index's / RB Value Index's own real
Team|Role helper key (Section 5's last column, e.g. "Buffalo Bills|Starter") -- the SAME
single-criteria-MATCH pattern those tabs' own Section 6/closing logic already established,
avoiding a two-criteria array/CSE formula.

Converted to points via TWO NEW, dedicated conversion constants (Model Assumptions, NOT
reused from any other tab's conversion factor -- these measure a structurally different
quantity, a phase-specific MATCHUP differential between two Section-5 point scores, not a
team-level quality adjustment or a Replacement Value swap).

NOT YET VALIDATED: there is no backtesting harness in this project yet to prove this phase-
specific approach actually improves predictions over the existing PPG-based blend -- stated
explicitly in the new Week 1 Matchups note, per the spec's own instruction. This is real,
verified-correct plumbing a future backtest will need, not a proven improvement.

Usage:
    uv run python scripts/build_defensive_matchup_wiring.py "C:\\path\\to\\model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_replacement_value import append_term_once  # noqa: E402

QB_INDEX_SHEET = "QB Index"
RB_INDEX_SHEET = "RB Value Index"
PASS_DEFENSE_SHEET = "Pass Defense Matchup"
RUN_DEFENSE_SHEET = "Run Defense Matchup"
MATCHUPS_SHEET = "Season Matchups"

# Score column + Team|Role (or Team) key column on each source tab's own Section 5 -- the
# ROW range itself is discovered dynamically per build (see _find_section5_range's own
# docstring for why: it used to be hardcoded here and silently drifted stale).
QB_SCORE_COL, QB_KEY_COL = "I", "K"
# RB Index's own Score/Team|Role-key COLUMNS shift with METRICS' length (each metric adds a
# 7-column Section 3 block and a 1-column Section 5 Z block) -- these were J/L when RB Index
# had 4 METRICS; claude_code_spec_route_redzone_usage.md added Red-Zone Carry Share as a 5th
# (weight defaults to 0, but it's still a real METRICS entry, so it still shifts the layout),
# moving them to K/M.
RB_SCORE_COL, RB_KEY_COL = "K", "M"
PASS_DEF_SCORE_COL, PASS_DEF_TEAM_COL = "H", "A"
RUN_DEF_SCORE_COL, RUN_DEF_TEAM_COL = "H", "A"

TITLE_FONT = Font(name="Arial", size=10, bold=True)
TITLE_FILL = PatternFill("solid", fgColor="FFD9E1F2")
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="FF1F4E78")
HEADER_ALIGN = Alignment(wrap_text=True, horizontal="center", vertical="center")
INPUT_FONT = Font(name="Arial", size=10, color="FF0000FF")
FORMULA_FONT = Font(name="Arial", size=10, color="FF000000")
LINK_FONT = Font(name="Arial", size=10, color="FF008000")
NOTE_FONT = Font(name="Arial", size=9, color="FF808080")
ASSUMPTION_FILL = PatternFill("solid", fgColor="FFFFFF00")


def _find_section5_range(ws) -> tuple[int, int]:
    """
    claude_code_spec_hfa_wiring_fix.md's own bug report (Root Cause 2): the module-level
    QB_SEC5_RANGE/RB_SEC5_RANGE constants used to be hand-verified against the live workbook
    once, then hardcoded -- but a player-level tab's Section 5 row count tracks its own
    CURRENT real-roster population (current_roster.py's live depth-chart pull), which drifts
    over time with real roster churn, independent of any code change. Caught live: RB Value
    Index's Section 5 had grown by 2 real rows (337-400) since RB_SEC5_RANGE=(335,398) was
    set, silently excluding the real LAST 2 players from every INDEX/MATCH search over that
    range -- including Jacory Croskey-Merritt, a real Washington Commanders RB starter with
    real volume, whose Matchup Differential came back blank not because his data was missing
    but because his own real Section 5 row (399) fell outside the stale hardcoded range.
    Discovers the real (first_row, last_row) fresh every build instead, so this can't drift
    stale again.
    """
    for r in range(1, ws.max_row + 1):
        v = ws.cell(row=r, column=1).value
        if isinstance(v, str) and v.strip().startswith("Section 5"):
            first_row = r + 2
            last_row = first_row
            while ws.cell(row=last_row + 1, column=1).value is not None:
                last_row += 1
            return first_row, last_row
    raise ValueError(f"Could not find a 'Section 5' title row in '{ws.title}'.")


def add_model_assumptions_weights(wb: openpyxl.Workbook) -> None:
    ws = wb["Model Assumptions"]
    title_row = 100
    ws.merge_cells(f"A{title_row}:D{title_row}")
    title = ws.cell(row=title_row, column=1, value=(
        "Defensive Matchup Engine -- Week 1 Matchups Wiring (Part C; pts per pt of "
        "Score-vs-Score differential -- see 'Week 1 Matchups' tab)"
    ))
    title.font = HEADER_FONT
    title.fill = HEADER_FILL

    rows = [
        (101, "Pass Matchup Points-to-Game-Points Conversion", 0.08,
         "A starting guess, like every other coefficient in this model -- a "
         "structurally different, dedicated constant, NOT reused from any other "
         "tab's conversion factor. Converts (Starter QB Index Score - opponent Pass "
         "Defense Matchup Score) into real game points. NOT YET VALIDATED against "
         "real outcomes -- see 'Week 1 Matchups' own closing note and "
         "claude_code_spec_defensive_matchup_engine.md."),
        (102, "Run Matchup Points-to-Game-Points Conversion", 0.06,
         "A starting guess, like every other coefficient in this model -- a "
         "structurally different, dedicated constant, NOT reused from any other "
         "tab's conversion factor. Converts (Starter RB Index Score - opponent Run "
         "Defense Matchup Score) into real game points. Smaller than the pass "
         "conversion (C101), reflecting the run game's generally smaller real "
         "game-point impact per snap. NOT YET VALIDATED against real outcomes."),
    ]
    for row, label, value, note in rows:
        ws.cell(row=row, column=2, value=label)
        c = ws.cell(row=row, column=3, value=value)
        c.font = INPUT_FONT
        c.fill = ASSUMPTION_FILL
        c.number_format = "0.00"
        n = ws.cell(row=row, column=4, value=note)
        n.font = NOTE_FONT
        n.alignment = Alignment(wrap_text=True, vertical="top")


def build(workbook_path: str) -> dict:
    wb = openpyxl.load_workbook(workbook_path)
    for required in (QB_INDEX_SHEET, RB_INDEX_SHEET, PASS_DEFENSE_SHEET, RUN_DEFENSE_SHEET,
                      MATCHUPS_SHEET):
        if required not in wb.sheetnames:
            raise ValueError(
                f"'{required}' not found -- run its own build script first "
                "(see this script's own module docstring for the required order)."
            )

    add_model_assumptions_weights(wb)
    wm = wb[MATCHUPS_SHEET]

    game_rows = []
    row = 3
    while wm.cell(row=row, column=1).value is not None:
        game_rows.append(row)
        row += 1

    qb_sec5 = _find_section5_range(wb[QB_INDEX_SHEET])
    rb_sec5 = _find_section5_range(wb[RB_INDEX_SHEET])
    pass_def_sec5 = _find_section5_range(wb[PASS_DEFENSE_SHEET])
    run_def_sec5 = _find_section5_range(wb[RUN_DEFENSE_SHEET])

    qb_score_range = f"'{QB_INDEX_SHEET}'!${QB_SCORE_COL}${qb_sec5[0]}:${QB_SCORE_COL}${qb_sec5[1]}"
    qb_key_range = f"'{QB_INDEX_SHEET}'!${QB_KEY_COL}${qb_sec5[0]}:${QB_KEY_COL}${qb_sec5[1]}"
    rb_score_range = f"'{RB_INDEX_SHEET}'!${RB_SCORE_COL}${rb_sec5[0]}:${RB_SCORE_COL}${rb_sec5[1]}"
    rb_key_range = f"'{RB_INDEX_SHEET}'!${RB_KEY_COL}${rb_sec5[0]}:${RB_KEY_COL}${rb_sec5[1]}"
    pass_def_score_range = (
        f"'{PASS_DEFENSE_SHEET}'!${PASS_DEF_SCORE_COL}${pass_def_sec5[0]}:"
        f"${PASS_DEF_SCORE_COL}${pass_def_sec5[1]}"
    )
    pass_def_team_range = (
        f"'{PASS_DEFENSE_SHEET}'!${PASS_DEF_TEAM_COL}${pass_def_sec5[0]}:"
        f"${PASS_DEF_TEAM_COL}${pass_def_sec5[1]}"
    )
    run_def_score_range = (
        f"'{RUN_DEFENSE_SHEET}'!${RUN_DEF_SCORE_COL}${run_def_sec5[0]}:"
        f"${RUN_DEF_SCORE_COL}${run_def_sec5[1]}"
    )
    run_def_team_range = (
        f"'{RUN_DEFENSE_SHEET}'!${RUN_DEF_TEAM_COL}${run_def_sec5[0]}:"
        f"${RUN_DEF_TEAM_COL}${run_def_sec5[1]}"
    )

    headers = [
        (47, "Home Starter QB\nIndex Score (ref)"), (48, "Away Pass Defense\nMatchup Score (ref)"),
        (49, "Home Pass Matchup\nDifferential"),
        (50, "Away Starter QB\nIndex Score (ref)"), (51, "Home Pass Defense\nMatchup Score (ref)"),
        (52, "Away Pass Matchup\nDifferential"),
        (53, "Home Starter RB\nIndex Score (ref)"), (54, "Away Run Defense\nMatchup Score (ref)"),
        (55, "Home Run Matchup\nDifferential"),
        (56, "Away Starter RB\nIndex Score (ref)"), (57, "Home Run Defense\nMatchup Score (ref)"),
        (58, "Away Run Matchup\nDifferential"),
        (59, "Home Phase-Matchup\nAdjustment (pts)"), (60, "Away Phase-Matchup\nAdjustment (pts)"),
    ]
    for col, label in headers:
        c = wm.cell(row=2, column=col, value=label)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = HEADER_ALIGN

    for r in game_rows:
        # ---- Pass side ---------------------------------------------------------------
        au = wm.cell(row=r, column=47, value=(
            f'=IFERROR(INDEX({qb_score_range},MATCH(D{r}&"|Starter",{qb_key_range},0)),"")'
        ))
        av = wm.cell(row=r, column=48, value=(
            f'=IFERROR(INDEX({pass_def_score_range},MATCH(C{r},{pass_def_team_range},0)),"")'
        ))
        aw = wm.cell(row=r, column=49, value=f'=IF(OR(AU{r}="",AV{r}=""),"",AU{r}-AV{r})')

        ax = wm.cell(row=r, column=50, value=(
            f'=IFERROR(INDEX({qb_score_range},MATCH(C{r}&"|Starter",{qb_key_range},0)),"")'
        ))
        ay = wm.cell(row=r, column=51, value=(
            f'=IFERROR(INDEX({pass_def_score_range},MATCH(D{r},{pass_def_team_range},0)),"")'
        ))
        az = wm.cell(row=r, column=52, value=f'=IF(OR(AX{r}="",AY{r}=""),"",AX{r}-AY{r})')

        # ---- Run side -----------------------------------------------------------------
        ba = wm.cell(row=r, column=53, value=(
            f'=IFERROR(INDEX({rb_score_range},MATCH(D{r}&"|Starter",{rb_key_range},0)),"")'
        ))
        bb = wm.cell(row=r, column=54, value=(
            f'=IFERROR(INDEX({run_def_score_range},MATCH(C{r},{run_def_team_range},0)),"")'
        ))
        bc = wm.cell(row=r, column=55, value=f'=IF(OR(BA{r}="",BB{r}=""),"",BA{r}-BB{r})')

        bd = wm.cell(row=r, column=56, value=(
            f'=IFERROR(INDEX({rb_score_range},MATCH(C{r}&"|Starter",{rb_key_range},0)),"")'
        ))
        be = wm.cell(row=r, column=57, value=(
            f'=IFERROR(INDEX({run_def_score_range},MATCH(D{r},{run_def_team_range},0)),"")'
        ))
        bf = wm.cell(row=r, column=58, value=f'=IF(OR(BD{r}="",BE{r}=""),"",BD{r}-BE{r})')

        for cell in (au, av, ax, ay, ba, bb, bd, be):
            cell.font = LINK_FONT
            cell.number_format = "0.0;(0.0)"
        for cell in (aw, az, bc, bf):
            cell.font = FORMULA_FONT
            cell.number_format = "0.0;(0.0)"

        # ---- Converted to points, independently visible (spec's own acceptance item #4)
        bg = wm.cell(row=r, column=59, value=(
            f'=IF(AW{r}="",0,AW{r}*\'Model Assumptions\'!$C$101)'
            f'+IF(BC{r}="",0,BC{r}*\'Model Assumptions\'!$C$102)'
        ))
        bh = wm.cell(row=r, column=60, value=(
            f'=IF(AZ{r}="",0,AZ{r}*\'Model Assumptions\'!$C$101)'
            f'+IF(BF{r}="",0,BF{r}*\'Model Assumptions\'!$C$102)'
        ))
        bg.font = FORMULA_FONT
        bh.font = FORMULA_FONT
        bg.number_format = "0.00;(0.00)"
        bh.number_format = "0.00;(0.00)"

        # Append to the EXISTING Model Home/Away Score formulas (Z/AA) -- idempotent,
        # never overwrites the base PPG-based blend or any prior adjustment (rest/
        # travel/weather/injury/division/QB Replacement Value all stay intact).
        z_cell = wm.cell(row=r, column=26)  # Z
        aa_cell = wm.cell(row=r, column=27)  # AA
        z_cell.value = append_term_once(z_cell.value, f"+BG{r}")
        aa_cell.value = append_term_once(aa_cell.value, f"+BH{r}")

    note_row_wm = max(game_rows) + 3
    wm.merge_cells(start_row=note_row_wm, start_column=1, end_row=note_row_wm, end_column=20)
    wm_note = wm.cell(row=note_row_wm, column=1, value=(
        "claude_code_spec_defensive_matchup_engine.md Part C. NOT YET VALIDATED: there is "
        "no backtesting harness in this project yet to prove phase-specific pass/run "
        "matchups actually improve predictions over the existing PPG-based Off/Def blend "
        "-- this is real, verified-correct plumbing (every input traces to a real, already-"
        "verified Section 5 Score on QB Index / RB Value Index / Pass Defense Matchup / "
        "Run Defense Matchup), NOT a proven improvement. Home/Away Phase-Matchup "
        "Adjustment (BG/BH) is ADDED to the existing Model Home/Away Score (Z/AA) "
        "alongside every prior adjustment (rest/travel/weather/injury/division/QB "
        "Replacement Value) -- it does NOT replace the base Home Off (PPG) vs. Away Def "
        "(PPG allowed) blend, specifically so a future backtest can compare 'PPG-only' "
        "against 'PPG + phase-matchup' directly by comparing Z/AA against (Z-BG)/(AA-BH). "
        "Uses CURRENT team ratings -- these are live formulas, not a snapshot: AU/AV/AX/AY/"
        "BA/BB/BD/BE re-evaluate automatically as QB Index / RB Value Index / Pass Defense "
        "Matchup / Run Defense Matchup's own current-season inputs change, nothing needs "
        "re-entering per week. A blank differential (a team missing a current Starter, or "
        "not yet in a source tab's Section 5) contributes 0 to the adjustment rather than "
        "a formula error."
    ))
    wm_note.font = NOTE_FONT
    wm_note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Wired Defensive Matchup Engine Part C into '{MATCHUPS_SHEET}' "
        f"(cols AU-BH, {len(game_rows)} games)."
    )
    print(f"Saved to {workbook_path}")
    return {"game_rows": game_rows}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            'Usage: uv run python scripts/build_defensive_matchup_wiring.py '
            '"path/to/workbook.xlsx"'
        )
        sys.exit(1)
    build(sys.argv[1])
