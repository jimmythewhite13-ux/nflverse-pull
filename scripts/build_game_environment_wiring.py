"""
Builds claude_code_spec_game_environment_upgrades.md Parts A/B/C/D on "Week 1 Matchups".
Part E (Weather-on-Passing) is explicitly NOT rebuilt here -- already covered by
claude_code_spec_qb_environment_model.md's Effective QB Rating wiring (build_effective_qb_
rating_wiring.py's Weather-on-Passing Modifier, cols BW/BX, Model Assumptions C134). This
script's own Weather Adj change (Part D) only touches the generic snow/humidity mechanics,
never anything QB-specific.

Requires "Team-Specific HFA" and the current "Availability Index" (with its Section 2b
Consecutive Road Games column) to already exist.

THIS TOUCHES THE CORE PREDICTION FORMULA -- same caution as every other Week 1 Matchups
wiring script in this family. Two different edit disciplines, deliberately kept separate:
  - Part A (HFA) and Part C (road fatigue + travel direction) are pure ADDITIVE terms,
    appended to the existing Model Home/Away Score formulas (Z/AA) via append_term_once --
    idempotent, never touches the base formula text.
  - Part B (Rest Effect, col O) and Part D (Weather Adj, col U) OVERWRITE those two existing
    "leaf" columns IN PLACE. This is safe specifically because Z/AA only ever reference O{r}
    and U{r} by cell address (verified live before writing this: nothing else in the
    workbook reads O or U directly) -- changing O/U's own internal formula requires no
    change to Z/AA's text at all, unlike Z/AA themselves which must never be rewritten.

Part A -- Team-Specific HFA (replaces the flat 'Model Assumptions'!$C$3 HFA the base Z/AA
formulas already apply):
    Home HFA Delta = Home Team's Regressed Team-Specific HFA (Team-Specific HFA tab,
                      Section 3 col H) / 2 - 'Model Assumptions'!$C$3 / 2
    Away HFA Delta = -Home HFA Delta
Appended into Z/AA -- nets the base formula's existing +-C3/2 terms to +-TeamHFA/2 without
ever touching Z3/AA3's own text.

Part B -- Rest Effect (col O) replaced with a tiered lookup (named category boundaries, not
a linear formula in disguise): Short Week/Thursday (days <= C150) gets a fixed penalty
(C152), Bye/Long Rest (days >= C151) gets a fixed bonus (C154), everything between gets
C153 (0 by default) -- computed independently for Home (M) and Away (N) rest days, then
Home Tier Effect - Away Tier Effect replaces the old linear (M-N)*C4 differential.

Part C -- Consecutive Road Games (checked first against the Availability Index's existing
Schedule Density mechanism per the spec's own instruction -- it did NOT already track
real home/away SEQUENCE, only trailing-date-window game FREQUENCY, so build_availability_
index.py was extended with a genuinely new Section 2b column rather than this script
duplicating a mechanism): whichever of this game's two teams has >= C155 consecutive real
road games (trailing 3, from Availability Index Section 2b) takes a flat fatigue penalty
(C156), applied to THAT team's own score regardless of whether they're playing at home or
away this specific week (the fatigue is real regardless of this week's site).

Part C -- Travel Direction: using Team-Specific HFA's own Section 4 (Team | Stadium UTC
Offset, standard time), Home Stadium Offset - Away Team's Home Offset > 0 means the away
team is crossing time zones EAST this week (e.g. Pacific -8 -> Eastern -5, delta +3) --
real, published (though coarse) jet-lag research finding that eastward travel is harder on
performance than westward; applies a dedicated penalty (C157) to the away team only (the
home team isn't traveling).

Part D -- Weather Adj (col U) extended with two new manual blue-input columns (Snow Y/N,
Humidity %). Snow applies its OWN adjustment (C158) INSTEAD OF the generic Precip
adjustment when both are checked (avoids double-counting the same precipitation event);
Humidity applies its own additive threshold-based penalty (>= C159 triggers C160) alongside
the unchanged existing Wind/Cold mechanics.

Part E -- Weather-on-Passing: CONFIRMED NOT REBUILT HERE. Already implemented by
build_effective_qb_rating_wiring.py (cols BW/BX, Model Assumptions C134) -- inspect that
tab's own columns, not this one, for QB-specific weather sensitivity.

NOT YET VALIDATED: same disclaimer as every tab in the Defensive Matchup Engine family.

Usage:
    uv run python scripts/build_game_environment_wiring.py "C:\\path\\to\\model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from build_replacement_value import append_term_once  # noqa: E402

HFA_SHEET = "Team-Specific HFA"
AVAIL_SHEET = "Availability Index"
MATCHUPS_SHEET = "Season Matchups"

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


def _find_title_row(ws, needle: str) -> int:
    """
    Locate a section's own title row by requiring the cell text to START WITH `needle`
    (e.g. "Section 3") rather than merely CONTAIN it -- an earlier section's own prose note
    can legitimately mention a LATER section by number (Section 1's own closing sentence
    here says "...Section 3 regresses this toward the league average..."), which a bare
    substring search would false-match. Verified live before fixing this: it did exactly
    that, resolving Team-Specific HFA's Section 3 to row 3 (Section 1's title) instead of
    its real title row, silently pointing CQ/CR/CS at Section 1's raw per-season data
    instead of Section 3's regressed HFA and producing real #VALUE! errors downstream.
    """
    for row in range(1, ws.max_row + 1):
        val = ws.cell(row=row, column=1).value
        if val and str(val).strip().startswith(needle):
            return row
    raise ValueError(f"Could not find a row starting with {needle!r} in '{ws.title}'.")


def add_model_assumptions_weights(wb: openpyxl.Workbook) -> None:
    ws = wb["Model Assumptions"]
    title_row = 149
    ws.merge_cells(f"A{title_row}:D{title_row}")
    title = ws.cell(row=title_row, column=1, value=(
        "Game Environment Upgrades (Week 1 Matchups Parts A-D -- HFA, Rest Tiers, Road "
        "Fatigue/Travel Direction, Snow/Humidity; see 'Week 1 Matchups' and 'Team-Specific "
        "HFA' tabs). Part E (Weather-on-Passing) is NOT here -- see C133/C134 instead."
    ))
    title.font = HEADER_FONT
    title.fill = HEADER_FILL

    rows = [
        (150, "Short Week/Thursday Rest Threshold (days, <=)", 4,
         "Home or Away Rest Days at or below this many days counts as a Short Week/"
         "Thursday game for that team -- a named category boundary, not a linear "
         "coefficient."),
        (151, "Bye/Long Rest Threshold (days, >=)", 10,
         "Home or Away Rest Days at or above this many days counts as Bye/Long Rest for "
         "that team."),
        (152, "Short Week/Thursday Rest Effect (pts)", -1.5,
         "Applied to whichever side (Home Tier Effect or Away Tier Effect) is on a Short "
         "Week; the other side keeps its own tier's effect. Replaces the old linear "
         "(Home Rest - Away Rest) * C4 formula in column O."),
        (153, "Normal Rest Effect (pts)", 0.0,
         "Applied when a team's rest days are strictly between the Short Week and Bye "
         "thresholds -- the 'nothing unusual' middle tier."),
        (154, "Bye/Long Rest Effect (pts)", 1.0,
         "Applied to whichever side is coming off a bye or extended rest."),
        (155, "Consecutive Road Games Threshold (games)", 3,
         "A team with this many or more consecutive real road games (Availability "
         "Index Section 2b, trailing 3) takes the road-fatigue penalty below, "
         "regardless of whether they're Home or Away in THIS game."),
        (156, "Consecutive Road Games Penalty (pts)", -1.0,
         "Applied to the fatigued team's own score (Z if they're Home this week, AA if "
         "Away) -- the fatigue is real regardless of this week's site."),
        (157, "Travel Direction -- West-to-East Penalty (pts)", -0.5,
         "Applied to the Away team only when Home Stadium UTC Offset - Away Team's own "
         "Home UTC Offset > 0 (traveling east, e.g. Pacific -8 -> Eastern -5) -- a real, "
         "published (though coarse/approximate, standard-time-only) jet-lag research "
         "finding that eastward travel is harder on performance than westward. The Home "
         "team never gets this adjustment -- they aren't traveling."),
        (158, "Snow Adjustment (pts, applied to game total)", -1.5,
         "Applied INSTEAD OF (not in addition to) the existing generic Precipitation "
         "Adjustment (C10) when Snow=Y -- avoids double-counting the same precipitation "
         "event. Precip=Y with Snow=N still uses C10 as before."),
        (159, "Humidity Threshold (%, >=)", 70,
         "Humidity at or above this triggers the High Humidity Adjustment below -- "
         "applied additively alongside the existing Wind/Cold/Precip-or-Snow mechanics, "
         "not a replacement for any of them."),
        (160, "High Humidity Adjustment (pts, applied to game total)", -0.5,
         "A starting guess, like every other coefficient in this model."),
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
    for required in (HFA_SHEET, AVAIL_SHEET, MATCHUPS_SHEET):
        if required not in wb.sheetnames:
            raise ValueError(
                f"'{required}' not found -- run its own build script first (see this "
                "script's own module docstring for the required order)."
            )

    hfa_ws = wb[HFA_SHEET]
    ai_ws = wb[AVAIL_SHEET]
    wm = wb[MATCHUPS_SHEET]

    # ---- Locate Team-Specific HFA's Section 3 (Team=A, Regressed HFA=H) and Section 4
    # (Team=A, UTC Offset=B) precisely by scanning for their own section titles -- avoids a
    # hardcoded row range that would silently misalign if real pulled-season counts shift.
    hfa_sec3_title_row = _find_title_row(hfa_ws, "Section 3")
    hfa_sec3_first = hfa_sec3_title_row + 2
    hfa_sec3_last = hfa_sec3_first
    while hfa_ws.cell(row=hfa_sec3_last + 1, column=1).value is not None:
        hfa_sec3_last += 1

    hfa_sec4_title_row = _find_title_row(hfa_ws, "Section 4")
    hfa_sec4_first = hfa_sec4_title_row + 2
    hfa_sec4_last = hfa_sec4_first
    while hfa_ws.cell(row=hfa_sec4_last + 1, column=1).value is not None:
        hfa_sec4_last += 1

    # ---- Locate Availability Index's Section 2b (Team=A, Consecutive Road Games=E) by
    # scanning for its own distinctive header text, since Section 2's raw game log ALSO uses
    # column A for Team -- a generous blanket range would silently match the wrong section.
    avail_sec2b_header_row = None
    for row in range(1, ai_ws.max_row + 1):
        val = ai_ws.cell(row=row, column=5).value
        if val and "Consecutive Road" in str(val):
            avail_sec2b_header_row = row
            break
    if avail_sec2b_header_row is None:
        raise ValueError(
            f"'{AVAIL_SHEET}' has no 'Consecutive Road' column -- rebuild it with the "
            "current build_availability_index.py first."
        )
    avail_sec2b_first = avail_sec2b_header_row + 1
    avail_sec2b_last = avail_sec2b_first
    while ai_ws.cell(row=avail_sec2b_last + 1, column=1).value is not None:
        avail_sec2b_last += 1

    add_model_assumptions_weights(wb)

    game_rows = []
    row = 3
    while wm.cell(row=row, column=1).value is not None:
        game_rows.append(row)
        row += 1

    hfa_team_range = f"'{HFA_SHEET}'!$A${hfa_sec3_first}:$A${hfa_sec3_last}"
    hfa_score_range = f"'{HFA_SHEET}'!$H${hfa_sec3_first}:$H${hfa_sec3_last}"
    offset_team_range = f"'{HFA_SHEET}'!$A${hfa_sec4_first}:$A${hfa_sec4_last}"
    offset_range = f"'{HFA_SHEET}'!$B${hfa_sec4_first}:$B${hfa_sec4_last}"
    road_team_range = f"'{AVAIL_SHEET}'!$A${avail_sec2b_first}:$A${avail_sec2b_last}"
    road_games_range = f"'{AVAIL_SHEET}'!$E${avail_sec2b_first}:$E${avail_sec2b_last}"

    headers = [
        (95, "Home Team Regressed\nHFA (ref)"), (96, "Home HFA\nDelta (pts)"),
        (97, "Away HFA\nDelta (pts)"),
        (98, "Home Consecutive\nRoad Games (ref)"), (99, "Away Consecutive\nRoad Games (ref)"),
        (100, "Home Road Fatigue\nAdj. (pts)"), (101, "Away Road Fatigue\nAdj. (pts)"),
        (102, "Home Stadium\nUTC Offset (ref)"), (103, "Away Team Home\nUTC Offset (ref)"),
        (104, "Travel Direction\nDelta (Home-Away)"), (105, "Away Travel\nDirection Adj (pts)"),
        (106, "Snow\n(Y/N)"), (107, "Humidity\n(%)"),
    ]
    for col, label in headers:
        c = wm.cell(row=2, column=col, value=label)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = HEADER_ALIGN

    for r in game_rows:
        # ==== Part A: Team-Specific HFA ====================================================
        cq = wm.cell(row=r, column=95, value=(
            f'=IFERROR(INDEX({hfa_score_range},MATCH(D{r},{hfa_team_range},0)),"")'
        ))
        cq.font = LINK_FONT
        cq.number_format = "0.00;(0.00)"

        # claude_code_spec_hfa_wiring_fix.md: CQ/CR/CS are no longer appended into Z/AA --
        # build_season_matchups.py's own base Z/AA formula now looks up CQ directly (with the
        # same 'Model Assumptions'!$C$3 fallback), so appending +-CR/CS here on top would
        # double-count the exact same value. CR/CS are kept, computed exactly as before, ONLY
        # because Market Comparison & Confidence's own Explanation Engine (col AB, "HFA Delta
        # Net Home Adv.") reads them directly for its own real factor-attribution ranking --
        # a genuinely different, isolated-marginal-contribution use, unrelated to Z/AA.
        cr = wm.cell(row=r, column=96, value=(
            f'=IF(CQ{r}="",0,(CQ{r}-\'Model Assumptions\'!$C$3)/2)'
        ))
        cs = wm.cell(row=r, column=97, value=f'=IF(CR{r}="",0,-CR{r})')
        cr.font = FORMULA_FONT
        cs.font = FORMULA_FONT
        cr.number_format = "0.00;(0.00)"
        cs.number_format = "0.00;(0.00)"

        # ==== Part C: Consecutive Road Games (fatigue, whichever side qualifies) ===========
        ct = wm.cell(row=r, column=98, value=(
            f'=IFERROR(INDEX({road_games_range},MATCH(D{r},{road_team_range},0)),0)'
        ))
        cu = wm.cell(row=r, column=99, value=(
            f'=IFERROR(INDEX({road_games_range},MATCH(C{r},{road_team_range},0)),0)'
        ))
        ct.font = LINK_FONT
        cu.font = LINK_FONT

        cv = wm.cell(row=r, column=100, value=(
            f"=IF(CT{r}>='Model Assumptions'!$C$155,'Model Assumptions'!$C$156,0)"
        ))
        cw = wm.cell(row=r, column=101, value=(
            f"=IF(CU{r}>='Model Assumptions'!$C$155,'Model Assumptions'!$C$156,0)"
        ))
        cv.font = FORMULA_FONT
        cw.font = FORMULA_FONT
        cv.number_format = "0.00;(0.00)"
        cw.number_format = "0.00;(0.00)"

        # ==== Part C: Travel Direction (away team only -- they're the one traveling) =======
        cx = wm.cell(row=r, column=102, value=(
            f'=IFERROR(INDEX({offset_range},MATCH(D{r},{offset_team_range},0)),"")'
        ))
        cy = wm.cell(row=r, column=103, value=(
            f'=IFERROR(INDEX({offset_range},MATCH(C{r},{offset_team_range},0)),"")'
        ))
        cx.font = LINK_FONT
        cy.font = LINK_FONT

        cz = wm.cell(row=r, column=104, value=(
            f'=IF(OR(CX{r}="",CY{r}=""),"",CX{r}-CY{r})'
        ))
        cz.font = FORMULA_FONT

        da = wm.cell(row=r, column=105, value=(
            f"=IF(CZ{r}=\"\",0,IF(CZ{r}>0,'Model Assumptions'!$C$157,0))"
        ))
        da.font = FORMULA_FONT
        da.number_format = "0.00;(0.00)"

        # ==== Part D: Snow / Humidity manual inputs =========================================
        db = wm.cell(row=r, column=106, value="N")
        dc = wm.cell(row=r, column=107, value=50)
        db.font = INPUT_FONT
        dc.font = INPUT_FONT
        dc.number_format = "0"

        # ==== Part B: Rest Effect (col O) -- tiered, named category boundaries =============
        def _tier(days_ref: str) -> str:
            return (
                f"IF({days_ref}<='Model Assumptions'!$C$150,'Model Assumptions'!$C$152,"
                f"IF({days_ref}>='Model Assumptions'!$C$151,'Model Assumptions'!$C$154,"
                f"'Model Assumptions'!$C$153))"
            )

        o_cell = wm.cell(row=r, column=15, value=f"={_tier(f'M{r}')}-{_tier(f'N{r}')}")
        o_cell.font = FORMULA_FONT
        o_cell.number_format = "0.00;(0.00)"

        # ==== Part D: Weather Adj (col U) -- Snow overrides Precip, Humidity additive ======
        u_cell = wm.cell(row=r, column=21, value=(
            f'=IF(F{r}="Dome",0,'
            f"IF(DB{r}=\"Y\",'Model Assumptions'!$C$158,IF(T{r}=\"Y\",'Model Assumptions'!$C$10,0))"
            f"+IF(S{r}>'Model Assumptions'!$C$6,'Model Assumptions'!$C$7,0)"
            f"+IF(R{r}<'Model Assumptions'!$C$8,'Model Assumptions'!$C$9,0)"
            f"+IF(DC{r}>='Model Assumptions'!$C$159,'Model Assumptions'!$C$160,0))"
        ))
        u_cell.font = FORMULA_FONT
        u_cell.number_format = "0.00;(0.00)"

        # ---- Append the new additive terms to the existing Model Home/Away Score formulas
        # (Z/AA) -- idempotent, never touches the base formula text. O/U are overwritten in
        # place above and need no append (Z/AA already reference them by cell address). CR/CS
        # (HFA Delta) are deliberately NOT appended here -- build_season_matchups.py's own
        # base formula already looks up the real Team-Specific HFA value directly (see that
        # script's own docstring), so appending the delta here on top would double-count it.
        z_cell = wm.cell(row=r, column=26)  # Z
        aa_cell = wm.cell(row=r, column=27)  # AA
        z_cell.value = append_term_once(z_cell.value, f"+CV{r}")
        aa_cell.value = append_term_once(aa_cell.value, f"+CW{r}")
        aa_cell.value = append_term_once(aa_cell.value, f"+DA{r}")

    note_row_wm = max(game_rows) + 11
    wm.merge_cells(start_row=note_row_wm, start_column=1, end_row=note_row_wm, end_column=20)
    wm_note = wm.cell(row=note_row_wm, column=1, value=(
        "claude_code_spec_game_environment_upgrades.md Parts A-D. Part A: Home/Away HFA "
        "Delta (CR/CS) nets the base Z/AA formulas' existing flat +-'Model Assumptions'!"
        "$C$3/2 terms to +-the Home team's own real, 3-Yr decay-weighted, REGRESSED "
        "Team-Specific HFA/2 (see 'Team-Specific HFA' tab) -- appended via append_term_once, "
        "Z3/AA3's own base text was never rewritten. Part B: column O (Rest Effect) was "
        "overwritten in place with a tiered lookup (Short Week/Normal/Bye, named category "
        "boundaries on Model Assumptions C150-C154), replacing the old linear (Home Rest - "
        "Away Rest) * C4 formula -- safe because Z/AA only ever reference O by cell address. "
        "Part C: Consecutive Road Games fatigue (CV/CW, from Availability Index's own new "
        "Section 2b column -- checked first, genuinely did not already exist there before "
        "extending it) applies to whichever team has >= C155 consecutive real road games, "
        "regardless of this week's home/away site; Travel Direction (DA) applies an "
        "eastward-travel penalty (C157) to the Away team only, using Team-Specific HFA's own "
        "Section 4 real Stadium UTC Offset reference table. Part D: column U (Weather Adj) "
        "was overwritten in place to add two new manual inputs, Snow (DB) and Humidity (DC) "
        "-- Snow REPLACES (not adds to) the generic Precip adjustment when both are checked, "
        "avoiding double-counting; Humidity applies its own additive threshold penalty "
        "(C159/C160) alongside the unchanged Wind/Cold mechanics. Part E (Weather-on-"
        "Passing) is CONFIRMED NOT REBUILT HERE -- already implemented by "
        "claude_code_spec_qb_environment_model.md's Effective QB Rating wiring (cols BW/BX, "
        "Model Assumptions C134); this script's own U/Snow/Humidity change is generic and "
        "QB-agnostic. NOT YET VALIDATED against real outcomes -- same disclaimer as every "
        "tab in the Defensive Matchup Engine family."
    ))
    wm_note.font = NOTE_FONT
    wm_note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Wired Game Environment Upgrades into '{MATCHUPS_SHEET}' (cols CQ-DC, "
        f"{len(game_rows)} games); overwrote O (Rest Effect) and U (Weather Adj) in place."
    )
    print(f"Saved to {workbook_path}")
    return {"game_rows": game_rows}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            'Usage: uv run python scripts/build_game_environment_wiring.py '
            '"path/to/workbook.xlsx"'
        )
        sys.exit(1)
    build(sys.argv[1])
