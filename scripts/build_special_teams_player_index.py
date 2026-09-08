"""
Builds "Special Teams Player Index" -- Part B/C of claude_code_spec_defensive_player_index.md,
extended per the user's explicit "fold in P/KR/PR now too" decision on the Full Engine
Completeness Tracker's open question. Real, individual, per-event-average production for the
punter (P), kickoff returner (KR), and punt returner (PR) -- complementary to Special Teams
Index (team-level Net Punt Average / Return Average, unchanged), the same relationship QB
Index has to Advanced Efficiency Metrics.

STRUCTURALLY DIFFERENT from EDGE/IDL Index, LB Index, and CB/S Index: those three tabs share
one common METRICS set (Sack/TFL/QB-Hit-Rate, or Tackle/TFL-Rate, or INT/PBU-Rate) across
every real slot in the tab. Punting and returning are not naturally combinable into a shared
metric set -- a punter's Net Punt Average and a returner's KR/PR Average measure completely
different, non-comparable skills. So this tab does NOT use a weighted multi-metric Z-score
composite. Each real role (P, KR, PR) has exactly ONE real governing stat, scored against
ONLY its own real population (punters scored against punters, kick returners against kick
returners, punt returners against punt returners) -- Section 1/3/5 are laid out as three
CONTIGUOUS role blocks (P block, then KR block, then PR block) specifically so Section 4's
league average/std-dev can reference a plain contiguous range per role, with no INDEX/MATCH
or array-formula filtering required.

HONESTY REQUIREMENT, same as every other tab in this spec, arguably sharper here: these are
real counting-derived per-event averages, but EVEN MORE scheme/teammate/luck-dependent than
front-seven or secondary counting stats. A punter's Net Punt Average is significantly shaped
by the return man he's kicking against, hang time his own gunners create room for, and even
weather/altitude at a given stadium -- none of which this tab can isolate. A returner's
average is enormously shaped by his own blocking unit's real performance, not just his own
open-field ability. DO NOT read these scores with anywhere near QB Index's confidence -- see
this tab's own closing note.

Real per-role qualifying-sample thresholds and real per-season rookie flag come from
special_teams_stats.py's compute_player_season_punting_rates() / compute_player_season_
return_rates() (MIN_QUALIFYING_PUNTS=20, MIN_QUALIFYING_KR_RETURNS=5,
MIN_QUALIFYING_PR_RETURNS=10 -- see that module's own docstring for the real-distribution
reasoning behind each). P, KR, and PR are all FIXED real 1:1 slots on the current depth
chart (current_roster.POSITION_ROLE_LABELS already carries P1/P2, KR1/KR2, PR1/PR2) --
resolved directly via resolve_slot_with_backup, same as CB/S Index's fixed secondary slots,
no scheme-variable priority remapping needed. Real coverage varies a lot by role (verified
live before building this: P has a real 2nd slot for only 14/32 teams -- most teams carry
one punter; KR/PR are real committee roles at many teams -- this tab captures the top-2 by
real depth-chart order at each, consistent with the "one pair per real slot" decision, same
limitation QB/RB/etc. Section 6 already documents for any slot missing a real 2nd name).

No Section 2B (same finding as every other Defensive Player Index tab -- zero defensive/
special-teams entries in fantasycalc's dynasty dataset). No man/zone coverage-shell content
(not applicable to special teams anyway).

LAST of the four new Defensive-Player-Index-family tabs in pipeline order -- per this
project's established Team-Ratings-N-formula convention (see main.py's own module
docstring), this script therefore OWNS the updated "most complete" Net Power Rating (Team
Ratings column N) formula, extending it to include EDGE/IDL Index (Y), LB Index (Z), CB/S
Index (AA), and this tab's own new column (AB) -- taking over ownership from build_special_
teams_index.py, which previously summed only through W.

Usage:
    uv run python scripts/build_special_teams_player_index.py \\
        "C:\\path\\to\\NFL_Prediction_Model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from add_manual_override_table import read_existing_overrides  # noqa: E402

from nflverse_pull.current_roster import (  # noqa: E402
    POSITION_ROLE_LABELS,
    compute_current_starters,
    fetch_depth_charts,
    fetch_seasonal_rosters,
    resolve_slot_with_backup,
)
from nflverse_pull.efficiency import fetch_pbp  # noqa: E402
from nflverse_pull.special_teams_stats import (  # noqa: E402
    compute_player_season_punting_rates,
    compute_player_season_return_rates,
)

HISTORICAL_YEARS = [2023, 2024, 2025]
CURRENT_ROSTER_YEAR = 2026
SHEET_NAME = "Special Teams Player Index"
CBS_SHEET = "CB-S Index"
SPECIAL_TEAMS_SHEET = "Special Teams Index"
TEAM_RATINGS_SHEET = "Team Ratings"

# Fixed real 1:1 roles -- each maps directly to its own scored slot, no priority remapping.
SLOT_ORDER = ["P", "KR", "PR"]
SLOT_LABEL = {"P": "Net Punt Avg\n(yds)", "KR": "KR Avg\n(yds)", "PR": "PR Avg\n(yds)"}

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


def add_model_assumptions(wb: openpyxl.Workbook) -> None:
    ws = wb["Model Assumptions"]
    title_row = 116
    ws.merge_cells(f"A{title_row}:D{title_row}")
    title = ws.cell(row=title_row, column=1, value=(
        "Special Teams Player Index Conversion (pts per std. dev.; reuses QB Index's "
        "points-scale constants C37/C38 -- see 'Special Teams Player Index' tab)"
    ))
    title.font = HEADER_FONT
    title.fill = HEADER_FILL

    row = 117
    ws.cell(row=row, column=2, value="Special Teams Player Index Repl. Value Conversion")
    c = ws.cell(row=row, column=3, value=0.05)
    c.font = INPUT_FONT
    c.fill = ASSUMPTION_FILL
    c.number_format = "0.00"
    n = ws.cell(row=row, column=4, value=(
        "A starting guess, like every other coefficient in this model -- ONE shared "
        "constant across all three real roles (P/KR/PR), same one-tab-one-conversion "
        "precedent as EDGE/IDL Index. These are the noisiest scores in the workbook "
        "(see this tab's own closing note) -- a given point gap here should move the "
        "prediction less than the same gap almost anywhere else."
    ))
    n.font = NOTE_FONT
    n.alignment = Alignment(wrap_text=True, vertical="top")


def _slots_to_population(slots: pd.DataFrame, slot_type: str) -> pd.DataFrame:
    rows = []
    for r in slots.to_dict("records"):
        if pd.notna(r["Starter Player ID"]):
            rows.append({
                "Team": r["Team"], "Role": f"{r['Slot']} Starter", "Slot Type": slot_type,
                "Player Name": r["Starter Name"], "Player ID": r["Starter Player ID"],
            })
        if pd.notna(r["Backup Player ID"]):
            rows.append({
                "Team": r["Team"], "Role": f"{r['Slot']} Backup", "Slot Type": slot_type,
                "Player Name": r["Backup Name"], "Player ID": r["Backup Player ID"],
            })
    return pd.DataFrame(
        rows, columns=["Team", "Role", "Slot Type", "Player Name", "Player ID"]
    )


def build(workbook_path: str) -> dict:
    wb = openpyxl.load_workbook(workbook_path)
    override_roles = [
        role for real_pos in SLOT_ORDER for role in POSITION_ROLE_LABELS[real_pos].values()
    ]
    overrides = read_existing_overrides(wb, SHEET_NAME, override_roles)
    print(f"Read back {len(overrides)} existing manual-override row(s) from Section 7 "
          "before rebuilding the sheet.")

    print(f"Pulling {HISTORICAL_YEARS} play-by-play data for P/KR/PR rate stats...")
    pbp = fetch_pbp(HISTORICAL_YEARS)
    rosters = fetch_seasonal_rosters(HISTORICAL_YEARS)

    punting = compute_player_season_punting_rates(pbp, rosters)
    returns = compute_player_season_return_rates(pbp, rosters)

    long_blocks = {
        "P": punting.rename(columns={"Net Punt Average": "Metric Value"})[
            ["Player ID", "Season", "Team", "Metric Value", "Is Rookie Season"]
        ],
        "KR": returns[returns["KR Average"].notna()].rename(
            columns={"KR Average": "Metric Value"}
        )[["Player ID", "Season", "Team", "Metric Value", "Is Rookie Season"]],
        "PR": returns[returns["PR Average"].notna()].rename(
            columns={"PR Average": "Metric Value"}
        )[["Player ID", "Season", "Team", "Metric Value", "Is Rookie Season"]],
    }
    for st, block in long_blocks.items():
        block.insert(3, "Slot Type", st)
    season_stats = pd.concat(
        [long_blocks[st] for st in SLOT_ORDER], ignore_index=True
    )[["Player ID", "Season", "Team", "Slot Type", "Metric Value", "Is Rookie Season"]]
    print(f"{len(season_stats)} qualifying special-teams player-role-seasons "
          f"(P={len(long_blocks['P'])}, KR={len(long_blocks['KR'])}, "
          f"PR={len(long_blocks['PR'])}; real rookie flag attached).")

    print(f"Pulling {CURRENT_ROSTER_YEAR} depth charts for P/KR/PR slots...")
    depth_charts = fetch_depth_charts([CURRENT_ROSTER_YEAR])
    current_starters = compute_current_starters(depth_charts)
    slots_by_type = {
        st: resolve_slot_with_backup(current_starters, overrides, st, st) for st in SLOT_ORDER
    }
    slots = pd.concat([slots_by_type[st] for st in SLOT_ORDER], ignore_index=True)
    population = pd.concat(
        [_slots_to_population(slots_by_type[st], st) for st in SLOT_ORDER], ignore_index=True
    )
    n_slots = len(slots)
    n_pop = len(population)
    print(f"{n_slots} real (team, slot) rows resolved; {n_pop} real players "
          f"(Starter+Backup) identified for scoring.")

    add_model_assumptions(wb)

    if SHEET_NAME in wb.sheetnames:
        del wb[SHEET_NAME]
    for candidate in (CBS_SHEET, SPECIAL_TEAMS_SHEET):
        if candidate in wb.sheetnames:
            insert_after = candidate
            break
    else:
        insert_after = wb.sheetnames[0]
    ws = wb.create_sheet(SHEET_NAME, index=wb.sheetnames.index(insert_after) + 1)
    ws.column_dimensions["A"].width = 20.0
    ws.column_dimensions["C"].width = 20.0

    ws.merge_cells("A1:H1")
    t = ws.cell(row=1, column=1, value=(
        "Special Teams Player Index -- Real, Individual Punt/Return Production for P, KR, "
        "PR. COMPLEMENTARY to Special Teams Index (team-level, unchanged). Each real role "
        "is scored against ONLY its own real population -- no cross-role composite. THE "
        "NOISIEST scores in this workbook -- see the closing note before treating these "
        "with any real confidence."
    ))
    t.font = Font(name="Arial", size=12, bold=True)

    # ==== Section 1: Raw 3-year per-role rate history, long format (all 3 roles) ===========
    sec1_first_row = 5
    sec1_last_row = sec1_first_row + len(season_stats) - 1
    _section_title(
        ws, 3, 6,
        "Section 1 — Raw 3-Year Per-Player-Role History (real nflverse pbp per-event "
        "averages -- see this tab's opening note). Below-threshold player-role-seasons "
        "are excluded entirely, not zero-filled.",
    )
    _header_row(ws, 4, [
        "Player ID", "Season", "Team", "Slot Type", "Metric Value", "Is Rookie Season",
    ])
    for i, r in enumerate(season_stats.to_dict("records")):
        row = sec1_first_row + i
        values = [
            r["Player ID"], int(r["Season"]), r["Team"], r["Slot Type"],
            float(r["Metric Value"]), bool(r["Is Rookie Season"]),
        ]
        for col, v in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.font = INPUT_FONT
        ws.cell(row=row, column=5).number_format = "0.0"

    id_range = f"$A${sec1_first_row}:$A${sec1_last_row}"
    season_range = f"$B${sec1_first_row}:$B${sec1_last_row}"
    slottype_range = f"$D${sec1_first_row}:$D${sec1_last_row}"
    metric_range = f"$E${sec1_first_row}:$E${sec1_last_row}"
    rookie_range = f"$F${sec1_first_row}:$F${sec1_last_row}"

    # ==== Section 2: League average per (Role, Season) + flat Rookie Baseline per Role =====
    sec2_title_row = sec1_last_row + 2
    row_cursor = sec2_title_row + 1
    _section_title(
        ws, sec2_title_row, 2,
        "Section 2 — League Average per Role/Season (all real qualifying player-role-"
        "seasons) + flat Rookie Baseline per Role, one contiguous block per role",
    )
    season_rows: dict[str, dict[int, int]] = {}
    rookie_baseline_row: dict[str, int] = {}
    for st in SLOT_ORDER:
        header_row = row_cursor
        _header_row(ws, header_row, [f"{st} — Season / Stat", "League Average"], height=18)
        season_rows[st] = {}
        row_cursor = header_row + 1
        for yr in HISTORICAL_YEARS:
            season_rows[st][yr] = row_cursor
            c = ws.cell(row=row_cursor, column=1, value=yr)
            c.font = INPUT_FONT
            f = ws.cell(row=row_cursor, column=2, value=(
                f'=AVERAGEIFS({metric_range},{slottype_range},"{st}",{season_range},{yr})'
            ))
            f.font = FORMULA_FONT
            f.number_format = "0.0"
            row_cursor += 1
        rookie_baseline_row[st] = row_cursor
        lbl = ws.cell(row=row_cursor, column=1, value="Rookie Baseline (all years, flat)")
        lbl.font = FORMULA_FONT
        f = ws.cell(row=row_cursor, column=2, value=(
            f'=AVERAGEIFS({metric_range},{slottype_range},"{st}",{rookie_range},TRUE)'
        ))
        f.font = FORMULA_FONT
        f.number_format = "0.0"
        row_cursor += 1
        lbl2 = ws.cell(row=row_cursor, column=1, value="Rookie Baseline Sample Size")
        lbl2.font = NOTE_FONT
        f2 = ws.cell(row=row_cursor, column=2, value=(
            f'=COUNTIFS({slottype_range},"{st}",{rookie_range},TRUE)'
        ))
        f2.font = FORMULA_FONT
        f2.number_format = "0"
        row_cursor += 2  # blank spacer row between role blocks

    flat_rookie_cell = {st: f"$B${rookie_baseline_row[st]}" for st in SLOT_ORDER}

    # ==== Section 3: Per-player 3-Yr decay-weighted, regressed baseline (per-role blocks) ==
    sec3_title_row = row_cursor
    sec3_header_row = sec3_title_row + 1
    sec3_first_row = sec3_header_row + 1
    n_players = len(population)
    sec3_last_row = sec3_first_row + n_players - 1

    _section_title(
        ws, sec3_title_row, 13,
        "Section 3 — Per-Player 3-Yr Decay-Weighted, Regressed Baseline. Population is "
        "every REAL player who could appear as either a Starter or Backup at P, KR, or PR "
        "-- laid out as three CONTIGUOUS role blocks (P, then KR, then PR) so Section 4 "
        "can average/std-dev each role's own real population directly. Missing years "
        "substitute that ROLE's own flat Section 2 Rookie Baseline -- no Section 2B (no "
        "real dynasty-fantasy market exists for special teams, verified live).",
    )
    headers = [
        "Player Name", "Player ID", "Team", "Role", "Slot Type", "Years of\nReal History",
        f"{'/'.join(SLOT_ORDER)}\nMetric Y-1", "Y-2", "Y-3", "Weighted\nAvg (3-Yr decay)",
        "Team History", "League Baseline\n(Y-1)", "Projected 3-Yr\nBaseline",
    ]
    _header_row(ws, sec3_header_row, headers)

    slot_start_row: dict[str, int] = {}
    slot_end_row: dict[str, int] = {}
    for i, p in enumerate(population.to_dict("records")):
        row = sec3_first_row + i
        st = p["Slot Type"]
        slot_start_row.setdefault(st, row)
        slot_end_row[st] = row

        ws.cell(row=row, column=1, value=p["Player Name"]).font = FORMULA_FONT
        ws.cell(row=row, column=2, value=p["Player ID"]).font = FORMULA_FONT
        ws.cell(row=row, column=3, value=p["Team"]).font = FORMULA_FONT
        ws.cell(row=row, column=4, value=p["Role"]).font = FORMULA_FONT
        ws.cell(row=row, column=5, value=st).font = FORMULA_FONT

        years_hist_terms = "+".join(
            f'--(COUNTIFS({id_range},$B{row},{season_range},'
            f'\'Model Assumptions\'!$C$18-{k},{slottype_range},"{st}")>0)'
            for k in (1, 2, 3)
        )
        yh = ws.cell(row=row, column=6, value=f"={years_hist_terms}")
        yh.font = FORMULA_FONT
        yh.number_format = "0"

        def _ysub(offset: int, st=st, row=row) -> str:
            flat_cell = flat_rookie_cell[st]
            return (
                f"=IF(COUNTIFS({id_range},$B{row},{season_range},"
                f"'Model Assumptions'!$C$18-{offset},{slottype_range},\"{st}\")=0,"
                f"{flat_cell},SUMIFS({metric_range},{id_range},$B{row},{season_range},"
                f"'Model Assumptions'!$C$18-{offset},{slottype_range},\"{st}\"))"
            )

        f_y1 = ws.cell(row=row, column=7, value=_ysub(1))
        f_y2 = ws.cell(row=row, column=8, value=_ysub(2))
        f_y3 = ws.cell(row=row, column=9, value=_ysub(3))
        f_wavg = ws.cell(row=row, column=10, value=(
            f"=(G{row}*1+H{row}*'Model Assumptions'!$C$20+"
            f"I{row}*('Model Assumptions'!$C$20^2))/"
            f"(1+'Model Assumptions'!$C$20+'Model Assumptions'!$C$20^2)"
        ))
        f_th = ws.cell(row=row, column=11, value=(
            f"=G{row}*'Model Assumptions'!$C$22+J{row}*(1-'Model Assumptions'!$C$22)"
        ))
        yrs = HISTORICAL_YEARS
        f_lb = ws.cell(row=row, column=12, value=(
            f"=INDEX($B${season_rows[st][yrs[0]]}:$B${season_rows[st][yrs[-1]]},"
            f"MATCH('Model Assumptions'!$C$18-1,$A${season_rows[st][yrs[0]]}:"
            f"$A${season_rows[st][yrs[-1]]},0))"
        ))
        f_pb = ws.cell(row=row, column=13, value=(
            f"=K{row}*'Model Assumptions'!$C$21+L{row}*(1-'Model Assumptions'!$C$21)"
        ))
        for cell in (f_y1, f_y2, f_y3, f_wavg, f_th, f_lb, f_pb):
            cell.font = FORMULA_FONT
            cell.number_format = "0.0"

    # ==== Section 4: League average/std-dev of Section 3's baselines, per role ==============
    sec4_title_row = sec3_last_row + 2
    sec4_header_row = sec4_title_row + 1
    row_cursor = sec4_header_row + 1

    _section_title(
        ws, sec4_title_row, 3,
        "Section 4 — League Average & Std. Dev. of the 3-Yr Baselines, PER ROLE (plain "
        "AVERAGE/STDEVP over each role's own contiguous Section 3 sub-range -- P scored "
        "only against P, KR only against KR, PR only against PR)",
    )
    _header_row(ws, sec4_header_row, ["Slot Type", "Baseline Avg", "Baseline Std. Dev."], height=18)

    avg_cell: dict[str, str] = {}
    std_cell: dict[str, str] = {}
    for st in SLOT_ORDER:
        row = row_cursor
        ws.cell(row=row, column=1, value=st).font = FORMULA_FONT
        rng = f"M${slot_start_row[st]}:M${slot_end_row[st]}"
        a = ws.cell(row=row, column=2, value=f"=AVERAGE({rng})")
        s = ws.cell(row=row, column=3, value=f"=STDEVP({rng})")
        for cell in (a, s):
            cell.font = FORMULA_FONT
            cell.number_format = "0.000"
        avg_cell[st] = f"$B${row}"
        std_cell[st] = f"$C${row}"
        row_cursor += 1

    # ==== Section 5: Z-score and Score (single governing stat per role) =====================
    sec5_title_row = row_cursor + 1
    sec5_header_row = sec5_title_row + 1
    sec5_first_row = sec5_header_row + 1
    sec5_last_row = sec5_first_row + n_players - 1

    _section_title(
        ws, sec5_title_row, 8,
        "Section 5 — Z-Score and Special Teams Player Index Score (one real governing "
        "stat per role -- Z is scored within that role's OWN population, not blended "
        "across roles. Baseline/points-per-SD reuse QB Index's own Model Assumptions "
        "cells C37/C38.)",
    )
    _header_row(ws, sec5_header_row, [
        "Player Name", "Player ID", "Team", "Role", "Slot Type", "Z-Score",
        "Index Score\n(Points)", "Years of\nReal History", "Team|Role\n(helper)",
    ])

    for i in range(n_players):
        sec3_row = sec3_first_row + i
        row = sec5_first_row + i
        st = population.iloc[i]["Slot Type"]
        for col, src_col in ((1, "A"), (2, "B"), (3, "C"), (4, "D"), (5, "E")):
            f = ws.cell(row=row, column=col, value=f"={src_col}{sec3_row}")
            f.font = FORMULA_FONT

        z = ws.cell(row=row, column=6, value=(
            f"=(M{sec3_row}-{avg_cell[st]})/{std_cell[st]}"
        ))
        z.font = FORMULA_FONT
        z.number_format = "0.00"

        score = ws.cell(row=row, column=7, value=(
            f"='Model Assumptions'!$C$37+F{row}*'Model Assumptions'!$C$38"
        ))
        score.font = FORMULA_FONT
        score.number_format = "0.0;(0.0)"

        yh_link = ws.cell(row=row, column=8, value=f"=F{sec3_row}")
        yh_link.font = FORMULA_FONT
        yh_link.number_format = "0"

        key = ws.cell(row=row, column=9, value=f'=C{row}&"|"&D{row}')
        key.font = FORMULA_FONT

    score_range = f"$G${sec5_first_row}:$G${sec5_last_row}"
    key_range = f"$I${sec5_first_row}:$I${sec5_last_row}"

    # ==== Section 6: Replacement Value, per real slot =======================================
    sec6_title_row = sec5_last_row + 2
    sec6_header_row = sec6_title_row + 1
    sec6_first_row = sec6_header_row + 1
    sec6_last_row = sec6_first_row + n_slots - 1

    _section_title(
        ws, sec6_title_row, 8,
        "Section 6 — Replacement Value, PER REAL SLOT (Starter Score minus Backup Score, "
        "can be negative -- a negative value means the backup rates HIGHER, and the game-"
        "point adjustment flips sign accordingly, same requirement as every other "
        "Replacement Value tab). A team missing a real backup (P2 is real for only "
        "14/32 teams) shows blank Replacement Value, not a misleading 0.",
    )
    _header_row(ws, sec6_header_row, [
        "Team", "Slot", "Starter Name", "Starter Score", "Backup Name", "Backup Score",
        "Replacement Value\n(Index Points)", "Replacement Value\n(Game Points)",
    ])

    for i, s in enumerate(slots.to_dict("records")):
        row = sec6_first_row + i
        team, slot = s["Team"], s["Slot"]
        t = ws.cell(row=row, column=1, value=team)
        sl = ws.cell(row=row, column=2, value=slot)
        t.font = INPUT_FONT
        sl.font = INPUT_FONT

        starter_key = f'"{team}|{slot} Starter"'
        backup_key = f'"{team}|{slot} Backup"'
        starter_name = ws.cell(row=row, column=3, value=(
            f'=IFERROR(INDEX($A${sec5_first_row}:$A${sec5_last_row},'
            f'MATCH({starter_key},{key_range},0)),"")'
        ))
        starter_score = ws.cell(row=row, column=4, value=(
            f"=IFERROR(INDEX({score_range},MATCH({starter_key},{key_range},0)),\"\")"
        ))
        backup_name = ws.cell(row=row, column=5, value=(
            f'=IFERROR(INDEX($A${sec5_first_row}:$A${sec5_last_row},'
            f'MATCH({backup_key},{key_range},0)),"")'
        ))
        backup_score = ws.cell(row=row, column=6, value=(
            f"=IFERROR(INDEX({score_range},MATCH({backup_key},{key_range},0)),\"\")"
        ))
        for cell in (starter_name, backup_name):
            cell.font = FORMULA_FONT
        for cell in (starter_score, backup_score):
            cell.font = FORMULA_FONT
            cell.number_format = "0.0;(0.0)"

        rv_index = ws.cell(row=row, column=7, value=(
            f'=IF(OR(D{row}="",F{row}=""),"",D{row}-F{row})'
        ))
        rv_game = ws.cell(row=row, column=8, value=(
            f'=IF(G{row}="","",G{row}*\'Model Assumptions\'!$C$117)'
        ))
        rv_index.font = FORMULA_FONT
        rv_game.font = FORMULA_FONT
        rv_index.number_format = "0.0;(0.0)"
        rv_game.number_format = "0.00;(0.00)"

    rv_game_range = f"'{SHEET_NAME}'!$H${sec6_first_row}:$H${sec6_last_row}"
    rv_team_range = f"'{SHEET_NAME}'!$A${sec6_first_row}:$A${sec6_last_row}"

    # ---- Closing note --------------------------------------------------------------------
    note_row = sec6_last_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=9)
    note = ws.cell(row=note_row, column=1, value=(
        "claude_code_spec_defensive_player_index.md (P/KR/PR folded in per the user's "
        "explicit decision on the Full Engine Completeness Tracker). HONESTY REQUIREMENT, "
        "sharper here than anywhere else in this workbook: these real per-event averages "
        "(Net Punt Average, KR/PR Average) are THE NOISIEST individual scores in the "
        "model. A punter's net average is significantly shaped by the return man he's "
        "kicking against, his own gunners' coverage, and even weather/altitude -- none of "
        "which this tab isolates. A returner's average is enormously shaped by his own "
        "blocking unit's real performance, not just his own ability. DO NOT read these "
        "scores with anywhere near QB Index's implied confidence. Each real role (P, KR, "
        "PR) is scored ONLY against its own real population -- there is no cross-role "
        "composite, unlike EDGE/IDL/LB/CB-S's shared multi-metric weighting, because "
        "punting and returning are not comparable skills. Real per-season rookie "
        "identification (current_roster.attach_real_rookie_season) was used from the "
        "START. Replacement Value (Section 6) is per real slot; P has a real 2nd slot for "
        "only 14/32 teams (most teams carry one punter) -- a blank Backup there is real, "
        "not a data gap. KR/PR are real committee roles at many teams; this tab captures "
        "only the top-2 by real depth-chart order at each, same limitation as every other "
        "multi-candidate slot in this workbook. The 2026 depth-chart snapshot this tab's "
        "population is built from was pulled BEFORE final 53-man roster cuts -- same "
        "caveat as every other current-roster-driven tab."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    # ==== Wire into Team Ratings (new column) + take over ownership of the Net Power Rating
    # (N) formula -- LAST of the four new Defensive-Player-Index-family tabs, per this
    # project's established convention (see main.py's own module docstring).
    tr = wb[TEAM_RATINGS_SHEET]
    tr_col = 28  # AB -- next free after CB/S Index's AA (27)
    tr.cell(row=2, column=tr_col, value="Special Teams\nPlayer Repl. Value\nAdj (pts)").font = (
        HEADER_FONT
    )
    tr.cell(row=2, column=tr_col).fill = HEADER_FILL
    tr.cell(row=2, column=tr_col).alignment = HEADER_ALIGN

    for row in range(3, 3 + len(TEAM_ORDER)):
        adj = tr.cell(row=row, column=tr_col, value=(
            f'=SUMIF({rv_team_range},A{row},{rv_game_range})'
        ))
        adj.font = LINK_FONT
        adj.number_format = "0.00;(0.00)"
        # Net Power Rating (N) -- now the most complete version in the workbook, extending
        # build_special_teams_index.py's previous formula (through X) with Y/Z/AA/AB.
        n_formula = tr.cell(row=row, column=14, value=(
            f"=J{row}-K{row}+L{row}+M{row}+P{row}+R{row}+S{row}+T{row}+U{row}+V{row}+"
            f"W{row}+X{row}+Y{row}+Z{row}+AA{row}+AB{row}"
        ))
        n_formula.font = FORMULA_FONT

    note_row_tr = 3 + len(TEAM_ORDER) + 14
    tr.merge_cells(start_row=note_row_tr, start_column=1, end_row=note_row_tr, end_column=tr_col)
    tr_note = tr.cell(row=note_row_tr, column=1, value=(
        "Special Teams Player Repl. Value Adj (AB) sums ALL of that team's real per-slot "
        "Replacement Value (Game Points) from 'Special Teams Player Index' Section 6 (P/"
        "KR/PR) into one Team Ratings column, unconditional. Net Power Rating (N) was "
        "extended by this script to include EDGE/IDL Repl. Value (Y), LB Repl. Value (Z), "
        "CB/S Repl. Value (AA), and this column (AB) -- this is now the most complete N "
        "formula in the workbook (see main.py's own module docstring for why ownership of "
        "N moves to whichever Team-Ratings-wired script runs last)."
    ))
    tr_note.font = NOTE_FONT
    tr_note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Built '{SHEET_NAME}': Section 1 {len(season_stats)} rows, Section 3/5 {n_players} "
        f"players, Section 6 {n_slots} real slots. Wired into '{TEAM_RATINGS_SHEET}' (col "
        f"AB) and took over ownership of the Net Power Rating (N) formula."
    )
    print(f"Saved to {workbook_path}")
    return {
        "sec1_rows": len(season_stats), "n_players": n_players, "n_slots": n_slots,
        "sec3_range": (sec3_first_row, sec3_last_row),
        "sec5_range": (sec5_first_row, sec5_last_row),
        "sec6_range": (sec6_first_row, sec6_last_row),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            'Usage: uv run python scripts/build_special_teams_player_index.py '
            '"path/to/workbook.xlsx"'
        )
        sys.exit(1)
    build(sys.argv[1])
