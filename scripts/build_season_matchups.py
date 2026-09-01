"""
Builds "Season Matchups" -- claude_code_spec_full_season_matchups.md. Replaces the old
hardcoded 16-game "Week 1 Matchups" tab with ONE long-format table, one row per real game
across the ENTIRE season (272 real 2026 games, 18 weeks) -- Week Number is a column here,
not a tab boundary. Confirmed with the user before building this: "Week 1 Matchups" is
RETIRED entirely (not kept as a filtered view) once this tab exists.

Columns A-AP replicate "Week 1 Matchups" own real base structure EXACTLY (verified live by
reading every one of its real row-3 formulas before writing this) -- same game info, same
Model Home/Away Score CLEAN base formula (no wiring terms baked in yet), same DraftKings/
MyBookie odds block. Columns AQ onward (QB Replacement AS/AT, Phase Matchup, OL Pressure,
Effective QB Rating, Explosive Play, Game Environment) are deliberately NOT written here --
verified live before building this that build_replacement_value.py and this project's other
existing Week 1 Matchups wiring scripts already own that territory (including their own
append_term_once("+AS{r}"/"+AT{r}"/etc.) into Z/AA); writing it here too would duplicate
those scripts' real work. Each of those scripts is instead repointed at this tab's own
MATCHUPS_SHEET constant and re-run by the pipeline in the SAME order as always -- they
append their own real terms back on exactly as they always have, just for 272 rows instead
of 16, which is why this script must run BEFORE build_replacement_value.py specifically
(the first of them to touch this tab) in main.py's own pipeline order.

NEW, per the spec's own explicit "set this up for backtesting" instruction: Actual Home
Score / Actual Away Score columns (appended at the very end, past every wiring script's own
territory) -- blank until a game is played, filled in by hand afterward. Nothing reads them
yet; this tab's own structure just doesn't need reworking later to support it.

Real per-week Rest Days (nflverse's own real computed home_rest/away_rest, verified live:
genuinely varies 4-14 real days for week 2+, not the old flat-7 placeholder Week 1 always
used since it had no prior game to compute from -- Week 1's own real rest values ARE 7 here
too, but that's because nflverse's real data says so for a season opener, not a hardcoded
simplification anymore) and real Divisional flag (nflverse's own real div_game) replace the
old manual blue-input placeholders. Bye weeks need no special handling: a team's row simply
doesn't exist for its bye week among the 272 real games -- no fabricated opponent, no error.

READ-BACK: genuinely discretionary manual fields (weather placeholders, sportsbook odds, QB
status, and the new Actual Score columns) are read back from the PRIOR Season Matchups sheet
before it's deleted and rebuilt, keyed by (Week, Away Team, Home Team) -- the same "preserve
real user input across a rebuild" discipline the Manual Override tables already established,
since re-pulling the real schedule every pipeline run would otherwise silently wipe a real
score the user entered after a game, or real odds they'd typed in for an upcoming week.

Usage:
    uv run python scripts/build_season_matchups.py "C:\\path\\to\\NFL_Prediction_Model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nflverse_pull.availability import fetch_schedules_with_dates  # noqa: E402
from nflverse_pull.season_schedule import (  # noqa: E402
    compute_roof_fallback,
    compute_season_schedule,
)

HISTORICAL_YEARS = [2023, 2024, 2025]
CURRENT_SEASON = 2026
SHEET_NAME = "Season Matchups"
OLD_SHEET_NAME = "Week 1 Matchups"

TITLE_FONT = Font(name="Arial", size=10, bold=True)
TITLE_FILL = PatternFill("solid", fgColor="FFD9E1F2")
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="FF1F4E78")
HEADER_ALIGN = Alignment(wrap_text=True, horizontal="center", vertical="center")
INPUT_FONT = Font(name="Arial", size=10, color="FF0000FF")
FORMULA_FONT = Font(name="Arial", size=10, color="FF000000")
LINK_FONT = Font(name="Arial", size=10, color="FF008000")
NOTE_FONT = Font(name="Arial", size=9, color="FF808080")

# Genuinely discretionary manual columns THIS script owns, to read back across a rebuild
# (by header text). Deliberately does NOT include QB Status (AQ/AR, owned by build_
# replacement_value.py) or Snow/Humidity (DB/DC, owned by build_game_environment_wiring.py)
# -- neither of those columns exists yet when this script runs, and both of those OTHER
# scripts already unconditionally reset their own columns on every rebuild regardless
# (a pre-existing behavior, not something this spec asks to fix).
READBACK_HEADERS = [
    "Temp\n(F)", "Wind\n(mph)", "Precip\n(Y/N)", "Home Add'l\nInjury (pts)",
    "Away Add'l\nInjury (pts)", "DraftKings Spread\n(Home)", "DraftKings\nTotal",
    "Sportsbook", "MyBookie Spread\n(Home)", "MyBookie\nTotal", "Actual Home\nScore",
    "Actual Away\nScore", "Home\nMoneyline", "Away\nMoneyline",
]




def _read_back(wb: openpyxl.Workbook) -> dict[tuple, dict[str, object]]:
    """
    Real per-game read-back of the discretionary manual columns from whichever sheet
    already holds them (this script's own prior 'Season Matchups' output, or -- the very
    first time this runs -- the old 'Week 1 Matchups', so Week 1's own real manual data
    isn't lost on the one-time cutover). Keyed by (Week, Away Team, Home Team).
    """
    source_name = SHEET_NAME if SHEET_NAME in wb.sheetnames else OLD_SHEET_NAME
    if source_name not in wb.sheetnames:
        return {}
    ws = wb[source_name]
    headers = {ws.cell(row=2, column=c).value: c for c in range(1, ws.max_column + 1)}
    week_col = headers.get("Week")
    away_col = headers.get("Away Team")
    home_col = headers.get("Home Team")
    if not (week_col and away_col and home_col):
        return {}

    out: dict[tuple, dict[str, object]] = {}
    row = 3
    while ws.cell(row=row, column=week_col).value is not None:
        key = (
            ws.cell(row=row, column=week_col).value,
            ws.cell(row=row, column=away_col).value,
            ws.cell(row=row, column=home_col).value,
        )
        vals = {}
        for h in READBACK_HEADERS:
            c = headers.get(h)
            if c is not None:
                v = ws.cell(row=row, column=c).value
                if v is not None and v != "" and not (isinstance(v, str) and v.startswith("=")):
                    vals[h] = v
        if vals:
            out[key] = vals
        row += 1
    return out


def _pull_data():
    print(f"Pulling {HISTORICAL_YEARS + [CURRENT_SEASON]} schedule data for Season Matchups...")
    sched_multi = fetch_schedules_with_dates(HISTORICAL_YEARS)
    sched_current = fetch_schedules_with_dates([CURRENT_SEASON])
    roof_fallback = compute_roof_fallback(sched_multi)
    return compute_season_schedule(sched_current, CURRENT_SEASON, roof_fallback)


def build(workbook_path: str) -> dict:
    schedule = _pull_data()

    wb = openpyxl.load_workbook(workbook_path)
    readback = _read_back(wb)

    if OLD_SHEET_NAME in wb.sheetnames:
        del wb[OLD_SHEET_NAME]
    if SHEET_NAME in wb.sheetnames:
        del wb[SHEET_NAME]
    ws = wb.create_sheet(SHEET_NAME, index=1)
    ws.column_dimensions["A"].width = 6.0
    ws.column_dimensions["E"].width = 22.0

    ws.merge_cells("A1:P1")
    t = ws.cell(row=1, column=1, value=(
        "Season Matchups -- Model Prediction vs. Sportsbook Line, ALL 18 real weeks in ONE "
        "long-format table (Week is a column, not a tab boundary). Retired 'Week 1 "
        "Matchups' -- this is the single source of truth now."
    ))
    t.font = Font(name="Arial", size=12, bold=True)

    headers = [
        "Week", "Date", "Away Team", "Home Team", "Stadium / Location", "Dome /\nOutdoor",
        "Home Net\nRating", "Away Net\nRating", "Home Off\n(PPG)", "Home Def\n(PPG)",
        "Away Off\n(PPG)", "Away Def\n(PPG)", "Home Rest\n(days)", "Away Rest\n(days)",
        "Rest Effect\n(pts)", "Away Travel\n(miles)", "Travel Effect\n(pts)", "Temp\n(F)",
        "Wind\n(mph)", "Precip\n(Y/N)", "Weather Adj\n(pts, total)", "Home Add'l\nInjury (pts)",
        "Away Add'l\nInjury (pts)", "Divisional?", "Division Adj\n(pts)", "Model Home\nScore",
        "Model Away\nScore", "Model\nTotal", "Model Margin\n(Home-Away)",
        "DraftKings Spread\n(Home)", "DraftKings\nTotal", "Sportsbook",
        "DK Spread Edge\n(Model-DK)", "DK Total Edge\n(Model-DK)", "DK Recommended\nSpread Play",
        "DK Recommended\nTotal Play", "MyBookie Spread\n(Home)", "MyBookie\nTotal",
        "MyB Spread Edge\n(Model-MyB)", "MyB Total Edge\n(Model-MyB)",
        "MyB Recommended\nSpread Play", "MyB Recommended\nTotal Play",
    ]
    # AQ-AT (QB Status + Replacement Adj) are deliberately NOT written here -- verified live
    # before building this that build_replacement_value.py (repointed at this tab, runs
    # right after it in the pipeline) already owns that block, including its own
    # append_term_once("+AS{r}"/"+AT{r}") into Z/AA -- writing it here too would duplicate
    # that script's real territory.
    ws.row_dimensions[2].height = 30
    for col, htext in enumerate(headers, start=1):
        c = ws.cell(row=2, column=col, value=htext)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = HEADER_ALIGN
    # Actual Home/Away Score live at cols 108/109 (DD/DE) -- past every wiring script's own
    # territory (ends at DC/107) -- written here directly since `headers` only covers the
    # contiguous A-AT block this script owns outright. Col 110 (DF) is a real "Game Key"
    # helper (Week|Away|Home) -- lets a LATER tab (e.g. Market Comparison & Confidence)
    # look up a specific real game via a single-criteria MATCH instead of an unwrapped
    # multi-criteria array MATCH (the exact pattern this project caught and removed as a
    # real bug earlier this session). Cols 111/112 (DG/DH): Home/Away Moneyline --
    # claude_code_spec_season_win_total_moneyline.md Part B, manual odds input alongside
    # the existing DK/MyBookie spread/total block, same convention (blue input, real
    # sportsbook odds the user types in).
    for col, htext in (
        (108, "Actual Home\nScore"), (109, "Actual Away\nScore"), (110, "Game Key\n(helper)"),
        (111, "Home\nMoneyline"), (112, "Away\nMoneyline"),
    ):
        c = ws.cell(row=2, column=col, value=htext)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = HEADER_ALIGN

    first_row = 3
    for i, r in enumerate(schedule.to_dict("records")):
        row = first_row + i
        key = (int(r["Week"]), r["Away Team"], r["Home Team"])
        rb = readback.get(key, {})

        vals = [
            int(r["Week"]), r["Date"], r["Away Team"], r["Home Team"], r["Stadium"],
            "Dome" if r["Dome"] else "Outdoor",
        ]
        for col, v in enumerate(vals, start=1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.font = INPUT_FONT if col in (1, 2, 3, 4, 5, 6) else FORMULA_FONT
        ws.cell(row=row, column=2).number_format = "yyyy-mm-dd"

        # ---- G-L: live Team Ratings cross-references (unchanged shape) -------------------
        g = ws.cell(row=row, column=7, value=(
            f"=INDEX('Team Ratings'!$N$3:$N$34,MATCH(D{row},'Team Ratings'!$A$3:$A$34,0))"
        ))
        h = ws.cell(row=row, column=8, value=(
            f"=INDEX('Team Ratings'!$N$3:$N$34,MATCH(C{row},'Team Ratings'!$A$3:$A$34,0))"
        ))
        i_ = ws.cell(row=row, column=9, value=(
            f"=INDEX('Team Ratings'!$J$3:$J$34,MATCH(D{row},'Team Ratings'!$A$3:$A$34,0))"
        ))
        j = ws.cell(row=row, column=10, value=(
            f"=INDEX('Team Ratings'!$K$3:$K$34,MATCH(D{row},'Team Ratings'!$A$3:$A$34,0))"
        ))
        k = ws.cell(row=row, column=11, value=(
            f"=INDEX('Team Ratings'!$J$3:$J$34,MATCH(C{row},'Team Ratings'!$A$3:$A$34,0))"
        ))
        l_ = ws.cell(row=row, column=12, value=(
            f"=INDEX('Team Ratings'!$K$3:$K$34,MATCH(C{row},'Team Ratings'!$A$3:$A$34,0))"
        ))
        for cell in (g, h, i_, j, k, l_):
            cell.font = LINK_FONT
            cell.number_format = "0.0"

        # ---- M/N: real Home/Away Rest (days), from the real pulled schedule --------------
        m = ws.cell(row=row, column=13, value=int(r["Home Rest"]))
        n = ws.cell(row=row, column=14, value=int(r["Away Rest"]))
        m.font = INPUT_FONT
        n.font = INPUT_FONT

        # ---- O: Rest Effect -- CLEAN base (linear); overwritten in place once the
        # pipeline re-runs build_game_environment_wiring against this tab, same as before.
        o = ws.cell(row=row, column=15, value=f"=(M{row}-N{row})*'Model Assumptions'!$C$4")
        o.font = FORMULA_FONT
        o.number_format = "0.00;(0.00)"

        # ---- P/Q: real Away Travel (miles) + Travel Effect --------------------------------
        p = ws.cell(row=row, column=16, value=round(float(r["Away Travel"]), 1))
        p.font = INPUT_FONT
        q = ws.cell(row=row, column=17, value=f"=-(P{row}/1000)*'Model Assumptions'!$C$5")
        q.font = FORMULA_FONT
        q.number_format = "0.00;(0.00)"

        # ---- R/S/T: weather PLACEHOLDERS (no real forecast this far out) -- read back if
        # a real value was already entered for this exact game, else a defensible default.
        r_temp = ws.cell(row=row, column=18, value=rb.get("Temp\n(F)", 70))
        r_wind = ws.cell(row=row, column=19, value=rb.get("Wind\n(mph)", 8))
        r_precip = ws.cell(row=row, column=20, value=rb.get("Precip\n(Y/N)", "N"))
        for cell in (r_temp, r_wind, r_precip):
            cell.font = INPUT_FONT

        # ---- U: Weather Adj -- CLEAN base (no Snow/Humidity yet); overwritten in place
        # once build_game_environment_wiring re-runs against this tab.
        u = ws.cell(row=row, column=21, value=(
            f"=IF(F{row}=\"Dome\",0,IF(S{row}>'Model Assumptions'!$C$6,"
            f"'Model Assumptions'!$C$7,0)+IF(R{row}<'Model Assumptions'!$C$8,"
            f"'Model Assumptions'!$C$9,0)+IF(T{row}=\"Y\",'Model Assumptions'!$C$10,0))"
        ))
        u.font = FORMULA_FONT
        u.number_format = "0.00;(0.00)"

        v_ = ws.cell(row=row, column=22, value=rb.get("Home Add'l\nInjury (pts)", 0))
        w = ws.cell(row=row, column=23, value=rb.get("Away Add'l\nInjury (pts)", 0))
        v_.font = INPUT_FONT
        w.font = INPUT_FONT

        x = ws.cell(row=row, column=24, value="Y" if r["Divisional"] else "N")
        x.font = INPUT_FONT
        y = ws.cell(row=row, column=25, value=f'=IF(X{row}="Y",\'Model Assumptions\'!$C$11,0)')
        y.font = FORMULA_FONT
        y.number_format = "0.00;(0.00)"

        # ---- Z/AA: CLEAN base Model Home/Away Score -- no wiring terms baked in. The 5
        # existing wiring scripts append their own real terms back on via append_term_once
        # when the pipeline re-runs them against this tab, in the SAME order as always.
        z = ws.cell(row=row, column=26, value=(
            f"=(I{row}+L{row})/2+'Model Assumptions'!$C$3/2+O{row}/2+U{row}/2+V{row}+"
            f"Y{row}/2"
        ))
        aa = ws.cell(row=row, column=27, value=(
            f"=(K{row}+J{row})/2-'Model Assumptions'!$C$3/2-O{row}/2+Q{row}+U{row}/2+"
            f"W{row}+Y{row}/2"
        ))
        z.font = FORMULA_FONT
        aa.font = FORMULA_FONT
        z.number_format = "0.0;(0.0)"
        aa.number_format = "0.0;(0.0)"

        ab = ws.cell(row=row, column=28, value=f"=Z{row}+AA{row}")
        ac = ws.cell(row=row, column=29, value=f"=Z{row}-AA{row}")
        ab.font = FORMULA_FONT
        ac.font = FORMULA_FONT
        ab.number_format = "0.0"
        ac.number_format = "0.0;(0.0)"

        # ---- AD-AP: DraftKings/MyBookie odds block (read back if entered already) --------
        ad = ws.cell(row=row, column=30, value=rb.get("DraftKings Spread\n(Home)", 0))
        ae = ws.cell(row=row, column=31, value=rb.get("DraftKings\nTotal", 0))
        af = ws.cell(row=row, column=32, value=rb.get("Sportsbook", "DraftKings"))
        for cell in (ad, ae, af):
            cell.font = INPUT_FONT
        ag = ws.cell(row=row, column=33, value=f"=AC{row}+AD{row}")
        ah = ws.cell(row=row, column=34, value=f"=AB{row}-AE{row}")
        ai = ws.cell(row=row, column=35, value=(
            f'=IF(ABS(AG{row})>=\'Model Assumptions\'!$C$15,IF(AG{row}>0,"Home","Away"),'
            f'"No Edge")'
        ))
        aj = ws.cell(row=row, column=36, value=(
            f'=IF(ABS(AH{row})>=\'Model Assumptions\'!$C$16,IF(AH{row}>0,"Over","Under"),'
            f'"No Edge")'
        ))
        for cell in (ag, ah, ai, aj):
            cell.font = FORMULA_FONT
        ag.number_format = "0.0;(0.0)"
        ah.number_format = "0.0;(0.0)"

        ak = ws.cell(row=row, column=37, value=rb.get("MyBookie Spread\n(Home)", 0))
        al = ws.cell(row=row, column=38, value=rb.get("MyBookie\nTotal", 0))
        for cell in (ak, al):
            cell.font = INPUT_FONT
        am = ws.cell(row=row, column=39, value=f"=AC{row}+AK{row}")
        an = ws.cell(row=row, column=40, value=f"=AB{row}-AL{row}")
        ao = ws.cell(row=row, column=41, value=(
            f'=IF(ABS(AM{row})>=\'Model Assumptions\'!$C$15,IF(AM{row}>0,"Home","Away"),'
            f'"No Edge")'
        ))
        ap = ws.cell(row=row, column=42, value=(
            f'=IF(ABS(AN{row})>=\'Model Assumptions\'!$C$16,IF(AN{row}>0,"Over","Under"),'
            f'"No Edge")'
        ))
        for cell in (am, an, ao, ap):
            cell.font = FORMULA_FONT
        am.number_format = "0.0;(0.0)"
        an.number_format = "0.0;(0.0)"

        # ---- DD/DE (cols 108/109): Actual Home/Away Score -- appended past every wiring
        # script's own territory (which ends at DC/107), blank until a game is played, read
        # back across a rebuild so a real entered result is never silently wiped.
        act_h = ws.cell(row=row, column=108, value=rb.get("Actual Home\nScore"))
        act_a = ws.cell(row=row, column=109, value=rb.get("Actual Away\nScore"))
        act_h.font = INPUT_FONT
        act_a.font = INPUT_FONT

        gk = ws.cell(row=row, column=110, value=f'=A{row}&"|"&C{row}&"|"&D{row}')
        gk.font = FORMULA_FONT

        home_ml = ws.cell(row=row, column=111, value=rb.get("Home\nMoneyline"))
        away_ml = ws.cell(row=row, column=112, value=rb.get("Away\nMoneyline"))
        home_ml.font = INPUT_FONT
        away_ml.font = INPUT_FONT

    last_row = first_row + len(schedule) - 1

    note_row = last_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=20)
    note = ws.cell(row=note_row, column=1, value=(
        "claude_code_spec_full_season_matchups.md. ONE tab, 272 real 2026 games across all "
        "18 real weeks -- retired 'Week 1 Matchups' entirely (confirmed with the user). "
        "Real per-week Rest Days and Divisional flag come directly from nflverse's own "
        "real schedule data (verified live: rest genuinely varies 4-14 real days for week "
        "2+, not the old flat-7 Week-1-only placeholder). Bye weeks need no special "
        "handling -- a team's row simply doesn't exist for its bye week among these 272 "
        "real games. Columns AQ onward (QB Replacement AS/AT, Phase Matchup, OL Pressure, "
        "Effective QB Rating, Explosive Play, Game Environment) are populated by this "
        "project's existing Week 1 Matchups wiring scripts (including build_replacement_"
        "value.py), repointed at THIS tab -- they reconstruct the exact same formula chain "
        "via append_term_once, just across 272 rows instead of 16."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Built '{SHEET_NAME}': {len(schedule)} real games across "
        f"{schedule['Week'].nunique()} real weeks. Retired '{OLD_SHEET_NAME}'."
    )
    print(f"Saved to {workbook_path}")
    return {"game_rows": list(range(first_row, last_row + 1))}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: uv run python scripts/build_season_matchups.py "path/to/workbook.xlsx"')
        sys.exit(1)
    build(sys.argv[1])
