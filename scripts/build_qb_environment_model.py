"""
Builds "QB Environment Model" -- claude_code_spec_qb_environment_model.md Parts A/B. QB
Index produces one number: raw talent (EPA/Play, CPOE, ANY/A). This tab adds situational
context ON TOP, producing a SECOND, separate number per current QB Starter/Backup -- a "QB
Environment-Adjusted Baseline" (Raw Talent Score + Situational Adjustments) that a later
wiring step (build_effective_qb_rating_wiring.py) combines with opponent-specific,
game-by-game modifiers (OL vs. Pass Rush, Weather-on-Passing) into the final Effective QB
Rating used ONLY in the Pass Matchup Differential calculation on Week 1 Matchups.

QB INDEX ITSELF IS NOT TOUCHED ANYWHERE IN THIS SCRIPT -- its own Section 5 Score stays
completely unchanged, per the spec's own explicit acceptance criterion. Instead:

Part A -- new Talent metrics, watching for double-counting (see qb_stats.py's own module
docstring for the exact population/denominator of each):
  - Success Rate / Explosive Pass Rate: genuinely NEW per-QB metrics
    (qb_stats.compute_player_season_qb_extended_stats), given the SAME decay-weighted,
    regressed, Z-scored treatment as QB Index's own 3 metrics (Sections 1-4 below), then
    combined into a Raw QB Talent Score in Section 5 alongside QB Index's own EPA/Play,
    CPOE, and ANY/A Z-scores -- REFERENCED live from QB Index's own Section 5 (columns E/F/
    G, matched by the same Team|Role key QB Index's Section 6/Replacement Value already
    uses), not recomputed. QB Index's own weights (Model Assumptions C34-36) apply to those
    3 referenced Z's unchanged; only the 2 new metrics get NEW, modest weights (C128/C129)
    on top, per the spec's own "don't weight these as heavily as the original three"
    instruction -- deliberately NOT a full proportional rebalancing of all 5 (a smaller,
    additive layer on the existing 3, not a redesign of QB Index's own weighting).
  - TD/INT Ratio: CONTEXT ONLY (Section 1, col L) -- NOT part of the weighted composite
    anywhere. ANY/A's own formula (+20*TD-45*INT) already includes this signal; adding it
    again as a separate weighted input would double-count it, per the spec's own explicit
    instruction. Same treatment as PROE (Advanced Efficiency Metrics) -- real, visible,
    never scored.
  - Sack Rate: tracked (Sections 1-4, same decay-weighted treatment for stability) but NOT
    part of the Talent composite anywhere -- exposed in Section 5 as its own reference Z,
    consumed later by Part C's OL-modifier scaling (see build_effective_qb_rating_wiring.py).
    Taking a sack isn't inherently a skill deficiency; it matters specifically combined with
    a bad pass-protection environment, a different question than raw talent.

Part B -- QB Situation Flags (Section 6), small transparent tunable point penalties, same
treatment as Offensive Line Index's rookie-starter-risk penalties (Model Assumptions C60/
C61) -- NOT a black-box model:
  - New Team This Season: real, derived by comparing a player's current-roster team
    (current_roster.py) against his own most recent PRIOR season's team in this tab's own
    Section 1 raw data -- if they differ, flagged True. A true rookie (no prior team at all)
    is correctly NOT flagged (that's a different, already-tracked concept -- Is Rookie
    Season).
  - Recently Returned from Injury: real, derived from the SAME injury report data
    Availability Index already uses (nflverse_pull.availability.compute_player_injury_
    history) -- flagged True when a player's most recent real 'Out' designation fell in the
    back stretch of the most recently pulled season (RECENT_INJURY_WEEK_THRESHOLD=14,
    season==max(HISTORICAL_YEARS)). HONESTY NOTE: this is a real, verifiable signal for
    "entered the offseason banged up," not literal live 2026 practice-report status (which
    doesn't exist yet, pre-season) -- same "as of the last pulled data" caveat Availability
    Index's own Schedule Density section already carries.
  - Rookie/experience, Starter/Backup status: REFERENCED from QB Index (Is Rookie Season,
    Years of Real History, Role), not recomputed -- per the spec's own explicit instruction.
  - New offensive coordinator: NOT ATTEMPTED anywhere in this project -- confirmed no
    coaching-staff-history data source exists, per the spec's own explicit instruction.

Requires "QB Index" and "Availability Index" to already exist (run their own build scripts
first) -- this tab reads both live, referencing rather than recomputing wherever possible.

NOT YET COMBINED with the opponent-specific OL/Weather modifiers -- that's Part C, built
separately by build_effective_qb_rating_wiring.py (requires this tab, Offensive Line Index,
Pass Rush Generation Index, and the OL vs. Pass Rush Matchup wiring's differential columns
on Week 1 Matchups, none of which are per-QB, opponent-independent values this tab can hold).

Usage:
    uv run python scripts/build_qb_environment_model.py "C:\\path\\to\\NFL_Prediction_Model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
import pandas as pd
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from add_manual_override_table import read_existing_overrides  # noqa: E402

from nflverse_pull.availability import (  # noqa: E402
    compute_player_injury_history,
    fetch_injuries,
)
from nflverse_pull.current_roster import (  # noqa: E402
    attach_real_rookie_season,
    compute_current_starters,
    fetch_depth_charts,
    fetch_seasonal_rosters,
    merge_with_historical_fallback,
    resolve_scored_population,
)
from nflverse_pull.efficiency import fetch_pbp  # noqa: E402
from nflverse_pull.qb_stats import (  # noqa: E402
    compute_player_season_qb_extended_stats,
    compute_qb_roles,
    compute_team_season_qb_stats,
)

HISTORICAL_YEARS = [2023, 2024, 2025]
CURRENT_ROSTER_YEAR = 2026
SHEET_NAME = "QB Environment Model"
QB_INDEX_SHEET = "QB Index"
TEAM_RATINGS_SHEET = "Team Ratings"

# Real per-season Out designation in the back stretch of the most recently pulled season
# counts as "entered the offseason banged up" -- see this module's own HONESTY NOTE above.
# A definitional threshold (like MIN_QUALIFYING_DROPBACKS elsewhere), not an Excel-tunable
# cell -- only the resulting PENALTY point value is tunable, per the spec's own instruction.
RECENT_INJURY_WEEK_THRESHOLD = 14

# QB Index's own real Section 5 layout (verified against that tab's own build script /
# build_replacement_value.py, which already reads these same columns): Team=C, Role=D,
# EPA/Play Z=E, CPOE Z=F, ANY/A Z=G, Is Rookie n/a here (see Section 1 instead), Years of
# Real History=J, Team|Role key=K (written by build_replacement_value.py, not this tab).
QB_SEC5_TEAM_COL, QB_SEC5_ROLE_COL = "C", "D"
QB_SEC5_EPA_Z_COL, QB_SEC5_CPOE_Z_COL, QB_SEC5_ANYA_Z_COL = "E", "F", "G"
QB_SEC5_YEARS_HIST_COL, QB_SEC5_KEY_COL = "J", "K"

METRICS = [
    {"key": "success", "col": "Success Rate", "label": "Success\nRate", "sec1_col": "E",
     "fmt": "0.00"},
    {"key": "explosive", "col": "Explosive Pass Rate", "label": "Explosive\nPass Rate",
     "sec1_col": "F", "fmt": "0.00"},
    {"key": "sack", "col": "Sack Rate", "label": "Sack\nRate", "sec1_col": "G", "fmt": "0.00"},
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
    title_row = 127
    ws.merge_cells(f"A{title_row}:D{title_row}")
    title = ws.cell(row=title_row, column=1, value=(
        "QB Environment Model -- Talent Extension & Situational Adjustments (reuses QB "
        "Index's own EPA/CPOE/ANY-A weights C34-36 and points-scale C37/C38 -- see 'QB "
        "Environment Model' tab)"
    ))
    title.font = HEADER_FONT
    title.fill = HEADER_FILL

    rows = [
        (128, "Success Rate Weight (QB Environment Model Talent, pts per SD)", 0.15,
         "claude_code_spec_qb_environment_model.md Part A. A NEW, modest weight added "
         "ON TOP of QB Index's own 3 weights (C34-36, unchanged) -- correlates with "
         "EPA/Play, so weighted well below it to avoid double-counting, per the "
         "spec's own explicit instruction."),
        (129, "Explosive Pass Rate Weight (QB Environment Model Talent, pts per SD)", 0.15,
         "Same reasoning as C128 -- correlates with CPOE/air yards, weighted modestly."),
        (130, "New Team This Season Penalty (pts)", 1.0,
         "A starting guess, like every other coefficient in this model. Applied to a "
         "QB's real Situational Adjustment when his current-roster team differs from "
         "his own most recent prior-season team -- a real, documented continuity-risk "
         "proxy, same treatment as OL Index's rookie-starter penalties (C60/C61), NOT "
         "a fabricated skill grade."),
        (131, "Recently Returned from Injury Penalty (pts)", 1.0,
         "A starting guess, like every other coefficient in this model. Applied when a "
         "QB's most recent real Out designation fell within the back stretch "
         f"(week >= {RECENT_INJURY_WEEK_THRESHOLD}) of the most recently pulled season "
         "-- see this tab's own HONESTY NOTE for why this is a real but imperfect proxy "
         "for entering the season banged up, not live practice-report status."),
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


def _pull_data(overrides: pd.DataFrame) -> dict:
    print(f"Pulling {HISTORICAL_YEARS} play-by-play data for QB extended stats...")
    pbp = fetch_pbp(HISTORICAL_YEARS)
    stats = compute_team_season_qb_stats(pbp)

    print(f"Pulling {HISTORICAL_YEARS} seasonal rosters for real Is Rookie Season data...")
    rosters = fetch_seasonal_rosters(HISTORICAL_YEARS)
    stats = attach_real_rookie_season(stats, rosters)

    roles = compute_qb_roles(stats)
    role_lookup = {(r["Player ID"], r["Season"]): r["Role"] for r in roles.to_dict("records")}
    stats = stats.copy()
    stats["Role"] = [
        role_lookup.get((pid, season), "Other")
        for pid, season in zip(stats["Player ID"], stats["Season"], strict=True)
    ]

    ext = compute_player_season_qb_extended_stats(pbp)
    stats = stats.merge(ext, on=["Player ID", "Season", "Team"], how="left")
    stats = stats.sort_values(
        ["Team", "Season", "Dropbacks"], ascending=[True, True, False]
    ).reset_index(drop=True)

    # Same population QB Index itself uses -- current-roster Starters/Backups (Section 7's
    # own override table lives on QB Index, read here too so both tabs stay consistent),
    # falling back to the historical proxy only where the current pull/override left a gap.
    current_season = max(HISTORICAL_YEARS)
    historical_proxy = (
        roles[(roles["Season"] == current_season) & (roles["Role"].isin(["Starter", "Backup"]))]
        [["Team", "Role", "Player Name", "Player ID"]]
        .reset_index(drop=True)
    )
    print(f"Pulling {CURRENT_ROSTER_YEAR} depth charts for current-roster QB population...")
    depth_charts = fetch_depth_charts([CURRENT_ROSTER_YEAR])
    current_starters = compute_current_starters(depth_charts)
    current_population = resolve_scored_population(current_starters, overrides, "QB")
    population = merge_with_historical_fallback(current_population, historical_proxy)
    print(f"{len(population)} current-roster QB Starters/Backups (same population QB Index "
          "itself scores).")

    # Part B -- New Team This Season: real, from each player's own most recent PRIOR
    # season's team in this tab's own Section 1 raw data.
    most_recent_team: dict[str, str] = {}
    for pid, grp in stats.groupby("Player ID"):
        most_recent_team[pid] = grp.sort_values("Season", ascending=False).iloc[0]["Team"]
    population = population.copy()
    population["Most Recent Prior Team"] = population["Player ID"].map(most_recent_team)
    population["New Team This Season"] = (
        population["Most Recent Prior Team"].notna()
        & (population["Most Recent Prior Team"] != population["Team"])
    )

    # Part B -- Recently Returned from Injury: real, from the SAME injury report data
    # Availability Index already uses.
    print(f"Pulling {HISTORICAL_YEARS} injury reports for real 'Recently Returned from "
          "Injury' flag...")
    injuries = fetch_injuries(HISTORICAL_YEARS)
    injury_hist = compute_player_injury_history(injuries, set(population["Player ID"]))
    injury_lookup = injury_hist.set_index("Player ID").to_dict("index")
    population["Recently Returned from Injury"] = [
        bool(
            injury_lookup.get(pid, {}).get("Most Recent Out Season") == current_season
            and (injury_lookup.get(pid, {}).get("Most Recent Out Week") or 0)
            >= RECENT_INJURY_WEEK_THRESHOLD
        )
        for pid in population["Player ID"]
    ]

    return {"stats": stats, "population": population}


def build(workbook_path: str) -> dict:
    wb = openpyxl.load_workbook(workbook_path)
    if QB_INDEX_SHEET not in wb.sheetnames:
        raise ValueError(f"'{QB_INDEX_SHEET}' not found -- run build_qb_index.py first.")

    overrides = read_existing_overrides(wb, QB_INDEX_SHEET, ["Starter", "Backup"])
    data = _pull_data(overrides)
    stats = data["stats"]
    population = data["population"]
    n_qb = len(population)

    add_model_assumptions_weights(wb)

    if SHEET_NAME in wb.sheetnames:
        del wb[SHEET_NAME]
    ws = wb.create_sheet(SHEET_NAME, index=wb.sheetnames.index(QB_INDEX_SHEET) + 1)
    ws.column_dimensions["A"].width = 18.0
    ws.column_dimensions["C"].width = 20.0

    ws.merge_cells("A1:L1")
    t = ws.cell(row=1, column=1, value=(
        "QB Environment Model -- Talent Extension (Success Rate, Explosive Pass Rate; real "
        "Sack Rate tracked separately) + real Situational Adjustments (New Team, Recently "
        "Returned from Injury). QB Index's own raw Score is COMPLETELY UNCHANGED by this "
        "tab -- see the closing note for how this feeds the Effective QB Rating, built "
        "separately by build_effective_qb_rating_wiring.py."
    ))
    t.font = Font(name="Arial", size=12, bold=True)

    # ==== Section 1: Raw 3-year extended QB data ===========================================
    sec1_first_row = 5
    sec1_last_row = sec1_first_row + len(stats) - 1
    _section_title(
        ws, 3, 13,
        "Section 1 — Raw 3-Year Extended QB Data (from nflverse pbp; Role here is "
        "HISTORICAL attempts-ranking per past season, same as QB Index's own Section 1 -- "
        "labeling only, NOT used to pick who is scored in Section 3/5). TD/INT (J/K) and "
        "TD/INT Ratio (L) are CONTEXT ONLY, never scored -- ANY/A's own formula already "
        "includes this signal. TD/INT Ratio is blank when INT=0 (undefined), not a "
        "fabricated infinity. Dropbacks (M) is real, from qb_stats.py -- carried here "
        "(QB Index's own Section 1 doesn't expose it) specifically so build_effective_qb_"
        "rating_wiring.py can compute each team's real current-season pass rate.",
    )
    _header_row(
        ws, 4,
        ["Player Name", "Player ID", "Team", "Season", "Success Rate", "Explosive Pass Rate",
         "Sack Rate", "Is Rookie Season", "Role", "TD\n(context only)", "INT\n(context only)",
         "TD/INT Ratio\n(context only)", "Dropbacks\n(context only)"],
    )
    for i, r in enumerate(stats.to_dict("records")):
        row = sec1_first_row + i
        values = [
            r["Player Name"], r["Player ID"], r["Team"], int(r["Season"]),
            float(r["Success Rate"]), float(r["Explosive Pass Rate"]), float(r["Sack Rate"]),
            bool(r["Is Rookie Season"]), r["Role"],
        ]
        for col, v in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.font = INPUT_FONT
            if col in (5, 6, 7):
                cell.number_format = "0.00"

        td_v = int(r["TD"]) if pd.notna(r.get("TD")) else None
        int_v = int(r["INT"]) if pd.notna(r.get("INT")) else None
        ratio_v = float(r["TD/INT Ratio"]) if pd.notna(r.get("TD/INT Ratio")) else None
        dropbacks_v = int(r["Dropbacks"])
        for col, v, fmt in (
            (10, td_v, "0"), (11, int_v, "0"), (12, ratio_v, "0.00"), (13, dropbacks_v, "0"),
        ):
            cell = ws.cell(row=row, column=col, value=v)
            cell.font = INPUT_FONT
            cell.number_format = fmt

    id_range = f"$B${sec1_first_row}:$B${sec1_last_row}"
    season_range = f"$D${sec1_first_row}:$D${sec1_last_row}"
    rookie_range = f"$H${sec1_first_row}:$H${sec1_last_row}"
    role_range = f"$I${sec1_first_row}:$I${sec1_last_row}"
    metric_ranges = {
        m["key"]: f"${m['sec1_col']}${sec1_first_row}:${m['sec1_col']}${sec1_last_row}"
        for m in METRICS
    }

    # ==== Section 2: League average per season (Starters+Backups) + flat Rookie Baseline ===
    sec2_title_row = sec1_last_row + 2
    sec2_header_row = sec2_title_row + 1
    season_rows = {yr: sec2_header_row + 1 + i for i, yr in enumerate(HISTORICAL_YEARS)}
    rookie_baseline_row = sec2_header_row + 1 + len(HISTORICAL_YEARS)
    rookie_count_row = rookie_baseline_row + 1

    _section_title(
        ws, sec2_title_row, 4,
        "Section 2 — League Average per Season (Starters + Backups only, same historical "
        "Role filter as QB Index's own Section 2) and flat Rookie Baseline. NO Section 2B "
        "on this tab (documented simplification, not an oversight) -- a missing year falls "
        "back directly to this flat baseline rather than a per-player ADP-informed "
        "assumption, since these 2 supplementary metrics don't warrant re-running the full "
        "rookie market-value crosswalk QB Index's own Section 2B already does.",
    )
    _header_row(ws, sec2_header_row, ["Season / Stat", *[m["label"] for m in METRICS]], height=20)

    for yr in HISTORICAL_YEARS:
        row = season_rows[yr]
        c = ws.cell(row=row, column=1, value=yr)
        c.font = INPUT_FONT
        for j, m in enumerate(METRICS):
            formula = (
                f"=AVERAGEIFS({metric_ranges[m['key']]},{season_range},{yr},"
                f"{role_range},\"<>Other\")"
            )
            cell = ws.cell(row=row, column=2 + j, value=formula)
            cell.font = FORMULA_FONT
            cell.number_format = m["fmt"]

    lbl = ws.cell(row=rookie_baseline_row, column=1, value="Rookie Baseline (all years, flat)")
    lbl.font = FORMULA_FONT
    for j, m in enumerate(METRICS):
        formula = f"=AVERAGEIF({rookie_range},TRUE,{metric_ranges[m['key']]})"
        cell = ws.cell(row=rookie_baseline_row, column=2 + j, value=formula)
        cell.font = FORMULA_FONT
        cell.number_format = m["fmt"]

    lbl2 = ws.cell(
        row=rookie_count_row, column=1,
        value="Rookie Baseline Sample Size (qualifying rookie seasons) -- small-sample "
              "estimate; recomputes automatically as more seasons are added",
    )
    lbl2.font = NOTE_FONT
    lbl2.alignment = Alignment(wrap_text=True)
    for j in range(len(METRICS)):
        cell = ws.cell(row=rookie_count_row, column=2 + j, value=f"=COUNTIF({rookie_range},TRUE)")
        cell.font = FORMULA_FONT
        cell.number_format = "0"

    flat_rookie_cell = {
        m["key"]: f"${get_column_letter(2 + j)}${rookie_baseline_row}"
        for j, m in enumerate(METRICS)
    }
    season_avg_col = {m["key"]: get_column_letter(2 + j) for j, m in enumerate(METRICS)}

    # ==== Section 3: Per-QB decay-weighted, regressed baseline (3 metrics) =================
    sec3_title_row = rookie_count_row + 2
    sec3_header_row = sec3_title_row + 1
    sec3_first_row = sec3_header_row + 1
    sec3_last_row = sec3_first_row + n_qb - 1
    sec3_last_col = 4 + len(METRICS) * 7

    _section_title(
        ws, sec3_title_row, sec3_last_col,
        "Section 3 — Per-QB 3-Yr Decay-Weighted, Regressed Baseline (Success Rate, "
        "Explosive Pass Rate, Sack Rate). Population is the IDENTICAL current-roster "
        "Starters + Backups QB Index itself scores (same override table, same historical-"
        "proxy fallback) -- so this tab's Team|Role key matches QB Index's own 1:1. "
        "Missing years fall back to the flat Section 2 Rookie Baseline (no Section 2B here).",
    )
    headers = ["Player Name", "Player ID", "Team", "Role"]
    metric_block_start_col: dict[str, int] = {}
    col_cursor = 5
    for m in METRICS:
        metric_block_start_col[m["key"]] = col_cursor
        headers += [
            f"{m['label']} Y-1", f"{m['label']} Y-2", f"{m['label']} Y-3",
            f"Weighted\n{m['label']} Avg\n(3-Yr decay)", f"Team History\n{m['label']}",
            f"League Baseline\n{m['label']} (Y-1)", f"Projected 3-Yr\n{m['label']} Baseline",
        ]
        col_cursor += 7
    _header_row(ws, sec3_header_row, headers)

    for i, qb in enumerate(population.to_dict("records")):
        row = sec3_first_row + i
        ws.cell(row=row, column=1, value=qb["Player Name"]).font = FORMULA_FONT
        ws.cell(row=row, column=2, value=qb["Player ID"]).font = FORMULA_FONT
        ws.cell(row=row, column=3, value=qb["Team"]).font = FORMULA_FONT
        ws.cell(row=row, column=4, value=qb["Role"]).font = FORMULA_FONT

        for m in METRICS:
            base = metric_block_start_col[m["key"]]
            y1, y2, y3, wavg, th, lb, pb = (get_column_letter(base + k) for k in range(7))
            mrange = metric_ranges[m["key"]]
            flat_cell = flat_rookie_cell[m["key"]]

            def _ysub(offset: int, mrange=mrange, flat_cell=flat_cell) -> str:
                return (
                    f"=IF(COUNTIFS({id_range},$B{row},{season_range},"
                    f"'Model Assumptions'!$C$18-{offset})=0,{flat_cell},"
                    f"SUMIFS({mrange},{id_range},$B{row},{season_range},"
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
            sec2_col = season_avg_col[m["key"]]
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
        ws, sec4_title_row, 4, "Section 4 — League Average & Std. Dev. of the 3-Yr Baselines"
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

    # ==== Section 5: Z-scores + Raw QB Talent Score (references QB Index's own Z's) ========
    sec5_title_row = std_row + 2
    sec5_header_row = sec5_title_row + 1
    sec5_first_row = sec5_header_row + 1
    sec5_last_row = sec5_first_row + n_qb - 1

    _section_title(
        ws, sec5_title_row, 13,
        "Section 5 — Z-Scores and Raw QB Talent Score. Success Rate/Explosive Pass Rate "
        "are \"higher is better\" (no sign-flip). Sack Rate Z (H) is a REFERENCE column "
        "only -- consumed by Part C's OL-modifier scaling, NOT part of the Talent weighted "
        "sum. EPA/CPOE/ANY-A Z's (I/J/K) are LIVE-REFERENCED from QB Index's own Section 5 "
        "(cols E/F/G there, matched by the same Team|Role key QB Index's Section 6 already "
        "uses) -- QB Index's own weights (C34-36) apply to them unchanged; only Success "
        "Rate/Explosive Pass Rate get the 2 new weights (C128/C129) on top.",
    )
    _header_row(
        ws, sec5_header_row,
        ["Player Name", "Player ID", "Team", "Role", "Success Rate\nZ", "Explosive Pass\nRate Z",
         "Sack Rate Z\n(ref only)", "EPA/Play Z\n(ref, QB Index)", "CPOE Z\n(ref, QB Index)",
         "ANY/A Z\n(ref, QB Index)", "Weighted\nTalent Z-Sum", "Raw QB Talent\nScore (Points)",
         "Team|Role\n(helper)"],
    )

    avg_cell_ref = {
        m["key"]: f"${get_column_letter(2 + j)}${avg_row}" for j, m in enumerate(METRICS)
    }
    std_cell_ref = {
        m["key"]: f"${get_column_letter(2 + j)}${std_row}" for j, m in enumerate(METRICS)
    }

    for i in range(n_qb):
        sec3_row = sec3_first_row + i
        row = sec5_first_row + i
        for col, src_col in ((1, "A"), (2, "B"), (3, "C"), (4, "D")):
            f = ws.cell(row=row, column=col, value=f"={src_col}{sec3_row}")
            f.font = FORMULA_FONT

        # Success Rate Z (E), Explosive Pass Rate Z (F), Sack Rate Z (G, reference only)
        for j, m in enumerate(METRICS):
            pcol = proj_baseline_col[m["key"]]
            formula = f"=({pcol}{sec3_row}-{avg_cell_ref[m['key']]})/{std_cell_ref[m['key']]}"
            cell = ws.cell(row=row, column=5 + j, value=formula)
            cell.font = FORMULA_FONT
            cell.number_format = "0.00"

        # QB Index's own real Team|Role key (col K there, written by
        # build_replacement_value.py) -- used to pull EPA/CPOE/ANY-A Z's live.
        qbi_key = f"'{QB_INDEX_SHEET}'!${QB_SEC5_KEY_COL}5:${QB_SEC5_KEY_COL}500"
        for col, qbi_col in ((8, QB_SEC5_EPA_Z_COL), (9, QB_SEC5_CPOE_Z_COL),
                              (10, QB_SEC5_ANYA_Z_COL)):
            ref_range = f"'{QB_INDEX_SHEET}'!${qbi_col}5:${qbi_col}500"
            f = ws.cell(row=row, column=col, value=(
                f'=IFERROR(INDEX({ref_range},MATCH(C{row}&"|"&D{row},{qbi_key},0)),"")'
            ))
            f.font = LINK_FONT
            f.number_format = "0.00"

        wz = ws.cell(row=row, column=11, value=(
            f"=IF(OR(H{row}=\"\",I{row}=\"\",J{row}=\"\"),\"\","
            f"E{row}*'Model Assumptions'!$C$128 + F{row}*'Model Assumptions'!$C$129 + "
            f"H{row}*'Model Assumptions'!$C$34 + I{row}*'Model Assumptions'!$C$35 + "
            f"J{row}*'Model Assumptions'!$C$36)"
        ))
        wz.font = FORMULA_FONT
        wz.number_format = "0.00"

        score = ws.cell(row=row, column=12, value=(
            f'=IF(K{row}="","",\'Model Assumptions\'!$C$37+K{row}*\'Model Assumptions\'!$C$38)'
        ))
        score.font = FORMULA_FONT
        score.number_format = "0.0;(0.0)"

        key = ws.cell(row=row, column=13, value=f'=C{row}&"|"&D{row}')
        key.font = FORMULA_FONT

    sec5_score_range = f"$L${sec5_first_row}:$L${sec5_last_row}"
    sec5_sack_z_range = f"$G${sec5_first_row}:$G${sec5_last_row}"
    sec5_key_range = f"$M${sec5_first_row}:$M${sec5_last_row}"

    # ==== Section 6: QB Situation Flags (Part B) + Environment-Adjusted Baseline ===========
    sec6_title_row = sec5_last_row + 2
    sec6_header_row = sec6_title_row + 1
    sec6_first_row = sec6_header_row + 1
    sec6_last_row = sec6_first_row + n_qb - 1

    _section_title(
        ws, sec6_title_row, 11,
        "Section 6 — QB Situation Flags (real, small, transparent, tunable point "
        "penalties -- same treatment as Offensive Line Index's rookie-starter-risk "
        "penalties, NOT a black-box model) + QB Environment-Adjusted Baseline (Raw Talent "
        "Score + Situational Adjustment). This is the OPPONENT-INDEPENDENT number Part C's "
        "wiring (build_effective_qb_rating_wiring.py) adds game-specific OL/Weather "
        "modifiers to.",
    )
    _header_row(ws, sec6_header_row, [
        "Player Name", "Player ID", "Team", "Role", "New Team\nThis Season",
        "Recently Returned\nfrom Injury", "Years of Real\nHistory (ref, QB Index)",
        "Situational\nAdjustment (pts)", "Raw QB Talent\nScore (ref)",
        "QB Environment-\nAdjusted Baseline", "Team|Role\n(helper)",
    ], height=30)

    for i, qb in enumerate(population.to_dict("records")):
        row = sec6_first_row + i
        sec5_row = sec5_first_row + i
        ws.cell(row=row, column=1, value=qb["Player Name"]).font = INPUT_FONT
        ws.cell(row=row, column=2, value=qb["Player ID"]).font = INPUT_FONT
        ws.cell(row=row, column=3, value=qb["Team"]).font = INPUT_FONT
        ws.cell(row=row, column=4, value=qb["Role"]).font = INPUT_FONT

        new_team_cell = ws.cell(row=row, column=5, value=bool(qb["New Team This Season"]))
        injury_cell = ws.cell(
            row=row, column=6, value=bool(qb["Recently Returned from Injury"])
        )
        new_team_cell.font = INPUT_FONT
        injury_cell.font = INPUT_FONT

        # QB Index's own real Years of Real History -- REFERENCED, not recomputed. Doubles
        # as the real "is this QB a rookie THIS season" signal (0 years of real history),
        # so a separate Is-Rookie reference column isn't needed on top of it.
        years_hist_ref = ws.cell(row=row, column=7, value=(
            f'=IFERROR(INDEX(\'{QB_INDEX_SHEET}\'!${QB_SEC5_YEARS_HIST_COL}5:'
            f'${QB_SEC5_YEARS_HIST_COL}500,MATCH(C{row}&"|"&D{row},'
            f'\'{QB_INDEX_SHEET}\'!${QB_SEC5_KEY_COL}5:${QB_SEC5_KEY_COL}500,0)),"")'
        ))
        years_hist_ref.font = LINK_FONT
        years_hist_ref.number_format = "0"

        adj = ws.cell(row=row, column=8, value=(
            f"=IF(E{row}=TRUE,-'Model Assumptions'!$C$130,0)"
            f"+IF(F{row}=TRUE,-'Model Assumptions'!$C$131,0)"
        ))
        adj.font = FORMULA_FONT
        adj.number_format = "0.0;(0.0)"

        talent_ref = ws.cell(row=row, column=9, value=f"=L{sec5_row}")
        talent_ref.font = FORMULA_FONT
        talent_ref.number_format = "0.0;(0.0)"

        baseline = ws.cell(row=row, column=10, value=(
            f'=IF(I{row}="","",I{row}+H{row})'
        ))
        baseline.font = FORMULA_FONT
        baseline.number_format = "0.0;(0.0)"

        key = ws.cell(row=row, column=11, value=f'=C{row}&"|"&D{row}')
        key.font = FORMULA_FONT

    sec6_baseline_range = f"$J${sec6_first_row}:$J${sec6_last_row}"
    sec6_key_range = f"$K${sec6_first_row}:$K${sec6_last_row}"

    # ---- Closing note --------------------------------------------------------------------
    note_row = sec6_last_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=13)
    note = ws.cell(row=note_row, column=1, value=(
        "claude_code_spec_qb_environment_model.md Parts A/B. QB Index's own Section 5 "
        "Score is COMPLETELY UNCHANGED by this tab -- verify by comparing QB Index's own "
        "Score column before/after this build, or by hand-tracing that this tab only ever "
        "READS QB Index's Section 5/Section 6 columns, never writes to them. TD/INT Ratio "
        "(Section 1, col L) is CONTEXT ONLY, same treatment as PROE on Advanced Efficiency "
        "Metrics -- never part of any weighted composite, since ANY/A's own formula "
        "(+20*TD-45*INT) already includes this signal (adding it again would double-count "
        "it). Sack Rate (Section 1 col G, Section 5 col G) is likewise NEVER part of the "
        "Talent weighted sum (K) -- only Success Rate/Explosive Pass Rate (weights C128/"
        "C129) are new Talent inputs, ADDED ON TOP of QB Index's own EPA/CPOE/ANY-A weights "
        "(C34-36, referenced live, unchanged) rather than a full 5-metric rebalancing. "
        "Section 6's Situational Adjustment (I) is a small, transparent, tunable PENALTY "
        "sum (C130/C131), same treatment as OL Index's rookie-starter-risk penalties -- NOT "
        "a black-box model. 'New offensive coordinator' was explicitly NOT attempted "
        "anywhere in this project -- no coaching-staff-history data source exists. This "
        "tab's own QB Environment-Adjusted Baseline (K) is OPPONENT-INDEPENDENT -- it does "
        "NOT yet include the OL vs. Pass Rush Matchup or Weather-on-Passing modifiers, both "
        "of which depend on a specific game's opponent and are computed separately, per "
        "game, by build_effective_qb_rating_wiring.py on Week 1 Matchups (which combines "
        "this baseline with those game-specific modifiers into the final Effective QB "
        "Rating -- used ONLY in the Pass Matchup Differential calculation there, per the "
        "spec's own explicit instruction; everywhere else that references QB Index's raw "
        "Score keeps doing so, unchanged). NOT YET VALIDATED against real outcomes -- same "
        "disclaimer as every tab in the Defensive Matchup Engine family."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Built '{SHEET_NAME}': Section 1 {len(stats)} rows, Section 3/5/6 {n_qb} QBs. QB "
        f"Index's own Score is untouched -- feeds Effective QB Rating separately."
    )
    print(f"Saved to {workbook_path}")
    return {
        "sec1_rows": len(stats), "n_qb": n_qb,
        "sec3_range": (sec3_first_row, sec3_last_row),
        "sec5_range": (sec5_first_row, sec5_last_row),
        "sec6_range": (sec6_first_row, sec6_last_row),
        "sec5_score_range": sec5_score_range,
        "sec5_sack_z_range": sec5_sack_z_range,
        "sec5_key_range": sec5_key_range,
        "sec6_baseline_range": sec6_baseline_range,
        "sec6_key_range": sec6_key_range,
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            'Usage: uv run python scripts/build_qb_environment_model.py '
            '"path/to/workbook.xlsx"'
        )
        sys.exit(1)
    build(sys.argv[1])
