"""
Builds claude_code_spec_explosive_play_engine.md Part C: the Explosive Play Matchup
differential on "Week 1 Matchups" -- offense's real Explosive Pass/Run Rate vs. the
opponent's real Explosive-Prevention composite, computed separately per phase (pass, run)
per team per game and ADDED alongside (never replacing) the existing PPG-based, phase-
matchup, OL-vs-pass-rush, and Effective-QB-Rating-driven Pass Matchup Differential
predictions -- same architectural category, same caution, as every prior Week 1 Matchups
wiring script in this family.

Deliberately does NOT rebuild QB/weather/coverage adjustments -- those are already handled
by claude_code_spec_qb_environment_model.md (Effective QB Rating, which already folds in
the OL-vs-pass-rush and Weather-on-Passing modifiers) and claude_code_spec_ol_vs_pass_rush_
matchup.md. This is its OWN additive term, not a re-implementation of either. Coverage-
specific adjustment remains confirmed not buildable -- not attempted here either.

Real per-team-per-game differentials, in Z-UNITS (same convention build_ol_pass_rush_
wiring.py already established -- Explosive Play Matchup's own Section 5 deliberately has no
points-scale column, so this operates on raw Z's, converted to points here via new dedicated
constants):
    Home Pass Explosive Matchup Differential = Home Offense's Explosive Pass Rate Z
                                                - Away's Pass Prevention Composite Z
    Away Pass Explosive Matchup Differential = Away Offense's Explosive Pass Rate Z
                                                - Home's Pass Prevention Composite Z
    Home Run Explosive Matchup Differential  = Home Offense's Explosive Run Rate Z
                                                - Away's Run Prevention Z
    Away Run Explosive Matchup Differential  = Away Offense's Explosive Run Rate Z
                                                - Home's Run Prevention Z

Converted to points via TWO NEW, dedicated conversion constants (Model Assumptions, NOT
reused from any other tab's conversion factor), summed into ONE Home/Away Explosive Play
Matchup Adjustment (pts) column each, then appended to the existing Model Home/Away Score
formulas (Z/AA) via append_term_once -- idempotent, never overwrites any prior adjustment.

NOT YET VALIDATED: same disclaimer as every tab in the Defensive Matchup Engine family.

Usage:
    uv run python scripts/build_explosive_play_matchup_wiring.py "C:\\path\\to\\model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_replacement_value import append_term_once  # noqa: E402

EXPLOSIVE_SHEET = "Explosive Play Matchup"
MATCHUPS_SHEET = "Week 1 Matchups"

# Explosive Play Matchup's own real Section 5 layout (verified against that tab's own build
# script): 32 teams, rows 150-181. Team=A, Explosive Pass Rate (Off) Z=B, Explosive Run Rate
# (Off) Z=C, Pass Prevention Composite Z=H, Run Prevention Z=I.
EXP_SEC5_RANGE = (150, 181)
EXP_TEAM_COL = "A"
EXP_PASS_OFF_Z_COL, EXP_RUN_OFF_Z_COL = "B", "C"
EXP_PASS_PREVENTION_COL, EXP_RUN_PREVENTION_COL = "H", "I"

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
    title_row = 139
    ws.merge_cells(f"A{title_row}:D{title_row}")
    title = ws.cell(row=title_row, column=1, value=(
        "Explosive Play Matchup Wiring (Week 1 Matchups; pts per pt of Z-score "
        "differential -- see 'Week 1 Matchups' tab)"
    ))
    title.font = HEADER_FONT
    title.fill = HEADER_FILL

    rows = [
        (140, "Pass Explosive Matchup Points-to-Game-Points Conversion", 0.06,
         "A starting guess, like every other coefficient in this model -- a "
         "structurally different, dedicated constant, NOT reused from any other tab's "
         "conversion factor. Converts (offense's real Explosive Pass Rate Z - "
         "opponent's real Pass Prevention Composite Z) into real game points. NOT YET "
         "VALIDATED against real outcomes -- see 'Week 1 Matchups' own closing note "
         "and claude_code_spec_explosive_play_engine.md."),
        (141, "Run Explosive Matchup Points-to-Game-Points Conversion", 0.05,
         "A starting guess, like every other coefficient in this model -- a "
         "structurally different, dedicated constant. Converts (offense's real "
         "Explosive Run Rate Z - opponent's real Run Prevention Z) into real game "
         "points. Smaller than the pass conversion (C140), same reasoning as the "
         "Defensive Matchup Engine's own smaller run conversion (C102) -- the run "
         "game's generally smaller real game-point impact per snap."),
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
    for required in (EXPLOSIVE_SHEET, MATCHUPS_SHEET):
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

    def _rng(col: str) -> str:
        return f"'{EXPLOSIVE_SHEET}'!${col}${EXP_SEC5_RANGE[0]}:${col}${EXP_SEC5_RANGE[1]}"

    team_range = _rng(EXP_TEAM_COL)
    pass_off_range = _rng(EXP_PASS_OFF_Z_COL)
    run_off_range = _rng(EXP_RUN_OFF_Z_COL)
    pass_prevention_range = _rng(EXP_PASS_PREVENTION_COL)
    run_prevention_range = _rng(EXP_RUN_PREVENTION_COL)

    headers = [
        (81, "Home Explosive\nPass Z (ref)"), (82, "Away Pass\nPrevention Z (ref)"),
        (83, "Home Pass Explosive\nMatchup Diff. (Z)"),
        (84, "Away Explosive\nPass Z (ref)"), (85, "Home Pass\nPrevention Z (ref)"),
        (86, "Away Pass Explosive\nMatchup Diff. (Z)"),
        (87, "Home Explosive\nRun Z (ref)"), (88, "Away Run\nPrevention Z (ref)"),
        (89, "Home Run Explosive\nMatchup Diff. (Z)"),
        (90, "Away Explosive\nRun Z (ref)"), (91, "Home Run\nPrevention Z (ref)"),
        (92, "Away Run Explosive\nMatchup Diff. (Z)"),
        (93, "Home Explosive Play\nMatchup Adj. (pts)"),
        (94, "Away Explosive Play\nMatchup Adj. (pts)"),
    ]
    for col, label in headers:
        c = wm.cell(row=2, column=col, value=label)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = HEADER_ALIGN

    for r in game_rows:
        # ---- Pass side: Home offense vs. Away's Pass Prevention ------------------------
        cc = wm.cell(row=r, column=81, value=(
            f'=IFERROR(INDEX({pass_off_range},MATCH(D{r},{team_range},0)),"")'
        ))
        cd = wm.cell(row=r, column=82, value=(
            f'=IFERROR(INDEX({pass_prevention_range},MATCH(C{r},{team_range},0)),"")'
        ))
        ce = wm.cell(row=r, column=83, value=f'=IF(OR(CC{r}="",CD{r}=""),"",CC{r}-CD{r})')

        cf = wm.cell(row=r, column=84, value=(
            f'=IFERROR(INDEX({pass_off_range},MATCH(C{r},{team_range},0)),"")'
        ))
        cg = wm.cell(row=r, column=85, value=(
            f'=IFERROR(INDEX({pass_prevention_range},MATCH(D{r},{team_range},0)),"")'
        ))
        ch = wm.cell(row=r, column=86, value=f'=IF(OR(CF{r}="",CG{r}=""),"",CF{r}-CG{r})')

        # ---- Run side: Home offense vs. Away's Run Prevention ---------------------------
        ci = wm.cell(row=r, column=87, value=(
            f'=IFERROR(INDEX({run_off_range},MATCH(D{r},{team_range},0)),"")'
        ))
        cj = wm.cell(row=r, column=88, value=(
            f'=IFERROR(INDEX({run_prevention_range},MATCH(C{r},{team_range},0)),"")'
        ))
        ck = wm.cell(row=r, column=89, value=f'=IF(OR(CI{r}="",CJ{r}=""),"",CI{r}-CJ{r})')

        cl = wm.cell(row=r, column=90, value=(
            f'=IFERROR(INDEX({run_off_range},MATCH(C{r},{team_range},0)),"")'
        ))
        cm = wm.cell(row=r, column=91, value=(
            f'=IFERROR(INDEX({run_prevention_range},MATCH(D{r},{team_range},0)),"")'
        ))
        cn = wm.cell(row=r, column=92, value=f'=IF(OR(CL{r}="",CM{r}=""),"",CL{r}-CM{r})')

        for cell in (cc, cd, cf, cg, ci, cj, cl, cm):
            cell.font = LINK_FONT
            cell.number_format = "0.00;(0.00)"
        for cell in (ce, ch, ck, cn):
            cell.font = FORMULA_FONT
            cell.number_format = "0.00;(0.00)"

        # ---- Converted to points, independently visible (acceptance item #6) ------------
        co = wm.cell(row=r, column=93, value=(
            f'=IF(CE{r}="",0,CE{r}*\'Model Assumptions\'!$C$140)'
            f'+IF(CK{r}="",0,CK{r}*\'Model Assumptions\'!$C$141)'
        ))
        cp = wm.cell(row=r, column=94, value=(
            f'=IF(CH{r}="",0,CH{r}*\'Model Assumptions\'!$C$140)'
            f'+IF(CN{r}="",0,CN{r}*\'Model Assumptions\'!$C$141)'
        ))
        co.font = FORMULA_FONT
        cp.font = FORMULA_FONT
        co.number_format = "0.00;(0.00)"
        cp.number_format = "0.00;(0.00)"

        # Append to the EXISTING Model Home/Away Score formulas (Z/AA) -- idempotent,
        # never overwrites any prior adjustment.
        z_cell = wm.cell(row=r, column=26)  # Z
        aa_cell = wm.cell(row=r, column=27)  # AA
        z_cell.value = append_term_once(z_cell.value, f"+CO{r}")
        aa_cell.value = append_term_once(aa_cell.value, f"+CP{r}")

    note_row_wm = max(game_rows) + 9
    wm.merge_cells(start_row=note_row_wm, start_column=1, end_row=note_row_wm, end_column=20)
    wm_note = wm.cell(row=note_row_wm, column=1, value=(
        "claude_code_spec_explosive_play_engine.md Part C. NOT YET VALIDATED: no "
        "backtesting harness exists yet to prove explosive-play matchups improve "
        "predictions -- this is real, verified-correct plumbing, not a proven improvement. "
        "Home/Away Explosive Play Matchup Adjustment (CO/CP) is ADDED to the existing Model "
        "Home/Away Score (Z/AA) alongside every prior adjustment (rest/travel/weather/"
        "injury/division/QB Replacement Value/Phase-Matchup/OL Pressure Matchup) -- it does "
        "NOT replace any of them. Deliberately does NOT rebuild QB/weather/coverage "
        "adjustments -- Effective QB Rating (claude_code_spec_qb_environment_model.md) "
        "already folds in the OL-vs-pass-rush and Weather-on-Passing modifiers; this is its "
        "OWN additive term for a genuinely different signal (offense's real big-play rate "
        "vs. opponent's real big-play prevention). Coverage-specific adjustment remains "
        "confirmed not buildable. Uses CURRENT team ratings -- these are live formulas, not "
        "a snapshot: CC/CD/CF/CG/CI/CJ/CL/CM re-evaluate automatically as Explosive Play "
        "Matchup's own current-season inputs change. A blank differential (a team not yet "
        "in Explosive Play Matchup's Section 5) contributes 0 to the adjustment rather than "
        "a formula error."
    ))
    wm_note.font = NOTE_FONT
    wm_note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Wired Explosive Play Matchup into '{MATCHUPS_SHEET}' (cols CC-CP, "
        f"{len(game_rows)} games)."
    )
    print(f"Saved to {workbook_path}")
    return {"game_rows": game_rows}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            'Usage: uv run python scripts/build_explosive_play_matchup_wiring.py '
            '"path/to/workbook.xlsx"'
        )
        sys.exit(1)
    build(sys.argv[1])
