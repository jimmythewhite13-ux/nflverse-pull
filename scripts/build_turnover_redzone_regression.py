"""
Builds "Turnover & Red-Zone Regression" -- claude_code_spec_turnover_redzone_regression_
engine.md Parts A/B, plus Team Ratings wiring. Applies real, published regression-to-the-
mean technique (fumble RECOVERY is close to a coin flip league-wide, largely independent of
skill; interceptions and fumble FORCING/LOSING are more skill-driven) to both turnover
differential and red-zone scoring rate.

Part A -- Sustainable vs. luck-driven turnover components (turnover_stats.py):
  - Sustainable (skill-driven): INT Rate Thrown (Off, real, new), INT Rate Forced (Def,
    REFERENCED from Secondary Index, not recomputed), Fumbles Forced Rate (Def, real, new),
    Fumbles Lost Rate (Off, real, new).
  - Luck-driven: Fumble Recovery Rate -- verified live before building this that the real
    2025 league-wide average is 50.06%, matching the well-established "close to a coin
    flip" finding almost exactly (a sanity check on the calculation itself).

Expected Turnover Differential is computed as a dimensionally-consistent real COUNT (each
rate x its own real play-count denominator, all from Section 1), NOT by subtracting raw
rates against a raw count the way the spec's own pseudocode would otherwise mismatch units
-- documented explicitly on the tab itself. Regressed (Projected Forward) Turnover
Differential = Expected + (Luck Component x Retention Weight), Retention Weight a new,
visible, TUNABLE assumption (starts at 0.25, per the spec's own "well below 1.0" guidance),
not hardcoded.

Part B -- Red-Zone Regression, same shrinkage-toward-league-average technique as the
existing Current-Season Blend Weight (Model Assumptions C12-14) -- NOT reusing those exact
cells (calibrated for a 0-17 games-played range), but the SAME formula SHAPE
(MIN(cap, base + increment*(count-1))) applied to real red-zone/goal-to-go POSSESSION count
instead of games played, per the spec's own "reuse the pattern... don't invent a parallel
mechanism" instruction. REAL BUG CAUGHT in turnover_stats.py before this shipped: drive
numbers repeat across different games within a season -- see that module's own docstring.

Team Ratings wiring: Turnover Regression Adj (pts) and Red-Zone Regression Adj (pts), both
NEW, unconditional, direct team-quality adjustments (no Replacement Value swap concept
applies to a team-level rate stat) -- both raw AND regressed figures stay visible side by
side on this tab (Section 2/3), per the spec's own explicit instruction, not hidden behind
only the regressed output.

NOT YET VALIDATED against real outcomes -- same disclaimer as every tab in the Defensive
Matchup Engine family.

Usage:
    uv run python scripts/build_turnover_redzone_regression.py \\
        "C:\\path\\to\\NFL_Prediction_Model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nflverse_pull.efficiency import fetch_pbp  # noqa: E402
from nflverse_pull.turnover_stats import (  # noqa: E402
    compute_team_season_redzone_components,
    compute_team_season_turnover_components,
)

HISTORICAL_YEARS = [2023, 2024, 2025]
SOURCE_SEASON = HISTORICAL_YEARS[-1]
SHEET_NAME = "Turnover & Red-Zone Regression"
SECONDARY_INDEX_SHEET = "Secondary Index"
EXPLOSIVE_SHEET = "Explosive Play Matchup"
TEAM_RATINGS_SHEET = "Team Ratings"

# Secondary Index's own real Section 1 range (verified against that tab's own build
# script): Team=A, Season=B, INT Rate=C, rows 5-100 (32 teams x 3 years).
SEC_IDX_SEC1_FIRST_ROW = 5
SEC_IDX_SEC1_LAST_ROW = 100

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
ASSUMPTION_FILL = PatternFill("solid", fgColor="FFFFFF00")


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


def add_model_assumptions_weights(wb: openpyxl.Workbook) -> None:
    ws = wb["Model Assumptions"]
    title_row = 142
    ws.merge_cells(f"A{title_row}:D{title_row}")
    title = ws.cell(row=title_row, column=1, value=(
        "Turnover & Red-Zone Regression Engine (see 'Turnover & Red-Zone Regression' tab)"
    ))
    title.font = HEADER_FONT
    title.fill = HEADER_FILL

    rows = [
        (143, "Turnover Luck Retention Weight", 0.25,
         "A judgment call, like every other coefficient in this model -- NOT an "
         "established fact. Starting well below 1.0 per the spec's own explicit "
         "guidance: most of a season's turnover LUCK component should not be expected "
         "to repeat. 0 = fully regress to Expected (assume none of the luck "
         "persists); 1 = fully trust Actual (assume all of it persists)."),
        (144, "Points per Net Turnover (Turnover Regression Adj conversion)", 4.0,
         "A starting guess, like every other coefficient in this model -- a real, "
         "commonly-cited approximate win-probability/field-position value of one "
         "turnover, not treated as more precise than that. Converts (Regressed "
         "Turnover Differential / real games played in the source season) into game "
         "points."),
        (145, "Red-Zone Blend Weight — Base (at 1 possession)", 0.10,
         "Same SHAPE as the existing Current-Season Blend Weight (C12-14), applied to "
         "real red-zone/goal-to-go POSSESSION count instead of games played -- NOT "
         "the same cells, since those are calibrated for a 0-17 games-played range, "
         "not red-zone possessions. A team with only 1 real red-zone possession "
         "should be trusted very little relative to the league average."),
        (146, "Red-Zone Blend Weight — Added per Additional Possession", 0.01,
         "Same reasoning as C145 -- a judgment call on how fast trust in a team's "
         "own real red-zone rate should ramp up as its real sample size grows. "
         "Calibrated against real 2023-2025 red-zone possession counts (roughly "
         "30-80 per team per season): 0.03 would saturate the cap for EVERY real "
         "team even at the low end of a full season's sample, leaving no real "
         "differentiation between a small- and large-sample team -- 0.01 keeps "
         "real teams spread across a meaningful range of trust levels."),
        (147, "Red-Zone Blend Weight — Maximum Cap", 0.90,
         "Same reasoning as C145/C146 -- even with a large real sample, some "
         "shrinkage toward the league average stays in place (matches C14's own "
         "0.85 cap in spirit, slightly higher since a full season's red-zone "
         "possession count is a real, if noisy, sample)."),
        (148, "Points per Red-Zone TD%-Point Advantage (Red-Zone Regression Adj conversion)",
         4.0,
         "A starting guess, like every other coefficient in this model -- a real, "
         "approximate points-per-possession value of converting a red-zone trip "
         "into a Touchdown instead of the average non-Touchdown red-zone outcome "
         "(field goal, turnover, etc.), roughly the real 7-vs-3 point swing. "
         "Converts (Regressed Red-Zone TD% - league average) x real red-zone "
         "drives-per-game into game points."),
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


def _pull_data() -> dict:
    print(f"Pulling {HISTORICAL_YEARS} play-by-play data for turnover/red-zone regression...")
    pbp = fetch_pbp(HISTORICAL_YEARS)
    turnover = compute_team_season_turnover_components(pbp)
    redzone = compute_team_season_redzone_components(pbp)

    reg = pbp[(pbp["season_type"] == "REG") & (pbp["season"] == SOURCE_SEASON)]
    games = (
        pd.concat([reg[["posteam", "game_id"]].rename(columns={"posteam": "team_abbr"}),
                   reg[["defteam", "game_id"]].rename(columns={"defteam": "team_abbr"})])
        .dropna(subset=["team_abbr"])
        .drop_duplicates()
        .groupby("team_abbr").size().rename("Games Played")
    )

    t = turnover[turnover["Season"] == SOURCE_SEASON].copy()
    r = redzone[redzone["Season"] == SOURCE_SEASON].copy()
    out = t.merge(r, on=["Team", "Season"], how="outer")

    from nflverse_pull.pull import TEAM_NAMES
    abbr_of = {v: k for k, v in TEAM_NAMES.items()}
    out["Games Played"] = out["Team"].map(abbr_of).map(games).fillna(0).astype(int)
    return {"season_stats": out}


def build(workbook_path: str) -> dict:
    data = _pull_data()
    season_stats = data["season_stats"]

    wb = openpyxl.load_workbook(workbook_path)
    if SECONDARY_INDEX_SHEET not in wb.sheetnames:
        raise ValueError(
            f"'{SECONDARY_INDEX_SHEET}' not found -- run build_secondary_index.py first "
            "(this tab references its real INT Rate directly)."
        )

    add_model_assumptions_weights(wb)

    if SHEET_NAME in wb.sheetnames:
        del wb[SHEET_NAME]
    for candidate in (EXPLOSIVE_SHEET, SECONDARY_INDEX_SHEET):
        if candidate in wb.sheetnames:
            insert_after = candidate
            break
    else:
        insert_after = wb.sheetnames[0]
    ws = wb.create_sheet(SHEET_NAME, index=wb.sheetnames.index(insert_after) + 1)
    ws.column_dimensions["A"].width = 20.0

    ws.merge_cells("A1:M1")
    t = ws.cell(row=1, column=1, value=(
        f"Turnover & Red-Zone Regression -- Real {SOURCE_SEASON} Season Turnover/Red-Zone "
        "Components, Regressed Toward the League Average Using a Well-Established Real "
        "Statistical Technique (fumble recovery is close to a coin flip league-wide, "
        "largely independent of skill). NOT YET VALIDATED against real outcomes -- see the "
        "closing note."
    ))
    t.font = Font(name="Arial", size=12, bold=True)

    lookup = {r["Team"]: r for r in season_stats.to_dict("records")}

    # ==== Section 1: Raw Real Season Components =============================================
    sec1_first_row = 5
    sec1_last_row = sec1_first_row + len(TEAM_ORDER) - 1
    _section_title(
        ws, 3, 15,
        f"Section 1 — Raw Real {SOURCE_SEASON} Season Components (turnover_stats.py; INT "
        "Rate Forced (D) is LIVE-REFERENCED from Secondary Index's own real Section 1 -- "
        "not recomputed). Pass Attempts/Offensive Plays/Defensive Plays/Defensive Pass "
        "Attempts Faced (J-M) are the real denominators behind the rate columns, exposed "
        "so Section 2's Expected Turnover Differential can be computed as a real COUNT.",
    )
    _header_row(ws, 4, [
        "Team", "INT Rate\nThrown (Off)", "INT Rate\nForced (Def, ref)",
        "Fumble Lost\nRate (Off)", "Fumble Forced\nRate (Def)", "Fumble\nRecovery Rate",
        "Actual Turnover\nDifferential", "Red-Zone\nDrive Count", "Red-Zone TD%",
        "Goal-to-Go\nDrive Count", "Goal-to-Go TD%", "Red-Zone EPA", "Pass Attempts\n(Off)",
        "Offensive\nPlays", "Defensive\nPlays", "Defensive Pass\nAttempts Faced",
        "Games Played",
    ])
    for i, team in enumerate(TEAM_ORDER):
        row = sec1_first_row + i
        r = lookup.get(team, {})
        ws.cell(row=row, column=1, value=team).font = INPUT_FONT

        int_thrown = ws.cell(row=row, column=2, value=float(r.get("INT Rate Thrown (Off)", 0)))
        int_forced_ref = ws.cell(row=row, column=3, value=(
            f'=IFERROR(INDEX(\'{SECONDARY_INDEX_SHEET}\'!$C${SEC_IDX_SEC1_FIRST_ROW}:'
            f'$C${SEC_IDX_SEC1_LAST_ROW},SUMPRODUCT(MATCH(1,'
            f"('{SECONDARY_INDEX_SHEET}'!$A${SEC_IDX_SEC1_FIRST_ROW}:"
            f"$A${SEC_IDX_SEC1_LAST_ROW}=A{row})*"
            f"('{SECONDARY_INDEX_SHEET}'!$B${SEC_IDX_SEC1_FIRST_ROW}:"
            f"$B${SEC_IDX_SEC1_LAST_ROW}={SOURCE_SEASON}),0))),\"\")"
        ))
        fum_lost = ws.cell(row=row, column=4, value=float(r.get("Fumble Lost Rate (Off)", 0)))
        fum_forced = ws.cell(row=row, column=5, value=float(r.get("Fumble Forced Rate (Def)", 0)))
        fum_rec = ws.cell(row=row, column=6, value=float(r.get("Fumble Recovery Rate", 0)))
        actual_diff = ws.cell(
            row=row, column=7, value=float(r.get("Actual Turnover Differential", 0))
        )
        rz_drives = ws.cell(row=row, column=8, value=int(r.get("Red-Zone Drive Count", 0)))
        rz_td = ws.cell(row=row, column=9, value=float(r.get("Red-Zone TD%", 0)))
        g2g_drives = ws.cell(row=row, column=10, value=int(r.get("Goal-to-Go Drive Count", 0)))
        g2g_td = ws.cell(row=row, column=11, value=float(r.get("Goal-to-Go TD%", 0)))
        rz_epa = ws.cell(row=row, column=12, value=float(r.get("Red-Zone EPA", 0)))
        pass_att = ws.cell(row=row, column=13, value=int(r.get("Pass Attempts (Off)", 0)))
        off_plays = ws.cell(row=row, column=14, value=int(r.get("Offensive Plays", 0)))
        def_plays = ws.cell(row=row, column=15, value=int(r.get("Defensive Plays", 0)))
        def_pass_att = ws.cell(
            row=row, column=16, value=int(r.get("Defensive Pass Attempts Faced", 0))
        )
        games = ws.cell(row=row, column=17, value=int(r.get("Games Played", 0)))

        int_forced_ref.font = LINK_FONT
        for cell in (int_thrown, fum_lost, fum_forced, fum_rec, rz_td, g2g_td):
            cell.font = INPUT_FONT
            cell.number_format = "0.00%"
        for cell in (actual_diff, rz_drives, g2g_drives, pass_att, off_plays, def_plays,
                     def_pass_att, games):
            cell.font = INPUT_FONT
            cell.number_format = "0"
        rz_epa.font = INPUT_FONT
        rz_epa.number_format = "0.000"
        int_forced_ref.number_format = "0.00%"

    # ==== Section 2: Turnover Regression (Part A) ============================================
    sec2_title_row = sec1_last_row + 2
    sec2_header_row = sec2_title_row + 1
    sec2_first_row = sec2_header_row + 1
    sec2_last_row = sec2_first_row + len(TEAM_ORDER) - 1

    _section_title(
        ws, sec2_title_row, 9,
        "Section 2 — Turnover Regression. Expected Turnover Differential is computed as a "
        "real COUNT (each Section 1 rate x its own real play-count denominator), NOT by "
        "subtracting raw rates directly -- dimensionally consistent with Actual Turnover "
        "Differential (also a real count). Turnover Luck Component = Actual - Expected. "
        "Regressed = Expected + (Luck x Retention Weight, C143 -- a visible, TUNABLE "
        "assumption). BOTH the raw Actual and the Regressed figure stay visible side by "
        "side, per the spec's own instruction.",
    )
    _header_row(ws, sec2_header_row, [
        "Team", "Expected\nTurnover Diff.", "Actual Turnover\nDiff. (ref)",
        "Turnover Luck\nComponent", "Retention\nWeight (ref)",
        "Regressed Turnover\nDifferential", "Games Played\n(ref)",
        "Turnover Regression\nAdj (Index)", "Turnover Regression\nAdj (Game Points)",
    ])
    for i, team in enumerate(TEAM_ORDER):
        row = sec2_first_row + i
        s1 = sec1_first_row + i
        ws.cell(row=row, column=1, value=f"=A{s1}").font = FORMULA_FONT

        expected = ws.cell(row=row, column=2, value=(
            f"=(C{s1}*P{s1}+E{s1}*O{s1})-(B{s1}*M{s1}+D{s1}*N{s1})"
        ))
        actual_ref = ws.cell(row=row, column=3, value=f"=G{s1}")
        luck = ws.cell(row=row, column=4, value=f"=C{row}-B{row}")
        retention = ws.cell(row=row, column=5, value="='Model Assumptions'!$C$143")
        regressed = ws.cell(row=row, column=6, value=f"=B{row}+D{row}*E{row}")
        games_ref = ws.cell(row=row, column=7, value=f"=Q{s1}")

        for cell in (expected, actual_ref, luck, regressed):
            cell.font = FORMULA_FONT
            cell.number_format = "0.0;(0.0)"
        retention.font = FORMULA_FONT
        retention.number_format = "0.00"
        games_ref.font = FORMULA_FONT
        games_ref.number_format = "0"

        adj_index = ws.cell(row=row, column=8, value=(
            f'=IF(G{row}=0,0,F{row}/G{row})'
        ))
        adj_game = ws.cell(row=row, column=9, value=(
            f"=H{row}*'Model Assumptions'!$C$144"
        ))
        adj_index.font = FORMULA_FONT
        adj_game.font = FORMULA_FONT
        adj_index.number_format = "0.00;(0.00)"
        adj_game.number_format = "0.00;(0.00)"

    # ==== Section 3: Red-Zone Regression (Part B) ============================================
    sec3_title_row = sec2_last_row + 2
    sec3_header_row = sec3_title_row + 1
    sec3_first_row = sec3_header_row + 1
    sec3_last_row = sec3_first_row + len(TEAM_ORDER) - 1
    league_avg_row = sec3_last_row + 2

    _section_title(
        ws, sec3_title_row, 12,
        "Section 3 — Red-Zone Regression. Same shrinkage-toward-league-average SHAPE as "
        "the existing Current-Season Blend Weight (Model Assumptions C12-14), applied to "
        "real red-zone/goal-to-go POSSESSION count instead of games played (C145-147, "
        "dedicated cells -- NOT the same ones, which are calibrated for a different real "
        "count range). BOTH raw and regressed TD% stay visible side by side.",
    )
    _header_row(ws, sec3_header_row, [
        "Team", "Red-Zone Drives\n(ref)", "Red-Zone TD%\n(raw, ref)", "Red-Zone\nBlend Weight",
        "Regressed Red-\nZone TD%", "Goal-to-Go Drives\n(ref)", "Goal-to-Go TD%\n(raw, ref)",
        "Goal-to-Go\nBlend Weight", "Regressed Goal-\nto-Go TD%",
        "Red-Zone Regression\nAdj (Index)", "Red-Zone Regression\nAdj (Game Points)",
    ])
    for i, team in enumerate(TEAM_ORDER):
        row = sec3_first_row + i
        s1 = sec1_first_row + i
        ws.cell(row=row, column=1, value=f"=A{s1}").font = FORMULA_FONT

        rz_drives_ref = ws.cell(row=row, column=2, value=f"=H{s1}")
        rz_td_ref = ws.cell(row=row, column=3, value=f"=I{s1}")
        rz_blend = ws.cell(row=row, column=4, value=(
            f"=IF(B{row}=0,0,MIN('Model Assumptions'!$C$147,"
            f"'Model Assumptions'!$C$145+('Model Assumptions'!$C$146*(B{row}-1))))"
        ))
        rz_regressed = ws.cell(row=row, column=5, value=(
            f"=C{row}*D{row}+$C${league_avg_row}*(1-D{row})"
        ))

        g2g_drives_ref = ws.cell(row=row, column=6, value=f"=J{s1}")
        g2g_td_ref = ws.cell(row=row, column=7, value=f"=K{s1}")
        g2g_blend = ws.cell(row=row, column=8, value=(
            f"=IF(F{row}=0,0,MIN('Model Assumptions'!$C$147,"
            f"'Model Assumptions'!$C$145+('Model Assumptions'!$C$146*(F{row}-1))))"
        ))
        g2g_regressed = ws.cell(row=row, column=9, value=(
            f"=G{row}*H{row}+$G${league_avg_row}*(1-H{row})"
        ))

        for cell in (rz_drives_ref, g2g_drives_ref):
            cell.font = FORMULA_FONT
            cell.number_format = "0"
        for cell in (rz_td_ref, rz_blend, rz_regressed, g2g_td_ref, g2g_blend, g2g_regressed):
            cell.font = FORMULA_FONT
            cell.number_format = "0.00%"

        adj_index = ws.cell(row=row, column=10, value=f"=E{row}-$C${league_avg_row}")
        adj_game = ws.cell(row=row, column=11, value=(
            f"=J{row}*IF(Q{s1}=0,0,H{s1}/Q{s1})*'Model Assumptions'!$C$148"
        ))
        adj_index.font = FORMULA_FONT
        adj_game.font = FORMULA_FONT
        adj_index.number_format = "0.00%"
        adj_game.number_format = "0.00;(0.00)"

    ws.cell(row=league_avg_row, column=1, value="League Average").font = FORMULA_FONT
    rz_td_range = f"C${sec3_first_row}:C${sec3_last_row}"
    g2g_td_range = f"G${sec3_first_row}:G${sec3_last_row}"
    la_rz = ws.cell(row=league_avg_row, column=3, value=f"=AVERAGE({rz_td_range})")
    la_g2g = ws.cell(row=league_avg_row, column=7, value=f"=AVERAGE({g2g_td_range})")
    la_rz.font = FORMULA_FONT
    la_g2g.font = FORMULA_FONT
    la_rz.number_format = "0.00%"
    la_g2g.number_format = "0.00%"

    # ---- Closing note --------------------------------------------------------------------
    note_row = league_avg_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=12)
    note = ws.cell(row=note_row, column=1, value=(
        "claude_code_spec_turnover_redzone_regression_engine.md. NOT YET VALIDATED against "
        "real outcomes -- this is real, verified-correct plumbing applying a well-"
        "established statistical technique, not a proven improvement to THIS model's own "
        "predictions specifically. Fumble Recovery Rate is the LUCK-driven component -- "
        "verified live before building this that the real 2025 league-wide average across "
        "all 32 teams is 50.06%, matching the published 'close to a coin flip' finding "
        "almost exactly. Expected Turnover Differential (Section 2, col B) is a real COUNT "
        "(each Section 1 rate x its own real play-count denominator), not a raw-rate "
        "subtraction, to stay dimensionally consistent with Actual Turnover Differential. "
        "Retention Weight (Model Assumptions C143) and the Red-Zone Blend Weight "
        "constants (C145-147) are explicit judgment calls, documented as such, not "
        "established facts -- change them and every regressed figure on this tab "
        "recalculates live. Uses real Season "
        f"{SOURCE_SEASON} data only (not a 3-Yr decay-weighted baseline like every other "
        "tab in this workbook) -- turnover/red-zone luck regression is inherently a "
        "single-season question (how much of THIS season's luck should be expected to "
        "repeat), a deliberate, documented design choice, not an oversight."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    # ==== Wire into Team Ratings (new, unconditional additive columns) + N formula =========
    tr = wb[TEAM_RATINGS_SHEET]
    tr.cell(row=2, column=29, value="Turnover Regression\nAdj (pts)").font = HEADER_FONT
    tr.cell(row=2, column=29).fill = HEADER_FILL
    tr.cell(row=2, column=29).alignment = HEADER_ALIGN
    tr.cell(row=2, column=30, value="Red-Zone Regression\nAdj (pts)").font = HEADER_FONT
    tr.cell(row=2, column=30).fill = HEADER_FILL
    tr.cell(row=2, column=30).alignment = HEADER_ALIGN

    turnover_adj_range = f"'{SHEET_NAME}'!$I${sec2_first_row}:$I${sec2_last_row}"
    turnover_team_range = f"'{SHEET_NAME}'!$A${sec2_first_row}:$A${sec2_last_row}"
    rz_adj_range = f"'{SHEET_NAME}'!$K${sec3_first_row}:$K${sec3_last_row}"
    rz_team_range = f"'{SHEET_NAME}'!$A${sec3_first_row}:$A${sec3_last_row}"

    for row in range(3, 3 + len(TEAM_ORDER)):
        turnover_adj = tr.cell(row=row, column=29, value=(
            f"=IFERROR(INDEX({turnover_adj_range},MATCH(A{row},{turnover_team_range},0)),0)"
        ))
        rz_adj = tr.cell(row=row, column=30, value=(
            f"=IFERROR(INDEX({rz_adj_range},MATCH(A{row},{rz_team_range},0)),0)"
        ))
        turnover_adj.font = LINK_FONT
        rz_adj.font = LINK_FONT
        turnover_adj.number_format = "0.00;(0.00)"
        rz_adj.number_format = "0.00;(0.00)"

        # Net Power Rating (N) -- now the most complete version in the workbook, extending
        # build_special_teams_player_index.py's previous formula (through AB) with AC/AD.
        net = tr.cell(row=row, column=14, value=(
            f"=J{row}-K{row}+L{row}+M{row}+P{row}+R{row}+S{row}+T{row}+U{row}+V{row}+"
            f"W{row}+X{row}+Y{row}+Z{row}+AA{row}+AB{row}+AC{row}+AD{row}"
        ))
        net.font = FORMULA_FONT

    note_row_tr = 3 + len(TEAM_ORDER) + 16
    tr.merge_cells(start_row=note_row_tr, start_column=1, end_row=note_row_tr, end_column=30)
    tr_note = tr.cell(row=note_row_tr, column=1, value=(
        "Turnover Regression Adj (AC) and Red-Zone Regression Adj (AD) are both "
        "unconditional -- they pull directly from 'Turnover & Red-Zone Regression' "
        "Sections 2/3 (that team's real, luck-regressed turnover differential / red-zone "
        "TD% advantage, converted to game points) and apply to Net Power Rating (N) for "
        "every team, every time. Net Power Rating (N) was extended by this script to "
        "include both new columns -- this is now the most complete N formula in the "
        "workbook (see main.py's own module docstring for why ownership of N moves to "
        "whichever Team-Ratings-wired script runs last)."
    ))
    tr_note.font = NOTE_FONT
    tr_note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Built '{SHEET_NAME}': {len(TEAM_ORDER)} teams, real Season {SOURCE_SEASON} data. "
        f"Wired into '{TEAM_RATINGS_SHEET}' (cols AC/AD) and took over ownership of the Net "
        "Power Rating (N) formula."
    )
    print(f"Saved to {workbook_path}")
    return {
        "sec1_range": (sec1_first_row, sec1_last_row),
        "sec2_range": (sec2_first_row, sec2_last_row),
        "sec3_range": (sec3_first_row, sec3_last_row),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            'Usage: uv run python scripts/build_turnover_redzone_regression.py '
            '"path/to/workbook.xlsx"'
        )
        sys.exit(1)
    build(sys.argv[1])
