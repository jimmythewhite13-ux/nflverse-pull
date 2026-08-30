"""
Builds "Front Seven & D-Line Index" -- addresses part of Phase 4 of the multi-phase roadmap
in claude_code_spec_rb_index.md ("Defense -- counting-stats index only (sacks/TFL/INT/PBU),
explicitly NOT an EPA-equivalent value model"). Scoped to EDGE/interior-line/linebacker per
explicit user instruction -- secondary (CB/S, INT/PBU) is a separate future phase, not built
here. No separate written spec exists for this phase -- designed directly.

Real, individually-attributed counting stats throughout (defense_stats.py) -- no invented
per-position "grade" anywhere on this tab (see that module's and oline_stats.py's own
docstrings for why that pattern, used in an earlier user-supplied draft engine for both
offensive AND defensive line, was rejected: there is no honest free source for a 0-100
"Pass_Rush_Grade"/"Coverage_Grade"-style number; that's PFF's proprietary domain). Kept
from that draft: the decay-weighted baseline and Z-score-to-points conversion -- both real
techniques, applied to real inputs. NOT kept: the positional 0-100 grades, and the
Scheme_Shell_Type layer (coverage-shell charting has no free public source at all).

UPDATED: added real Blitz Rate / Avg Box Count context (Section 1, columns F/G), per
explicit user instruction to incorporate FTN Fantasy's real per-play charting (already
accessible via nfl_data_py.import_ftn_data -- see defense_stats.compute_team_season_
scheme_context). Deliberately informational, NOT part of the weighted Z-score composite: a
higher or lower blitz rate isn't inherently "better," it's a scheme choice, unlike Sack/
TFL/QB-Hit Rate which are unambiguously higher-is-better -- this was the exact future
contextual addition flagged when this tab was first built.

Structural note vs. Offensive Line Index: this tab does NOT need a Section-7-style
positional-weighted blend step. O-line's real data (Pass Protection/Run Blocking) was
inherently team-only, so it had to be redistributed to 5 individual starters with a
modifier and then re-aggregated using positional weights. Front-seven counting stats are
real and individual FIRST -- every credited sack/TFL/QB-hit from every real contributing
player already rolls up into the team-level rate in Section 1 directly. The three metric
weights in Section 5 (Sack Rate/TFL Rate/QB Hit Rate) already encode which type of
production matters most, without needing a separate per-position re-weighting step.

Section 1: raw 3-year TEAM-level rates (Sack Rate, TFL Rate, QB Hit Rate) from
           defense_stats.py -- team-level, built from every real contributing player
Section 2: league average per season (simple average across 32 teams)
Section 3: per-team 3-Yr decay-weighted, regressed baseline -- a missing year substitutes
           that season's own Section 2 league average (no rookie concept for a team stat)
Section 4: league average/std-dev of Section 3's projected baselines
Section 5: Z-scores, weighted composite, points-scale Team Front 7 Score (reuses QB
           Index's own Model Assumptions C37/C38 scale constants)
Section 6: Individual Real Production -- the current real starters at EDGE1/EDGE2,
           IDL1/IDL2, LB1/LB2/LB3 (current_roster.py's live depth-chart pull, mapped from
           the real scheme-specific labels onto these fixed slots via a documented
           priority order -- see _pick_idl_lb below), each showing THEIR OWN real season
           Sacks/TFL/QB Hits (defense_stats.compute_player_season_front7_stats) --
           informational, not fed back into team-level scoring (Section 1 already captures
           it via the team rollup)
Section 7: direct (not Replacement-Value-swap) Team Ratings adjustment, same unconditional
           pattern as Kicking/Offensive Line Index -- there's no "backup front seven" to
           swap in as a unit

Usage:
    uv run python scripts/build_defense_index.py "C:\\path\\to\\NFL_Prediction_Model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nflverse_pull.current_roster import (  # noqa: E402
    compute_current_starters,
    fetch_depth_charts,
    resolve_scored_population,
)
from nflverse_pull.defense_stats import (  # noqa: E402
    compute_player_season_front7_stats,
    compute_team_season_front7_stats,
    compute_team_season_scheme_context,
    fetch_ftn,
)
from nflverse_pull.efficiency import fetch_pbp  # noqa: E402

HISTORICAL_YEARS = [2023, 2024, 2025]
CURRENT_ROSTER_YEAR = 2026
SHEET_NAME = "Front Seven Index"  # Excel sheet titles can't contain "&"
OLINE_SHEET = "Offensive Line Index"
KICKING_SHEET = "Kicking Index"
WR_TE_SHEET = "WR-TE Value Index"
RB_INDEX_SHEET = "RB Value Index"
QB_INDEX_SHEET = "QB Index"
TEAM_RATINGS_SHEET = "Team Ratings"

METRICS = [
    {"key": "sack", "col": "Sack Rate", "label": "Sack\nRate", "fmt": "0.00%"},
    {"key": "tfl", "col": "TFL Rate", "label": "TFL\nRate", "fmt": "0.00%"},
    {"key": "hit", "col": "QB Hit Rate", "label": "QB Hit\nRate", "fmt": "0.00%"},
]

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

# EDGE is a clean, real 2-slot group for every team (LDE1 -> EDGE1, RDE1 -> EDGE2).
EDGE_MAP = [("LDE", "EDGE1"), ("RDE", "EDGE2")]
# Interior line and linebacker vary by real scheme (verified live -- see current_roster.py's
# own comment): this priority order picks up to 2 IDL / 3 LB real starters per team,
# whichever of the scheme-specific labels that team's real depth chart actually populates.
# Not fabrication -- every slot filled here is a real player at a real depth-chart position;
# a team whose scheme populates more than this (e.g. a 3-4's 4th linebacker, RILB) simply
# isn't scored, a documented limit, same as WR4+ elsewhere in this project.
IDL_PRIORITY = ["LDT", "RDT", "NT"]
LB_PRIORITY_FIXED = ["WLB", "SLB"]
LB_PRIORITY_THIRD = ["MLB", "LILB"]

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
    title_row = 68
    ws.merge_cells(f"A{title_row}:D{title_row}")
    title = ws.cell(row=title_row, column=1, value=(
        "Front Seven Index Weighting & Conversion (pts per std. dev.; reuses QB Index's "
        "points-scale constants C37/C38 -- see 'Front Seven Index' tab)"
    ))
    title.font = HEADER_FONT
    title.fill = HEADER_FILL

    rows = [
        (69, "Sack Rate Weight (Front 7 Index, pts per SD)", 0.4,
         "Real, individually-credited sacks per real pass play faced -- weighted "
         "highest as the clearest single pass-rush production signal."),
        (70, "TFL Rate Weight (Front 7 Index, pts per SD)", 0.3,
         "Real run-and-pass tackles for loss per real defensive play faced."),
        (71, "QB Hit Rate Weight (Front 7 Index, pts per SD)", 0.3,
         "Real QB hits per real pass play faced -- correlates with Sack Rate but "
         "captures pressure that didn't finish as a sack."),
        (72, "Front 7 Index Points-to-Game-Points Conversion", 0.07,
         "A starting guess, like every other coefficient in this model. This is a "
         "DIRECT quality adjustment, not a Replacement Value swap -- there's no "
         "'backup front seven' to swap in as a unit, same reasoning as Kicking "
         "Index's C56 and Offensive Line Index's C67."),
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


def _pick_idl_lb(population: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function. Remaps the real, scheme-specific IDL/LB depth-chart rows (LDT/RDT/NT,
    MLB/WLB/SLB/LILB/RILB) onto fixed IDL1/IDL2 and LB1/LB2/LB3 slots via the documented
    priority order -- see IDL_PRIORITY/LB_PRIORITY_FIXED/LB_PRIORITY_THIRD above. Every row
    returned is a REAL player at a REAL depth-chart position; this only renames the slot
    label, it never invents a player.
    """
    out_rows = []
    for team in population["Team"].unique():
        team_pop = population[population["Team"] == team].set_index("Role")

        idl_found = [pos for pos in IDL_PRIORITY if pos in team_pop.index][:2]
        for slot_num, pos in enumerate(idl_found, start=1):
            row = team_pop.loc[pos].to_dict()
            row["Team"], row["Role"] = team, f"IDL{slot_num}"
            out_rows.append(row)

        lb_found = [pos for pos in LB_PRIORITY_FIXED if pos in team_pop.index]
        for pos in LB_PRIORITY_THIRD:
            if pos in team_pop.index:
                lb_found.append(pos)
                break
        for slot_num, pos in enumerate(lb_found[:3], start=1):
            row = team_pop.loc[pos].to_dict()
            row["Team"], row["Role"] = team, f"LB{slot_num}"
            out_rows.append(row)

    return pd.DataFrame(out_rows, columns=["Team", "Role", "Player Name", "Player ID", "Source"])


def _pull_data() -> dict:
    print(f"Pulling {HISTORICAL_YEARS} play-by-play data for front-seven counting stats...")
    pbp = fetch_pbp(HISTORICAL_YEARS)
    team_stats = compute_team_season_front7_stats(pbp)
    player_stats = compute_player_season_front7_stats(pbp)

    print(f"Pulling {HISTORICAL_YEARS} FTN charting for real blitz-rate/box-count context...")
    ftn = fetch_ftn(HISTORICAL_YEARS)
    scheme_context = compute_team_season_scheme_context(pbp, ftn)
    # Context-only columns -- deliberately NOT part of METRICS/the weighted Z-score
    # composite (see defense_stats.py's module docstring for why).
    team_stats = team_stats.merge(scheme_context, on=["Team", "Season"], how="left")

    print(f"Pulling {CURRENT_ROSTER_YEAR} depth charts for the front-seven starters...")
    depth_charts = fetch_depth_charts([CURRENT_ROSTER_YEAR])
    current_starters = compute_current_starters(depth_charts)
    empty_overrides = pd.DataFrame(
        columns=["Team", "Manual Starter Override", "Manual Backup Override"]
    )
    raw_positions = (
        [pos for pos, _ in EDGE_MAP] + IDL_PRIORITY + LB_PRIORITY_FIXED + LB_PRIORITY_THIRD
    )
    raw_population = pd.concat(
        [
            resolve_scored_population(current_starters, empty_overrides, pos)
            for pos in raw_positions
        ],
        ignore_index=True,
    )

    edge_rows = []
    for pos, slot in EDGE_MAP:
        sub = raw_population[raw_population["Role"] == pos].copy()
        sub["Role"] = slot
        edge_rows.append(sub)
    edge_df = pd.concat(edge_rows, ignore_index=True)

    idl_lb_df = _pick_idl_lb(raw_population)
    starters = pd.concat([edge_df, idl_lb_df], ignore_index=True)

    role_priority = {"EDGE1": 1, "EDGE2": 2, "IDL1": 3, "IDL2": 4, "LB1": 5, "LB2": 6, "LB3": 7}
    starters["_priority"] = starters["Role"].map(role_priority)
    starters = starters.sort_values(["Team", "_priority"]).drop(columns="_priority")
    starters = starters.reset_index(drop=True)

    print(f"{len(starters)} current-roster front-seven starters identified across up to 7 "
          f"slots/team (EDGE1/EDGE2 always; IDL/LB vary by real scheme).")

    return {"team_stats": team_stats, "player_stats": player_stats, "starters": starters}


def build(workbook_path: str) -> dict:
    data = _pull_data()
    team_stats = data["team_stats"]
    player_stats = data["player_stats"]
    starters = data["starters"]

    wb = openpyxl.load_workbook(workbook_path)
    add_model_assumptions_weights(wb)

    if SHEET_NAME in wb.sheetnames:
        del wb[SHEET_NAME]
    for candidate in (OLINE_SHEET, KICKING_SHEET, WR_TE_SHEET, RB_INDEX_SHEET, QB_INDEX_SHEET):
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
        "Front Seven & D-Line Index -- Multi-Year Decay-Weighted TEAM-Level Pass-Rush/"
        "Run-Stop Rating (Sack Rate, TFL Rate, QB Hit Rate; real nflverse play-by-play "
        "counting stats), plus real Blitz Rate / Avg Box Count context from FTN Fantasy "
        "charting. Scoped to EDGE/interior line/linebacker -- secondary (CB/S, INT/PBU) "
        "is a separate future phase, not built here. NO invented per-position grade "
        "appears anywhere -- see the closing note."
    ))
    t.font = Font(name="Arial", size=12, bold=True)

    # ==== Section 1: Raw 3-year TEAM-level data ============================================
    sec1_first_row = 5
    sec1_last_row = sec1_first_row + len(team_stats) - 1
    _section_title(
        ws, 3, 7,
        "Section 1 \u2014 Raw 3-Year TEAM-Level Rates (real nflverse play-by-play counting "
        "stats, rolled up from every real contributing player). Blitz Rate / Avg Box "
        "Count (F/G, real FTN Fantasy charting) are CONTEXT ONLY -- not part of the "
        "weighted composite in Section 5 (see this tab's closing note for why).",
    )
    _header_row(ws, 4, [
        "Team", "Season", *[m["label"] for m in METRICS],
        "Blitz Rate\n(context only)", "Avg Box Count\n(context only)",
    ])
    for i, r in enumerate(team_stats.to_dict("records")):
        row = sec1_first_row + i
        values = [r["Team"], int(r["Season"]), r["Sack Rate"], r["TFL Rate"], r["QB Hit Rate"]]
        for col, v in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.font = INPUT_FONT
        for col in (3, 4, 5):
            ws.cell(row=row, column=col).number_format = "0.00%"

        blitz_v = float(r["Blitz Rate"]) if pd.notna(r.get("Blitz Rate")) else None
        box_v = float(r["Avg Box Count"]) if pd.notna(r.get("Avg Box Count")) else None
        blitz_cell = ws.cell(row=row, column=6, value=blitz_v)
        box_cell = ws.cell(row=row, column=7, value=box_v)
        blitz_cell.font = INPUT_FONT
        box_cell.font = INPUT_FONT
        blitz_cell.number_format = "0.00%"
        box_cell.number_format = "0.00"

    team_range = f"$A${sec1_first_row}:$A${sec1_last_row}"
    season_range = f"$B${sec1_first_row}:$B${sec1_last_row}"
    sec1_col_of = {"sack": "C", "tfl": "D", "hit": "E"}
    metric_ranges = {
        m["key"]: (
            f"${sec1_col_of[m['key']]}${sec1_first_row}:${sec1_col_of[m['key']]}${sec1_last_row}"
        )
        for m in METRICS
    }

    # ==== Section 2: League average per season ==============================================
    sec2_title_row = sec1_last_row + 2
    sec2_header_row = sec2_title_row + 1
    season_rows = {yr: sec2_header_row + 1 + i for i, yr in enumerate(HISTORICAL_YEARS)}

    _section_title(
        ws, sec2_title_row, 4,
        "Section 2 \u2014 League Average per Season (simple average across all 32 teams)",
    )
    _header_row(ws, sec2_header_row, ["Season", *[m["label"] for m in METRICS]], height=20)

    for yr in HISTORICAL_YEARS:
        row = season_rows[yr]
        c = ws.cell(row=row, column=1, value=yr)
        c.font = INPUT_FONT
        for j, m in enumerate(METRICS):
            formula = f"=AVERAGEIF({season_range},{yr},{metric_ranges[m['key']]})"
            cell = ws.cell(row=row, column=2 + j, value=formula)
            cell.font = FORMULA_FONT
            cell.number_format = m["fmt"]

    season_avg_col = {m["key"]: get_column_letter(2 + j) for j, m in enumerate(METRICS)}

    # ==== Section 3: Per-team decay-weighted, regressed baseline ===========================
    sec3_title_row = season_rows[HISTORICAL_YEARS[-1]] + 2
    sec3_header_row = sec3_title_row + 1
    sec3_first_row = sec3_header_row + 1
    n_teams = len(TEAM_ORDER)
    sec3_last_row = sec3_first_row + n_teams - 1
    sec3_last_col = 2 + len(METRICS) * 7

    _section_title(
        ws, sec3_title_row, sec3_last_col,
        "Section 3 \u2014 Per-Team 3-Yr Decay-Weighted, Regressed Baseline. A missing year "
        "substitutes THAT season's own Section 2 league average (no rookie concept for a "
        "team-level stat).",
    )
    headers = ["Team", "Years of\nReal History"]
    metric_block_start_col: dict[str, int] = {}
    col_cursor = 3
    for m in METRICS:
        metric_block_start_col[m["key"]] = col_cursor
        headers += [
            f"{m['label']} Y-1", f"{m['label']} Y-2", f"{m['label']} Y-3",
            f"Weighted\n{m['label']} Avg\n(3-Yr decay)", f"Team History\n{m['label']}",
            f"League Baseline\n{m['label']} (Y-1)", f"Projected 3-Yr\n{m['label']} Baseline",
        ]
        col_cursor += 7
    _header_row(ws, sec3_header_row, headers)

    for i, team in enumerate(TEAM_ORDER):
        row = sec3_first_row + i
        ws.cell(row=row, column=1, value=team).font = FORMULA_FONT

        years_hist_terms = "+".join(
            f"--(COUNTIFS({team_range},$A{row},{season_range},'Model Assumptions'!$C$18-{k})>0)"
            for k in (1, 2, 3)
        )
        yh = ws.cell(row=row, column=2, value=f"={years_hist_terms}")
        yh.font = FORMULA_FONT
        yh.number_format = "0"

        for m in METRICS:
            base = metric_block_start_col[m["key"]]
            y1, y2, y3, wavg, th, lb, pb = (get_column_letter(base + k) for k in range(7))
            mrange = metric_ranges[m["key"]]
            sec2_col = season_avg_col[m["key"]]

            def _ysub(offset: int, mrange=mrange, sec2_col=sec2_col) -> str:
                season_avg_lookup = (
                    f"INDEX(${sec2_col}${season_rows[HISTORICAL_YEARS[0]]}:"
                    f"${sec2_col}${season_rows[HISTORICAL_YEARS[-1]]},"
                    f"MATCH('Model Assumptions'!$C$18-{offset},"
                    f"$A${season_rows[HISTORICAL_YEARS[0]]}:"
                    f"$A${season_rows[HISTORICAL_YEARS[-1]]},0))"
                )
                return (
                    f"=IF(COUNTIFS({team_range},$A{row},{season_range},"
                    f"'Model Assumptions'!$C$18-{offset})=0,{season_avg_lookup},"
                    f"SUMIFS({mrange},{team_range},$A{row},{season_range},"
                    f"'Model Assumptions'!$C$18-{offset}))"
                )

            f_y1 = ws.cell(row=row, column=base, value=_ysub(1))
            f_y2 = ws.cell(row=row, column=base + 1, value=_ysub(2))
            f_y3 = ws.cell(row=row, column=base + 2, value=_ysub(3))
            f_wavg = ws.cell(row=row, column=base + 3, value=(
                f"=({y1}{row}*1+{y2}{row}*'Model Assumptions'!$C$20+"
                f"{y3}{row}*('Model Assumptions'!$C$20^2))/"
                f"(1+'Model Assumptions'!$C$20+'Model Assumptions'!$C$20^2)"
            ))
            f_th = ws.cell(row=row, column=base + 4, value=(
                f"={y1}{row}*'Model Assumptions'!$C$22+{wavg}{row}*(1-'Model Assumptions'!$C$22)"
            ))
            f_lb = ws.cell(row=row, column=base + 5, value=(
                f"=INDEX(${sec2_col}${season_rows[HISTORICAL_YEARS[0]]}:"
                f"${sec2_col}${season_rows[HISTORICAL_YEARS[-1]]},"
                f"MATCH('Model Assumptions'!$C$18-1,$A${season_rows[HISTORICAL_YEARS[0]]}:"
                f"$A${season_rows[HISTORICAL_YEARS[-1]]},0))"
            ))
            f_pb = ws.cell(row=row, column=base + 6, value=(
                f"={th}{row}*'Model Assumptions'!$C$21+{lb}{row}*(1-'Model Assumptions'!$C$21)"
            ))
            for cell in (f_y1, f_y2, f_y3, f_wavg, f_th, f_lb, f_pb):
                cell.font = FORMULA_FONT
                cell.number_format = m["fmt"]

    # ==== Section 4: League average/std-dev of Section 3's Projected Baselines =============
    sec4_title_row = sec3_last_row + 2
    sec4_header_row = sec4_title_row + 1
    avg_row, std_row = sec4_header_row + 1, sec4_header_row + 2

    _section_title(
        ws, sec4_title_row, 4, "Section 4 \u2014 League Average & Std. Dev. of the 3-Yr Baselines"
    )
    _header_row(ws, sec4_header_row, ["Stat", *[m["label"] for m in METRICS]], height=18)

    ws.cell(row=avg_row, column=1, value="League Average").font = FORMULA_FONT
    ws.cell(row=std_row, column=1, value="League Std. Dev.").font = FORMULA_FONT

    proj_baseline_col = {
        m["key"]: get_column_letter(metric_block_start_col[m["key"]] + 6) for m in METRICS
    }
    for j, m in enumerate(METRICS):
        pcol = proj_baseline_col[m["key"]]
        pb_range = f"{pcol}${sec3_first_row}:{pcol}${sec3_last_row}"
        a = ws.cell(row=avg_row, column=2 + j, value=f"=AVERAGE({pb_range})")
        s = ws.cell(row=std_row, column=2 + j, value=f"=STDEVP({pb_range})")
        for cell in (a, s):
            cell.font = FORMULA_FONT
            cell.number_format = m["fmt"]

    # ==== Section 5: Z-scores, weighted composite, points-scale Team Front 7 Score =========
    sec5_title_row = std_row + 2
    sec5_header_row = sec5_title_row + 1
    sec5_first_row = sec5_header_row + 1
    sec5_last_row = sec5_first_row + n_teams - 1

    _section_title(
        ws, sec5_title_row, 6,
        "Section 5 \u2014 Z-Scores and Team Front 7 Score (all three metrics are \"higher "
        "is better\" -- no sign-flip needed. Baseline/points-per-SD reuse QB Index's own "
        "Model Assumptions cells C37/C38.)",
    )
    _header_row(
        ws, sec5_header_row,
        ["Team", *[f"{m['label']}\nZ" for m in METRICS], "Weighted\nZ-Score Sum",
         "Team Front 7\nScore (Points)", "Years of\nReal History"],
    )

    avg_cell_ref = {
        m["key"]: f"${get_column_letter(2 + j)}${avg_row}" for j, m in enumerate(METRICS)
    }
    std_cell_ref = {
        m["key"]: f"${get_column_letter(2 + j)}${std_row}" for j, m in enumerate(METRICS)
    }
    weight_cells = {"sack": "$C$69", "tfl": "$C$70", "hit": "$C$71"}

    for i in range(n_teams):
        sec3_row = sec3_first_row + i
        row = sec5_first_row + i
        f = ws.cell(row=row, column=1, value=f"=A{sec3_row}")
        f.font = FORMULA_FONT

        z_cols = []
        for j, m in enumerate(METRICS):
            pcol = proj_baseline_col[m["key"]]
            formula = f"=({pcol}{sec3_row}-{avg_cell_ref[m['key']]})/{std_cell_ref[m['key']]}"
            col = 2 + j
            cell = ws.cell(row=row, column=col, value=formula)
            cell.font = FORMULA_FONT
            cell.number_format = "0.00"
            z_cols.append(get_column_letter(col))

        weighted_terms = " + ".join(
            f"{z_cols[j]}{row}*'Model Assumptions'!{weight_cells[m['key']]}"
            for j, m in enumerate(METRICS)
        )
        wz_col = 2 + len(METRICS)
        wz = ws.cell(row=row, column=wz_col, value=f"={weighted_terms}")
        wz.font = FORMULA_FONT
        wz.number_format = "0.00"

        score = ws.cell(row=row, column=wz_col + 1, value=(
            f"='Model Assumptions'!$C$37+{get_column_letter(wz_col)}{row}*'Model Assumptions'!$C$38"
        ))
        score.font = FORMULA_FONT
        score.number_format = "0.0;(0.0)"

        yh_link = ws.cell(row=row, column=wz_col + 2, value=f"=B{sec3_row}")
        yh_link.font = FORMULA_FONT
        yh_link.number_format = "0"

    sec5_score_col = get_column_letter(2 + len(METRICS) + 1)
    sec5_score_range = f"${sec5_score_col}${sec5_first_row}:${sec5_score_col}${sec5_last_row}"
    sec5_team_range = f"$A${sec5_first_row}:$A${sec5_last_row}"

    # ==== Section 6: Individual Real Production (informational) ============================
    sec6_title_row = sec5_last_row + 2
    sec6_header_row = sec6_title_row + 1
    sec6_first_row = sec6_header_row + 1
    n_starters = len(starters)
    sec6_last_row = sec6_first_row + n_starters - 1

    _section_title(
        ws, sec6_title_row, 8,
        "Section 6 \u2014 Individual Real Production (the current real starters at EDGE1/"
        "EDGE2, IDL1/IDL2, LB1/LB2/LB3 -- current_roster.py's live 2026 depth-chart pull, "
        "mapped from the real scheme-specific labels via a documented priority order, see "
        "this script's own comments). Sacks/TFL/QB Hits are THAT PLAYER'S OWN real "
        "2025 season totals (defense_stats.py) -- not a grade, and not fed back into "
        "Section 1-5 scoring (already captured there via the team rollup).",
    )
    _header_row(ws, sec6_header_row, [
        "Team", "Slot", "Player Name", "Player ID", "2025 Sacks", "2025 TFL",
        "2025 QB Hits", "Team Front 7\nScore (Points)",
    ], height=24)

    for i, r in enumerate(starters.to_dict("records")):
        row = sec6_first_row + i
        team = r["Team"]
        pid = r["Player ID"]
        ws.cell(row=row, column=1, value=team).font = INPUT_FONT
        ws.cell(row=row, column=2, value=r["Role"]).font = INPUT_FONT
        ws.cell(row=row, column=3, value=r["Player Name"]).font = INPUT_FONT
        ws.cell(row=row, column=4, value=pid).font = INPUT_FONT

        # A player may have multiple season rows (traded mid-history) -- filter to the most
        # recent pulled year specifically for this "current production" display column.
        recent = player_stats[
            (player_stats["Player ID"] == pid) & (player_stats["Season"] == HISTORICAL_YEARS[-1])
        ]
        sacks_v = float(recent["Sacks"].iloc[0]) if len(recent) else None
        tfl_v = float(recent["TFL"].iloc[0]) if len(recent) else None
        hits_v = float(recent["QB Hits"].iloc[0]) if len(recent) else None

        for col, v in ((5, sacks_v), (6, tfl_v), (7, hits_v)):
            cell = ws.cell(row=row, column=col, value=v)
            cell.font = INPUT_FONT
            cell.number_format = "0.0"

        team_score = ws.cell(row=row, column=8, value=(
            f'=IFERROR(INDEX({sec5_score_range},MATCH(A{row},{sec5_team_range},0)),"")'
        ))
        team_score.font = FORMULA_FONT
        team_score.number_format = "0.0;(0.0)"

    # ==== Section 7: Team Ratings adjustment (direct, unconditional) =======================
    sec7_title_row = sec6_last_row + 2
    sec7_header_row = sec7_title_row + 1
    sec7_first_row = sec7_header_row + 1
    sec7_last_row = sec7_first_row + len(TEAM_ORDER) - 1

    _section_title(
        ws, sec7_title_row, 4,
        "Section 7 \u2014 Front 7 Adjustment (pts) -- a DIRECT quality measure (Team Front "
        "7 Score minus the league-average baseline of 50, converted to game points), NOT a "
        "Replacement Value swap -- there's no 'backup front seven' to swap in as a unit.",
    )
    _header_row(ws, sec7_header_row, [
        "Team", "Front 7 Adjustment\n(Index Points)", "Front 7 Adjustment\n(Game Points)",
    ])

    for i, team in enumerate(TEAM_ORDER):
        row = sec7_first_row + i
        ws.cell(row=row, column=1, value=team).font = INPUT_FONT

        adj_index = ws.cell(row=row, column=2, value=(
            f'=IFERROR(INDEX({sec5_score_range},MATCH(A{row},{sec5_team_range},0))'
            f"-'Model Assumptions'!$C$37,\"\")"
        ))
        adj_game = ws.cell(row=row, column=3, value=(
            f'=IF(B{row}="","",B{row}*\'Model Assumptions\'!$C$72)'
        ))
        adj_index.font = FORMULA_FONT
        adj_game.font = FORMULA_FONT
        adj_index.number_format = "0.0;(0.0)"
        adj_game.number_format = "0.00;(0.00)"

    note_row = sec7_last_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=10)
    note = ws.cell(row=note_row, column=1, value=(
        "NO INVENTED PER-POSITION GRADE APPEARS ANYWHERE ON THIS TAB. Section 1-5 use REAL, "
        "individually-attributed nflverse play-by-play counting stats (sack_player_id / "
        "half_sack_1-2_player_id, qb_hit_1-2_player_id, tackle_for_loss_1-2_player_id), "
        "rolled up to team-level rates and run through the same decay-weighted/regressed/"
        "Z-scored chain as every other tab. UNLIKE Offensive Line Index, there is no "
        "separate positional-weighted blend step here -- the real team rate in Section 1 "
        "already sums every real contributing player's own production, so the Section 5 "
        "metric weights (Sack/TFL/QB-Hit Rate) already encode positional emphasis without "
        "needing a re-aggregation step. Section 6 shows the current real starters at "
        "EDGE1/EDGE2 (always LDE/RDE), IDL1/IDL2, and LB1/LB2/LB3 -- interior line and "
        "linebacker vary by real scheme (verified live: some teams' real depth charts run "
        "1-3 interior-line starters, 3-4 linebackers), mapped onto these fixed slots by a "
        "documented priority order, not fabricated. Their Sacks/TFL/QB Hits are THAT "
        "PLAYER'S OWN real 2025 totals -- informational only, not re-fed into scoring. "
        "SCOPE: this tab covers EDGE/interior line/linebacker only -- secondary (CB/S, "
        "INT/PBU) is a separate future phase (built separately as 'Secondary Index'). "
        "Section 1's Blitz Rate / Avg Box Count (F/G) are real, per-play FTN Fantasy "
        "charting (n_blitzers, n_defense_box, joined by game_id/play_id) -- DELIBERATELY "
        "CONTEXT ONLY, not part of Section 5's weighted composite: a higher or lower "
        "blitz rate isn't inherently 'better,' it's a scheme choice, unlike Sack/TFL/QB-"
        "Hit Rate which are unambiguously higher-is-better. NOT INCLUDED: coverage-shell "
        "scheme charting (single-high/two-high) has no free public source at all. The "
        "2026 depth-chart snapshot Section 6's starters are pulled from was pulled BEFORE "
        "final 53-man roster cuts -- same caveat as every other current-roster-driven tab "
        "in this workbook."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    # ==== Wire into Team Ratings (new, unconditional additive column) ======================
    tr = wb[TEAM_RATINGS_SHEET]
    tr.cell(row=2, column=21, value="Front 7\nAdjustment (pts)").font = HEADER_FONT
    tr.cell(row=2, column=21).fill = HEADER_FILL
    tr.cell(row=2, column=21).alignment = HEADER_ALIGN

    adj_game_range = f"'{SHEET_NAME}'!$C${sec7_first_row}:$C${sec7_last_row}"
    adj_team_range = f"'{SHEET_NAME}'!$A${sec7_first_row}:$A${sec7_last_row}"

    for row in range(3, 3 + len(TEAM_ORDER)):
        adj = tr.cell(row=row, column=21, value=(
            f"=IFERROR(INDEX({adj_game_range},MATCH(A{row},{adj_team_range},0)),0)"
        ))
        adj.font = LINK_FONT
        adj.number_format = "0.00;(0.00)"

        # Net Power Rating (N) now also includes the Front 7 Adjustment, additive alongside
        # QB (P), RB (R), Kicking (S), and OL (T) -- none disturb each other. This is now
        # the MOST COMPLETE version of the N formula -- see main.py's own ordering comment.
        net = tr.cell(row=row, column=14, value=(
            f"=J{row}-K{row}+L{row}+M{row}+P{row}+R{row}+S{row}+T{row}+U{row}"
        ))
        net.font = FORMULA_FONT
        net.number_format = "0.0;(0.0)"

    note_row_tr = 3 + len(TEAM_ORDER) + 4
    tr.merge_cells(start_row=note_row_tr, start_column=1, end_row=note_row_tr, end_column=21)
    tr_note = tr.cell(row=note_row_tr, column=1, value=(
        "Front 7 Adjustment (U) is unconditional, same reasoning as Kicking (S) and OL "
        "(T) Adjustments -- there's no 'backup front seven' to switch to. It pulls "
        "directly from 'Front Seven Index' Section 7 (that team's real, Z-scored Front 7 "
        "Score minus the league-average baseline, converted to game points) and applies "
        "to Net Power Rating (N) for every team, every time, alongside whatever QB/RB/"
        "Kicking/OL adjustments are also active."
    ))
    tr_note.font = NOTE_FONT
    tr_note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Built '{SHEET_NAME}': Section 1 {len(team_stats)} rows, Section 3/5 {n_teams} "
        f"teams, Section 6 {n_starters} starters, Section 7 {len(TEAM_ORDER)} teams. "
        f"Wired into '{TEAM_RATINGS_SHEET}' (col U)."
    )
    print(f"Saved to {workbook_path}")
    return {
        "sec1_rows": len(team_stats), "n_teams": n_teams, "n_starters": n_starters,
        "sec3_range": (sec3_first_row, sec3_last_row),
        "sec5_range": (sec5_first_row, sec5_last_row),
        "sec6_range": (sec6_first_row, sec6_last_row),
        "sec7_range": (sec7_first_row, sec7_last_row),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: uv run python scripts/build_defense_index.py "path/to/workbook.xlsx"')
        sys.exit(1)
    build(sys.argv[1])
