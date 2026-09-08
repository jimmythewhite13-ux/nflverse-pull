"""
Builds claude_code_spec_qb_environment_model.md Part C: the actual combination --
Effective QB Rating = QB Environment Model's opponent-independent baseline (Raw Talent
Score + Situational Adjustments) + a game-specific OL vs. Pass Rush modifier (scaled up for
a QB with a high Sack Tendency) + a game-specific Weather-on-Passing modifier (scaled by the
team's real current-season pass rate).

THIS TOUCHES THE CORE PREDICTION FORMULA -- same caution as every other Week 1 Matchups
wiring script in this family:
  - Requires "QB Environment Model", "Offensive Line Index" (Pass Protection Z via the OL
    vs. Pass Rush Matchup wiring's own BK/BN columns), and the OL vs. Pass Rush Matchup
    wiring to already exist.
  - Writes 12 NEW, independently-visible reference/modifier columns (BQ-CB) so every piece
    of the combination stays inspectable, same transparency standard as every prior wiring
    script.
  - Then OVERWRITES Week 1 Matchups' existing "Home/Away Starter QB Index Score (ref)"
    cells (AU/AX, written by build_defensive_matchup_wiring.py) to reference the new Home/
    Away Effective QB Rating (CA/CB) INSTEAD -- per the spec's own explicit instruction:
    "This Effective Rating replaces the raw QB Index score specifically in the Pass Matchup
    Differential calculation ... update that one reference." Verified live before writing
    this: AU/AX are read ONLY by AW/AZ (Home/Away Pass Matchup Differential = AU-AV / AX-AY)
    -- nothing else in the workbook references AU/AX, so overwriting their formula in place
    is safe and automatically propagates through AW/AZ -> BG/BH -> Z/AA without touching
    any of those downstream formulas. Everywhere else that currently points to QB Index's
    raw Score (Team Ratings' QB Replacement Value, Week 1 Matchups' own QB Replacement Adj
    columns AS/AT, etc.) is UNTOUCHED -- this script writes ONLY to BQ-CB and overwrites
    ONLY AU/AX.

Real per-team-per-game combination:
    Home OL Modifier (scaled) = Home OL Pressure Matchup Adjustment (BK, from build_ol_
                                 pass_rush_wiring.py) * (1 + MAX(0, Home Starter's real Sack
                                 Rate Z) * Sack-Tendency Scaling Constant)
    Home Weather-on-Passing Modifier = existing Weather Adj (U) * Home team's real current-
                                        season pass rate (dropbacks / (dropbacks+carries),
                                        from QB Environment Model's own Section 1 Dropbacks
                                        and RB Value Index's own Section 1 Carries) *
                                        Weather-on-Passing Scaling Constant
    Home Effective QB Rating = QB Environment Model's Home Starter Baseline (Section 6)
                                + Home OL Modifier (scaled) + Home Weather-on-Passing
                                Modifier
(same shape for Away, using each side's own opponent -- Home's OL modifier uses the SAME
Home-vs-Away-pass-rush differential build_ol_pass_rush_wiring.py already computed, just
scaled here by the Home Starter's own Sack Tendency; not recomputed).

Converted via TWO NEW, dedicated tunable constants (Model Assumptions C133/C134) -- NOT
reused from any other tab's conversion factor.

NOT YET VALIDATED: same disclaimer as every tab in the Defensive Matchup Engine family.

Usage:
    uv run python scripts/build_effective_qb_rating_wiring.py "C:\\path\\to\\model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

QB_ENV_SHEET = "QB Environment Model"
RB_INDEX_SHEET = "RB Value Index"
MATCHUPS_SHEET = "Season Matchups"

# QB Environment Model's own real Section 1 (Team=C, Season=D, Dropbacks=M -- added
# specifically for this wiring script, since QB Index's own Section 1 doesn't expose real
# Dropbacks; see that tab's own module docstring), Section 5 (Sack Rate Z=G, Team|Role
# key=M), and Section 6 (Baseline=J, Team|Role key=K). Generous "5:500" ranges rather than
# exact literal row bounds -- INDEX/MATCH and SUMIFS both tolerate blank rows past the real
# data harmlessly, avoiding yet another hardcoded-row-range constant that needs updating
# whenever the real pulled data's row count shifts.
QB_ENV_SEC1_TEAM_COL, QB_ENV_SEC1_SEASON_COL, QB_ENV_SEC1_DROPBACKS_COL = "C", "D", "M"
QB_ENV_SEC5_SACK_Z_COL, QB_ENV_SEC5_KEY_COL = "G", "M"
QB_ENV_SEC6_BASELINE_COL, QB_ENV_SEC6_KEY_COL = "J", "K"
RB_SEC1_TEAM_COL, RB_SEC1_SEASON_COL, RB_SEC1_CARRIES_COL = "C", "D", "E"

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
    title_row = 132
    ws.merge_cells(f"A{title_row}:D{title_row}")
    title = ws.cell(row=title_row, column=1, value=(
        "Effective QB Rating Wiring (Week 1 Matchups Part C combination -- see 'Week 1 "
        "Matchups' tab)"
    ))
    title.font = HEADER_FONT
    title.fill = HEADER_FILL

    rows = [
        (133, "Sack Tendency OL-Modifier Scaling Constant", 0.25,
         "A starting guess, like every other coefficient in this model. The OL vs. Pass "
         "Rush Matchup Adjustment is multiplied by (1 + MAX(0, Starter's real Sack Rate "
         "Z) * this constant) -- a QB with an average or below-average sack rate gets NO "
         "amplification (multiplier stays 1x); a QB 1 SD above average sack rate gets "
         "his OL modifier amplified by 25% at the default. Never dampens a low-sack "
         "QB's OL modifier below 1x -- only amplifies a high-sack QB's."),
        (134, "Weather-on-Passing Scaling Constant", 0.5,
         "A starting guess, like every other coefficient in this model. This is an "
         "ADDITIONAL modifier on top of the existing generic Weather Adj (U, applied "
         "evenly to both teams via Z/AA's own U/2 term) -- deliberately moderate (0.5, "
         "not 1.0) to avoid double-penalizing bad weather twice. Multiplies the "
         "existing Weather Adj by the team's own real current-season pass rate "
         "(dropbacks / (dropbacks+carries)) -- a pass-heavy team's effective QB rating "
         "is hurt more by wind/precip than a run-heavy team's."),
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
    for required in (QB_ENV_SHEET, RB_INDEX_SHEET, MATCHUPS_SHEET):
        if required not in wb.sheetnames:
            raise ValueError(
                f"'{required}' not found -- run its own build script first (see this "
                "script's own module docstring for the required order)."
            )
    wm = wb[MATCHUPS_SHEET]
    if wm.cell(row=2, column=61).value is None:
        raise ValueError(
            "'Week 1 Matchups' col BI (Home OL Protection Z) not found -- run "
            "build_ol_pass_rush_wiring.py first."
        )

    add_model_assumptions_weights(wb)

    game_rows = []
    row = 3
    while wm.cell(row=row, column=1).value is not None:
        game_rows.append(row)
        row += 1

    dropbacks_range = (
        f"'{QB_ENV_SHEET}'!${QB_ENV_SEC1_DROPBACKS_COL}5:${QB_ENV_SEC1_DROPBACKS_COL}500"
    )
    qb_env_team_range = f"'{QB_ENV_SHEET}'!${QB_ENV_SEC1_TEAM_COL}5:${QB_ENV_SEC1_TEAM_COL}500"
    qb_env_season_range = (
        f"'{QB_ENV_SHEET}'!${QB_ENV_SEC1_SEASON_COL}5:${QB_ENV_SEC1_SEASON_COL}500"
    )
    carries_range = f"'{RB_INDEX_SHEET}'!${RB_SEC1_CARRIES_COL}5:${RB_SEC1_CARRIES_COL}500"
    rb_team_range = f"'{RB_INDEX_SHEET}'!${RB_SEC1_TEAM_COL}5:${RB_SEC1_TEAM_COL}500"
    rb_season_range = f"'{RB_INDEX_SHEET}'!${RB_SEC1_SEASON_COL}5:${RB_SEC1_SEASON_COL}500"

    sack_z_range = f"'{QB_ENV_SHEET}'!${QB_ENV_SEC5_SACK_Z_COL}5:${QB_ENV_SEC5_SACK_Z_COL}500"
    sec5_key_range = f"'{QB_ENV_SHEET}'!${QB_ENV_SEC5_KEY_COL}5:${QB_ENV_SEC5_KEY_COL}500"
    baseline_range = f"'{QB_ENV_SHEET}'!${QB_ENV_SEC6_BASELINE_COL}5:${QB_ENV_SEC6_BASELINE_COL}500"
    sec6_key_range = f"'{QB_ENV_SHEET}'!${QB_ENV_SEC6_KEY_COL}5:${QB_ENV_SEC6_KEY_COL}500"

    headers = [
        (69, "Home Team\nPass Rate"), (70, "Away Team\nPass Rate"),
        (71, "Home Starter\nSack Rate Z (ref)"), (72, "Away Starter\nSack Rate Z (ref)"),
        (73, "Home OL Modifier\n(Scaled, pts)"), (74, "Away OL Modifier\n(Scaled, pts)"),
        (75, "Home Weather-on-\nPassing Mod. (pts)"), (76, "Away Weather-on-\nPassing Mod. (pts)"),
        (77, "Home QB Environment-\nAdj. Baseline (ref)"),
        (78, "Away QB Environment-\nAdj. Baseline (ref)"),
        (79, "Home Effective\nQB Rating"), (80, "Away Effective\nQB Rating"),
    ]
    for col, label in headers:
        c = wm.cell(row=2, column=col, value=label)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = HEADER_ALIGN

    for r in game_rows:
        # ---- Real team pass rate (dropbacks / (dropbacks+carries)), most recent season --
        home_db = (
            f'SUMIFS({dropbacks_range},{qb_env_team_range},D{r},{qb_env_season_range},'
            f"'Model Assumptions'!$C$18-1)"
        )
        home_car = (
            f'SUMIFS({carries_range},{rb_team_range},D{r},{rb_season_range},'
            f"'Model Assumptions'!$C$18-1)"
        )
        away_db = (
            f'SUMIFS({dropbacks_range},{qb_env_team_range},C{r},{qb_env_season_range},'
            f"'Model Assumptions'!$C$18-1)"
        )
        away_car = (
            f'SUMIFS({carries_range},{rb_team_range},C{r},{rb_season_range},'
            f"'Model Assumptions'!$C$18-1)"
        )
        bq = wm.cell(row=r, column=69, value=(
            f'=IFERROR({home_db}/({home_db}+{home_car}),"")'
        ))
        br = wm.cell(row=r, column=70, value=(
            f'=IFERROR({away_db}/({away_db}+{away_car}),"")'
        ))

        # ---- Home/Away Starter's real Sack Rate Z (reference only) ----------------------
        bs = wm.cell(row=r, column=71, value=(
            f'=IFERROR(INDEX({sack_z_range},MATCH(D{r}&"|Starter",{sec5_key_range},0)),"")'
        ))
        bt = wm.cell(row=r, column=72, value=(
            f'=IFERROR(INDEX({sack_z_range},MATCH(C{r}&"|Starter",{sec5_key_range},0)),"")'
        ))

        for cell in (bq, br, bs, bt):
            cell.font = LINK_FONT
        bq.number_format = "0.00"
        br.number_format = "0.00"
        bs.number_format = "0.00"
        bt.number_format = "0.00"

        # ---- OL Modifier, scaled by Sack Tendency (never dampens a low-sack QB below 1x)
        bu = wm.cell(row=r, column=73, value=(
            f'=IF(BK{r}="","",BK{r}*(1+MAX(0,IF(BS{r}="",0,BS{r}))*'
            f"'Model Assumptions'!$C$133))"
        ))
        bv = wm.cell(row=r, column=74, value=(
            f'=IF(BN{r}="","",BN{r}*(1+MAX(0,IF(BT{r}="",0,BT{r}))*'
            f"'Model Assumptions'!$C$133))"
        ))

        # ---- Weather-on-Passing Modifier (additional, on top of the existing generic U/2)
        bw = wm.cell(row=r, column=75, value=(
            f'=IF(BQ{r}="",0,U{r}*BQ{r}*\'Model Assumptions\'!$C$134)'
        ))
        bx = wm.cell(row=r, column=76, value=(
            f'=IF(BR{r}="",0,U{r}*BR{r}*\'Model Assumptions\'!$C$134)'
        ))

        for cell in (bu, bv, bw, bx):
            cell.font = FORMULA_FONT
            cell.number_format = "0.00;(0.00)"

        # ---- QB Environment Model's own opponent-independent baseline (reference) --------
        by = wm.cell(row=r, column=77, value=(
            f'=IFERROR(INDEX({baseline_range},MATCH(D{r}&"|Starter",{sec6_key_range},0)),"")'
        ))
        bz = wm.cell(row=r, column=78, value=(
            f'=IFERROR(INDEX({baseline_range},MATCH(C{r}&"|Starter",{sec6_key_range},0)),"")'
        ))
        by.font = LINK_FONT
        bz.font = LINK_FONT
        by.number_format = "0.0;(0.0)"
        bz.number_format = "0.0;(0.0)"

        # ---- Effective QB Rating = Baseline + OL Modifier (scaled) + Weather Modifier ----
        ca = wm.cell(row=r, column=79, value=(
            f'=IF(BY{r}="","",BY{r}+IF(BU{r}="",0,BU{r})+BW{r})'
        ))
        cb = wm.cell(row=r, column=80, value=(
            f'=IF(BZ{r}="","",BZ{r}+IF(BV{r}="",0,BV{r})+BX{r})'
        ))
        ca.font = FORMULA_FONT
        cb.font = FORMULA_FONT
        ca.number_format = "0.0;(0.0)"
        cb.number_format = "0.0;(0.0)"

        # ---- Replace the ONE reference the spec calls for: Home/Away Starter QB Index
        # Score (AU/AX) now point at the new Effective QB Rating instead. AW/AZ (Pass
        # Matchup Differential = AU-AV / AX-AY) automatically pick up the new value with no
        # changes of their own -- verified live before writing this that nothing else in
        # the workbook reads AU/AX.
        au_cell = wm.cell(row=r, column=47, value=f"=CA{r}")
        ax_cell = wm.cell(row=r, column=50, value=f"=CB{r}")
        au_cell.font = LINK_FONT
        ax_cell.font = LINK_FONT
        au_cell.number_format = "0.0;(0.0)"
        ax_cell.number_format = "0.0;(0.0)"

    note_row_wm = max(game_rows) + 7
    wm.merge_cells(start_row=note_row_wm, start_column=1, end_row=note_row_wm, end_column=20)
    wm_note = wm.cell(row=note_row_wm, column=1, value=(
        "claude_code_spec_qb_environment_model.md Part C. Home/Away Effective QB Rating "
        "(CA/CB) = QB Environment Model's opponent-independent baseline (BY/BZ, Section 6 "
        "there: Raw Talent Score + Situational Adjustments) + this game's OL vs. Pass Rush "
        "Matchup Adjustment (BK/BN, from build_ol_pass_rush_wiring.py), scaled up by "
        "(1 + MAX(0, Starter's real Sack Rate Z) * C133) so a QB who holds the ball longer "
        "is hurt more by a bad protection matchup than a quick-release QB facing the same "
        "matchup + a NEW Weather-on-Passing Modifier (BW/BX) that scales the EXISTING "
        "generic Weather Adj (U, already applied evenly to both teams via Z/AA) by this "
        "team's own real current-season pass rate (BQ/BR) and a dedicated constant (C134) "
        "-- a pass-heavy team's effective rating is hurt more by bad weather than a "
        "run-heavy team's. Home/Away Starter QB Index Score (AU/AX) NOW REFERENCE the new "
        "Effective QB Rating instead of QB Index directly -- per the spec's own explicit "
        "instruction, this is the ONLY reference that changed; everywhere else that "
        "referenced QB Index's raw Score (Team Ratings' QB Replacement Value, this sheet's "
        "own QB Replacement Adj columns AS/AT) is untouched. QB Index's own Section 5 "
        "Score itself was never modified anywhere in this chain. NOT YET VALIDATED against "
        "real outcomes -- same disclaimer as every tab in the Defensive Matchup Engine "
        "family; this is real, verified-correct plumbing, not a proven improvement."
    ))
    wm_note.font = NOTE_FONT
    wm_note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Wired Effective QB Rating into '{MATCHUPS_SHEET}' (cols BQ-CB, {len(game_rows)} "
        "games) and replaced AU/AX's reference from QB Index's raw Score to the new "
        "Effective QB Rating."
    )
    print(f"Saved to {workbook_path}")
    return {"game_rows": game_rows}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            'Usage: uv run python scripts/build_effective_qb_rating_wiring.py '
            '"path/to/workbook.xlsx"'
        )
        sys.exit(1)
    build(sys.argv[1])
