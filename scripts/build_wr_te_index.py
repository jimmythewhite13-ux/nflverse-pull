"""
Builds "WR/TE Value Index" -- Phase 2 of the multi-phase roadmap sketched in
claude_code_spec_rb_index.md's own header ("1. RB (done). 2. WR/TE -- bigger value pool,
but multiple starters per team, not a clean binary. 3. Kicking. 4. Defense. 5. Offensive
line -- not attempted."). No separate written spec exists for this phase -- designed
directly (per explicit user instruction), mirroring build_rb_index.py's own pattern and
documenting every place this phase's design departs from it.

Where this departs from QB/RB Index, and why:

- WR is NOT a clean Starter/Backup binary -- it's a 3-WR personnel group. This tab scores
  FOUR roles per team: WR1, WR2, WR3 (current_roster.py's new WR support), and TE1 (TE2 is
  a documented future extension, not built here). ~128 scored player-rows across 32 teams,
  not ~64.
- NO Section 6 Replacement Value / Team Ratings wiring in this phase. QB/RB's Replacement
  Value is a clean "Starter score minus Backup score" swap; there's no equally clean
  equivalent for a 3-WR group (WR1 minus WR3 isn't "who plays if the starter is hurt," it's
  just "gap between the best and third-best receiver," a different and less actionable
  number). Building a real Replacement Value concept for a non-binary position group is left
  for a future extension once there's a concrete definition worth building, rather than
  forcing QB/RB's swap logic onto a shape it wasn't designed for.
- Section 1 has NO historical Role/label column, and Section 2's league average is NOT
  filtered to "Starters + Backups only" the way QB/RB's is. QB/RB's Role filter existed to
  keep a rare "3rd-string emergency starter" season out of the league-average baseline;
  MIN_QUALIFYING_TARGETS (receiving_stats.py) already excludes below-threshold seasons from
  Section 1 entirely, and with 4 scored roles instead of 2 per team, a similar "who's a real
  starter historically" filter would need its own historical-role concept this phase
  deliberately doesn't build (a documented scope simplification, not an oversight).
- Section 2B's historical tier-average pool (used for a zero-history rookie's fallback) is
  COMBINED across WR and TE rookies -- receiving_stats.py's stats pull carries no Position
  column (same as qb_stats.py / rb_stats.py, by design: position identity comes from
  current_roster.py, not the stats pull), so a WR-only vs TE-only historical split isn't
  available without a separate historical position pull this phase doesn't build. The
  CURRENT draft class's market ranking, by contrast, IS split by real position (WR rookies
  ranked among WR rookies, TE rookies among TE rookies) since that comes from this year's
  live current-roster population, which does carry a real position per player.

Section 1: raw 3-year data per receiver-season (from receiving_stats.py)
Section 2: league average per season (ALL qualifying rows, no role filter -- see above) + a
           flat Rookie Baseline (fallback when a player isn't in Section 2B)
Section 2B: Individual Rookie Assumptions (ADP/trade-value-informed), same mechanism as
           RB/QB Index's Section 2B -- see build_rb_index.py's own comments
Section 3: per-player 3-Yr decay-weighted, regressed baseline -- population is the CURRENT-
           roster-identified WR1/WR2/WR3/TE1 (current_roster.resolve_scored_population,
           called once per position and concatenated; no historical-proxy fallback exists
           for WR/TE, unlike QB's retrofit, since there was never an old population to fall
           back to here)
Section 4: league average/std-dev of Section 3's projected baselines
Section 5: Z-scores, weighted composite, points-scale score (reuses QB Index's own
           Model Assumptions C37/C38 scale constants, same design choice as RB Index)

Usage:
    uv run python scripts/build_wr_te_index.py "C:\\path\\to\\NFL_Prediction_Model.xlsx"
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
from nflverse_pull.efficiency import fetch_pbp  # noqa: E402
from nflverse_pull.receiving_stats import (  # noqa: E402
    compute_team_season_receiving_stats,
)
from nflverse_pull.rookie_crosswalk import (  # noqa: E402
    assign_rookie_assumptions,
    compute_historical_tier_averages,
    fetch_draft_info,
    fetch_fantasycalc_values,
    fetch_ffc_dynasty_rookie_adp,
    rank_rookie_class,
)

HISTORICAL_YEARS = [2023, 2024, 2025]
CURRENT_ROSTER_YEAR = 2026
SHEET_NAME = "WR-TE Value Index"  # Excel sheet titles can't contain "/"
QB_INDEX_SHEET = "QB Index"
RB_INDEX_SHEET = "RB Value Index"

METRICS = [
    {"key": "epa", "col": "Receiving EPA/Target", "label": "Receiving\nEPA/Target",
     "fmt": "0.000"},
    {"key": "success", "col": "Reception Success Rate", "label": "Reception\nSuccess Rate",
     "fmt": "0.00"},
    {"key": "ypt", "col": "YPT", "label": "YPT", "fmt": "0.00"},
]

TITLE_FONT = Font(name="Arial", size=10, bold=True)
TITLE_FILL = PatternFill("solid", fgColor="FFD9E1F2")
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="FF1F4E78")
HEADER_ALIGN = Alignment(wrap_text=True, horizontal="center", vertical="center")
INPUT_FONT = Font(name="Arial", size=10, color="FF0000FF")
FORMULA_FONT = Font(name="Arial", size=10, color="FF000000")
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
    title_row = 48
    ws.merge_cells(f"A{title_row}:D{title_row}")
    title = ws.cell(row=title_row, column=1, value=(
        "WR/TE Value Index Weighting (pts per std. dev.; reuses QB Index's points-scale "
        "constants C37/C38 -- see 'WR-TE Value Index' tab)"
    ))
    title.font = HEADER_FONT
    title.fill = HEADER_FILL

    rows = [
        (49, "Receiving EPA/Target Weight (WR/TE Index, pts per SD)", 0.5,
         "EPA/target is the most complete single receiving stat -- weighted highest, "
         "same logic as every other efficiency weighting in this model."),
        (50, "Reception Success Rate Weight (WR/TE Index, pts per SD)", 0.4,
         "Correlates with EPA but isolates consistency (positive-EPA rate) rather than "
         "magnitude -- weighted lower to avoid double-counting."),
        (51, "YPT Weight (WR/TE Index, pts per SD)", 0.3,
         "Traditional, well-understood counting stat -- a sanity check alongside the "
         "EPA-based metrics, not the primary signal."),
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
    print(f"Pulling {HISTORICAL_YEARS} play-by-play data for receiving stats...")
    pbp = fetch_pbp(HISTORICAL_YEARS)
    season_stats = compute_team_season_receiving_stats(pbp)

    print(f"Pulling {CURRENT_ROSTER_YEAR} depth charts for current-roster WR/TE population...")
    depth_charts = fetch_depth_charts([CURRENT_ROSTER_YEAR])
    current_starters = compute_current_starters(depth_charts)
    empty_overrides = pd.DataFrame(
        columns=["Team", "Manual Starter Override", "Manual Backup Override"]
    )

    populations = []
    for pos in ("WR", "TE"):
        pop = resolve_scored_population(current_starters, empty_overrides, pos)
        pop = pop.copy()
        pop["Position"] = pos
        populations.append(pop)
    population = pd.concat(populations, ignore_index=True)
    print(f"{len(population)} current-roster WR/TE roles identified "
          f"({(population['Position'] == 'WR').sum()} WR, "
          f"{(population['Position'] == 'TE').sum()} TE).")

    return {"season_stats": season_stats, "population": population}


def _rookie_assumptions_for_position(
    position: str, zero_history: pd.DataFrame, tier_averages: pd.DataFrame,
    flat_baseline: dict, metric_cols: list[str],
) -> pd.DataFrame:
    """
    Builds Section 2B rows for one position's zero-history current-roster players, ranking
    this year's real draft class within THAT position only (a rookie TE shouldn't be ranked
    against rookie WR trade values -- see module docstring) against the SHARED (WR+TE
    combined) historical tier-average pool.
    """
    names = list(zero_history["Player Name"])
    if not names:
        return pd.DataFrame()

    market = fetch_ffc_dynasty_rookie_adp()
    if len(market) and "position" in market:
        pos_market = market[market["position"].str.upper() == position]
    else:
        pos_market = pd.DataFrame()

    if len(pos_market):
        ranking = rank_rookie_class(pos_market, rank_col="adp", ascending=True, name_col="name")
        print(f"  {position}: using FFC Dynasty Rookie ADP, {len(ranking)} ranked.")
    else:
        fc = fetch_fantasycalc_values()
        is_pos = fc["player.position"] == position
        is_this_class = fc["player.maybeDraftInfo.year"] == CURRENT_ROSTER_YEAR
        pos_rookies = fc[is_pos & is_this_class]
        ranking = rank_rookie_class(
            pos_rookies, rank_col="value", ascending=False, name_col="player.name"
        )
        print(f"  {position}: FFC empty, using fantasycalc.com dynasty trade values, "
              f"{len(ranking)} ranked.")

    assumptions = assign_rookie_assumptions(
        ranking, tier_averages, metric_cols, flat_baseline, all_rookie_names=names,
    )
    id_lookup = dict(zip(zero_history["Player Name"], zero_history["Player ID"], strict=True))
    team_lookup = dict(zip(zero_history["Player Name"], zero_history["Team"], strict=True))
    role_lookup = dict(zip(zero_history["Player Name"], zero_history["Role"], strict=True))
    assumptions = assumptions.copy()
    assumptions["Player ID"] = assumptions["Player Name"].map(id_lookup)
    assumptions["Team"] = assumptions["Player Name"].map(team_lookup)
    assumptions["Role"] = assumptions["Player Name"].map(role_lookup)
    assumptions["Position"] = position
    return assumptions


def _build_rookie_assumptions(season_stats: pd.DataFrame, population: pd.DataFrame) -> dict:
    metric_cols = [m["col"] for m in METRICS]
    known_ids = set(season_stats["Player ID"])
    zero_history = population[~population["Player ID"].isin(known_ids)]

    if not len(zero_history):
        print("No current-roster WR/TE role has zero qualifying pbp history -- Section 2B "
              "will be empty.")
        return {"table": pd.DataFrame()}

    zh_wr = zero_history["Player Name"].tolist()
    print(f"{len(zero_history)} current WR/TE role(s) with zero qualifying history: {zh_wr} "
          "-- building ADP/trade-value-informed assumptions.")

    rookie_stats = season_stats[season_stats["Is Rookie Season"]]
    draft_info = fetch_draft_info()
    # COMBINED across WR+TE, per the module docstring's documented simplification.
    tier_averages = compute_historical_tier_averages(
        rookie_stats, draft_info, metric_cols, id_col="Player ID"
    )
    flat_baseline = {col: rookie_stats[col].mean() for col in metric_cols}

    tables = []
    for pos in ("WR", "TE"):
        pos_zero = zero_history[zero_history["Position"] == pos]
        t = _rookie_assumptions_for_position(
            pos, pos_zero, tier_averages, flat_baseline, metric_cols
        )
        if len(t):
            tables.append(t)

    combined = pd.concat(tables, ignore_index=True) if tables else pd.DataFrame()
    return {"table": combined}


def build(workbook_path: str) -> dict:
    data = _pull_data()
    season_stats = data["season_stats"]
    population = data["population"]
    n_players = len(population)

    rookie = _build_rookie_assumptions(season_stats, population)
    rookie_table = rookie["table"]

    wb = openpyxl.load_workbook(workbook_path)
    add_model_assumptions_weights(wb)

    if SHEET_NAME in wb.sheetnames:
        del wb[SHEET_NAME]
    insert_after = RB_INDEX_SHEET if RB_INDEX_SHEET in wb.sheetnames else QB_INDEX_SHEET
    ws = wb.create_sheet(SHEET_NAME, index=wb.sheetnames.index(insert_after) + 1)
    ws.column_dimensions["A"].width = 18.0
    ws.column_dimensions["C"].width = 20.0

    ws.merge_cells("A1:J1")
    t = ws.cell(row=1, column=1, value=(
        "WR/TE Value Index -- Multi-Year Decay-Weighted Receiving Rating (Receiving "
        "EPA/Target, Reception Success Rate, YPT). Scores WR1/WR2/WR3 and TE1 per team -- "
        "NOT a Starter/Backup binary like QB/RB Index, and has NO Replacement Value / Team "
        "Ratings wiring yet (see the closing note below for why)."
    ))
    t.font = Font(name="Arial", size=12, bold=True)

    # ==== Section 1: Raw 3-year data per receiver-season ===================================
    sec1_first_row = 5
    sec1_last_row = sec1_first_row + len(season_stats) - 1
    _section_title(
        ws, 3, 9,
        "Section 1 \u2014 Raw 3-Year Data per Receiver-Season (from nflverse pbp; no "
        "Position or historical Role column -- see this tab's closing note)",
    )
    _header_row(
        ws, 4,
        ["Player Name", "Player ID", "Team", "Season", "Targets", "Receiving EPA/Target",
         "Reception Success Rate", "YPT", "Is Rookie Season"],
    )
    for i, r in enumerate(season_stats.to_dict("records")):
        row = sec1_first_row + i
        values = [
            r["Player Name"], r["Player ID"], r["Team"], int(r["Season"]), int(r["Targets"]),
            float(r["Receiving EPA/Target"]), float(r["Reception Success Rate"]),
            float(r["YPT"]), bool(r["Is Rookie Season"]),
        ]
        for col, v in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.font = INPUT_FONT
            if col == 6:
                cell.number_format = "0.000"
            elif col in (7, 8):
                cell.number_format = "0.00"

    id_range = f"$B${sec1_first_row}:$B${sec1_last_row}"
    season_range = f"$D${sec1_first_row}:$D${sec1_last_row}"
    rookie_range = f"$I${sec1_first_row}:$I${sec1_last_row}"
    sec1_col_of = {"epa": "F", "success": "G", "ypt": "H"}
    metric_ranges = {
        m["key"]: (
            f"${sec1_col_of[m['key']]}${sec1_first_row}:${sec1_col_of[m['key']]}${sec1_last_row}"
        )
        for m in METRICS
    }

    # ==== Section 2: League average per season (ALL qualifying rows) + flat Rookie Baseline
    sec2_title_row = sec1_last_row + 2
    sec2_header_row = sec2_title_row + 1
    season_rows = {yr: sec2_header_row + 1 + i for i, yr in enumerate(HISTORICAL_YEARS)}
    rookie_baseline_row = sec2_header_row + 1 + len(HISTORICAL_YEARS)
    rookie_count_row = rookie_baseline_row + 1

    _section_title(
        ws, sec2_title_row, 4,
        "Section 2 \u2014 League Average per Season (ALL qualifying rows -- no "
        "Starter/Backup-style Role filter, see closing note) and flat Rookie Baseline",
    )
    _header_row(ws, sec2_header_row, ["Season / Stat", *[m["label"] for m in METRICS]], height=20)

    for yr in HISTORICAL_YEARS:
        row = season_rows[yr]
        c = ws.cell(row=row, column=1, value=yr)
        c.font = INPUT_FONT
        for j, m in enumerate(METRICS):
            formula = f"=AVERAGEIF({season_range},{yr},{metric_ranges[m['key']]})"
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

    # ==== Section 2B: Individual Rookie Assumptions =========================================
    sec2b_title_row = rookie_count_row + 2
    sec2b_header_row = sec2b_title_row + 1
    sec2b_first_row = sec2b_header_row + 1
    n_2b = len(rookie_table)
    sec2b_last_row = sec2b_first_row + max(n_2b, 1) - 1

    _section_title(
        ws, sec2b_title_row, 9,
        "Section 2B \u2014 Individual Rookie Assumptions (ADP/trade-value-informed, "
        "current draft class only; WR rookies ranked among WR, TE among TE -- see "
        "rookie_crosswalk.py). Only lists current-roster WR/TE roles with ZERO qualifying "
        "pbp history; Section 3 looks this table up by Player ID FIRST, falling back to "
        "the flat Section 2 Rookie Baseline for everyone else.",
    )
    _header_row(
        ws, sec2b_header_row,
        ["Player Name", "Player ID", "Team", "Position", "Role",
         *[m["label"] for m in METRICS], "Source"],
        height=20,
    )
    if n_2b:
        for i, r in enumerate(rookie_table.to_dict("records")):
            row = sec2b_first_row + i
            values = [r["Player Name"], r["Player ID"], r["Team"], r["Position"], r["Role"]]
            for col, v in enumerate(values, start=1):
                ws.cell(row=row, column=col, value=v).font = INPUT_FONT
            for j, m in enumerate(METRICS):
                v = r.get(m["col"])
                cell = ws.cell(row=row, column=6 + j, value=float(v) if v is not None else None)
                cell.font = INPUT_FONT
                cell.number_format = m["fmt"]
            src = ws.cell(row=row, column=6 + len(METRICS), value=r.get("Source"))
            src.font = INPUT_FONT
    else:
        ws.merge_cells(
            start_row=sec2b_first_row, start_column=1, end_row=sec2b_first_row, end_column=9
        )
        empty_note = ws.cell(
            row=sec2b_first_row, column=1,
            value="(none currently -- no identified current-roster WR/TE role has zero "
                  "qualifying pbp history)",
        )
        empty_note.font = NOTE_FONT

    sec2b_id_range = f"$B${sec2b_first_row}:$B${sec2b_last_row}"
    sec2b_metric_range = {
        m["key"]: (
            f"${get_column_letter(6 + j)}${sec2b_first_row}:"
            f"${get_column_letter(6 + j)}${sec2b_last_row}"
        )
        for j, m in enumerate(METRICS)
    }

    # ==== Section 3: Per-player decay-weighted, regressed baseline =========================
    sec3_title_row = sec2b_last_row + 2
    sec3_header_row = sec3_title_row + 1
    sec3_first_row = sec3_header_row + 1
    sec3_last_row = sec3_first_row + n_players - 1
    sec3_last_col = 6 + len(METRICS) * 7

    _section_title(
        ws, sec3_title_row, sec3_last_col,
        "Section 3 \u2014 Per-Player 3-Yr Decay-Weighted, Regressed Baseline. Population is "
        "the CURRENT-roster-identified WR1/WR2/WR3/TE1 (current_roster.py's live 2026 "
        "depth-chart pull) -- no historical-proxy fallback exists for this tab (there was "
        "never an old population to fall back to). Missing years substitute Section 2B's "
        "individual assumption first, falling back to the flat Section 2 Rookie Baseline.",
    )
    headers = ["Player Name", "Player ID", "Team", "Position", "Role", "Years of\nReal History"]
    metric_block_start_col: dict[str, int] = {}
    col_cursor = 7
    for m in METRICS:
        metric_block_start_col[m["key"]] = col_cursor
        headers += [
            f"{m['label']} Y-1", f"{m['label']} Y-2", f"{m['label']} Y-3",
            f"Weighted\n{m['label']} Avg\n(3-Yr decay)", f"Team History\n{m['label']}",
            f"League Baseline\n{m['label']} (Y-1)", f"Projected 3-Yr\n{m['label']} Baseline",
        ]
        col_cursor += 7
    _header_row(ws, sec3_header_row, headers)

    for i, p in enumerate(population.to_dict("records")):
        row = sec3_first_row + i
        ws.cell(row=row, column=1, value=p["Player Name"]).font = FORMULA_FONT
        ws.cell(row=row, column=2, value=p["Player ID"]).font = FORMULA_FONT
        ws.cell(row=row, column=3, value=p["Team"]).font = FORMULA_FONT
        ws.cell(row=row, column=4, value=p["Position"]).font = FORMULA_FONT
        ws.cell(row=row, column=5, value=p["Role"]).font = FORMULA_FONT

        years_hist_terms = "+".join(
            f"--(COUNTIFS({id_range},$B{row},{season_range},'Model Assumptions'!$C$18-{k})>0)"
            for k in (1, 2, 3)
        )
        yh = ws.cell(row=row, column=6, value=f"={years_hist_terms}")
        yh.font = FORMULA_FONT
        yh.number_format = "0"

        for m in METRICS:
            base = metric_block_start_col[m["key"]]
            y1, y2, y3, wavg, th, lb, pb = (get_column_letter(base + k) for k in range(7))
            mrange = metric_ranges[m["key"]]
            flat_cell = flat_rookie_cell[m["key"]]
            twob_metric_range = sec2b_metric_range[m["key"]]

            def _ysub(offset: int, mrange=mrange, flat_cell=flat_cell,
                       twob_metric_range=twob_metric_range) -> str:
                rookie_sub = (
                    f"IFERROR(INDEX({twob_metric_range},MATCH($B{row},{sec2b_id_range},0)),"
                    f"{flat_cell})"
                )
                return (
                    f"=IF(COUNTIFS({id_range},$B{row},{season_range},"
                    f"'Model Assumptions'!$C$18-{offset})=0,{rookie_sub},"
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

    # ==== Section 5: Z-scores, weighted composite, points-scale score ======================
    sec5_title_row = std_row + 2
    sec5_header_row = sec5_title_row + 1
    sec5_first_row = sec5_header_row + 1
    sec5_last_row = sec5_first_row + n_players - 1

    _section_title(
        ws, sec5_title_row, 11,
        "Section 5 \u2014 Z-Scores and WR/TE Index Score (all three metrics are \"higher is "
        "better\" -- no sign-flip needed. Baseline/points-per-SD reuse QB Index's own Model "
        "Assumptions cells C37/C38, same design choice as RB Index.)",
    )
    _header_row(
        ws, sec5_header_row,
        ["Player Name", "Player ID", "Team", "Position", "Role",
         *[f"{m['label']}\nZ" for m in METRICS], "Weighted\nZ-Score Sum",
         "WR/TE Index\nScore (Points)", "Years of\nReal History"],
    )

    avg_cell_ref = {
        m["key"]: f"${get_column_letter(2 + j)}${avg_row}" for j, m in enumerate(METRICS)
    }
    std_cell_ref = {
        m["key"]: f"${get_column_letter(2 + j)}${std_row}" for j, m in enumerate(METRICS)
    }
    weight_cells = {"epa": "$C$49", "success": "$C$50", "ypt": "$C$51"}

    for i in range(n_players):
        sec3_row = sec3_first_row + i
        row = sec5_first_row + i
        for col, src_col in ((1, "A"), (2, "B"), (3, "C"), (4, "D"), (5, "E")):
            f = ws.cell(row=row, column=col, value=f"={src_col}{sec3_row}")
            f.font = FORMULA_FONT

        z_cols = []
        for j, m in enumerate(METRICS):
            pcol = proj_baseline_col[m["key"]]
            formula = f"=({pcol}{sec3_row}-{avg_cell_ref[m['key']]})/{std_cell_ref[m['key']]}"
            col = 6 + j
            cell = ws.cell(row=row, column=col, value=formula)
            cell.font = FORMULA_FONT
            cell.number_format = "0.00"
            z_cols.append(get_column_letter(col))

        weighted_terms = " + ".join(
            f"{z_cols[j]}{row}*'Model Assumptions'!{weight_cells[m['key']]}"
            for j, m in enumerate(METRICS)
        )
        wz_col = 6 + len(METRICS)
        wz = ws.cell(row=row, column=wz_col, value=f"={weighted_terms}")
        wz.font = FORMULA_FONT
        wz.number_format = "0.00"

        score = ws.cell(row=row, column=wz_col + 1, value=(
            f"='Model Assumptions'!$C$37+{get_column_letter(wz_col)}{row}*'Model Assumptions'!$C$38"
        ))
        score.font = FORMULA_FONT
        score.number_format = "0.0;(0.0)"

        yh_link = ws.cell(row=row, column=wz_col + 2, value=f"=F{sec3_row}")
        yh_link.font = FORMULA_FONT
        yh_link.number_format = "0"

    # ---- Closing note --------------------------------------------------------------------
    note_row = sec5_last_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=11)
    note = ws.cell(row=note_row, column=1, value=(
        "Phase 2 of the multi-phase roadmap (claude_code_spec_rb_index.md) -- no separate "
        "written spec, designed directly. Scores 4 roles per team (WR1/WR2/WR3, TE1), not a "
        "Starter/Backup binary like QB/RB Index -- TE2 is a documented future extension. "
        "Section 1 carries no historical Role label and Section 2's league average is NOT "
        "filtered to 'real starters only' the way QB/RB's is -- MIN_QUALIFYING_TARGETS "
        "(receiving_stats.py) already excludes below-threshold seasons, and building an "
        "equivalent historical-role concept for 4 roles/team was out of scope this phase. "
        "Section 2B's historical tier-average pool (the fallback for a zero-history rookie "
        "not in this year's real market rankings) is COMBINED across WR and TE -- "
        "receiving_stats.py carries no Position column (same design as qb_stats.py / "
        "rb_stats.py: position comes from current_roster.py, not the stats pull), so a "
        "WR-only vs TE-only historical split isn't available without a separate historical "
        "position pull. The CURRENT draft class's market ranking IS split by real position "
        "(WR ranked among WR, TE among TE), since that comes from this year's live "
        "current-roster population. THERE IS NO SECTION 6 REPLACEMENT VALUE AND NO TEAM "
        "RATINGS WIRING for this tab -- QB/RB's Replacement Value is a clean Starter-minus-"
        "Backup swap; there's no equally clean equivalent for a 3-WR group (WR1 minus WR3 "
        "measures depth-chart spread, not 'who plays if the starter is hurt'), so this was "
        "deliberately left for a future extension rather than forcing an ill-fitting metric. "
        "The 2026 depth-chart snapshot this tab's population is built from was pulled "
        "BEFORE final 53-man roster cuts -- same caveat as every other current-roster-driven "
        "tab in this workbook."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Built '{SHEET_NAME}': Section 1 {len(season_stats)} rows, Section 2B {n_2b} rows, "
        f"Section 3/5 {n_players} WR/TE roles."
    )
    print(f"Saved to {workbook_path}")
    return {
        "sec1_rows": len(season_stats), "n_players": n_players, "n_2b": n_2b,
        "sec3_range": (sec3_first_row, sec3_last_row),
        "sec5_range": (sec5_first_row, sec5_last_row),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: uv run python scripts/build_wr_te_index.py "path/to/workbook.xlsx"')
        sys.exit(1)
    build(sys.argv[1])
