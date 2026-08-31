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
- UPDATED (claude_code_spec_consolidated_fixes.md Part 3): Section 6 wires this tab into
  Team Ratings -- but still NOT a Replacement Value swap. QB/RB's Replacement Value is a
  clean "Starter score minus Backup score" swap; there's no equally clean equivalent for a
  4-role group (WR1 minus WR3 isn't "who plays if the starter is hurt," it's just "gap
  between the best and third-best receiver," a different and less actionable number).
  Instead, Section 6 blends the team's top 3 of its 4 scored roles (WR1/WR2/WR3/TE1) via
  LARGE() -- a real quality measure, not a swap -- same unconditional-adjustment pattern
  Kicking/OL/Special Teams already established for a position group with no clean "backup
  unit" concept.
- Section 1 has NO historical Role/label column, and Section 2's league average is NOT
  filtered to "Starters + Backups only" the way QB/RB's is. QB/RB's Role filter existed to
  keep a rare "3rd-string emergency starter" season out of the league-average baseline;
  MIN_QUALIFYING_TARGETS (receiving_stats.py) already excludes below-threshold seasons from
  Section 1 entirely, and with 4 scored roles instead of 2 per team, a similar "who's a real
  starter historically" filter would need its own historical-role concept this phase
  deliberately doesn't build (a documented scope simplification, not an oversight).
- UPDATED (claude_code_spec_route_redzone_usage.md): added Pass-Play Snap Participation %
  and Red-Zone Target Share as METRICS' 6th/7th entries -- real USAGE signals
  (receiving_stats.compute_player_season_pass_play_participation /
  compute_player_season_red_zone_target_share), flowing through the full Section 1/3/4/5
  pipeline like every other metric, but with their Section 5 composite weights defaulting to
  0 (Model Assumptions C125/C126) so the existing WR/TE Index Score is completely unchanged
  until someone deliberately activates them. Pass-Play Snap Participation % is an honest
  PROXY for the spec's own "Route Participation" ask -- verified live before building this
  that true route-run data isn't free anywhere, reported to and confirmed by the user (see
  receiving_stats.py's own docstring). Unlike RB Index's own version of this addition, no
  external script hardcodes this tab's Section 5 columns, and this tab's Section 6 already
  computed its score/key columns dynamically from len(METRICS) -- no column-shift bug to fix.
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
Section 6: WR/TE Corps Quality (pts) -- top-3-of-4-role blended score, direct Team Ratings
           adjustment (unconditional, no Replacement Value swap -- see Part 3 note above)

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
sys.path.insert(0, str(Path(__file__).resolve().parent))

from add_manual_override_table import read_existing_overrides  # noqa: E402
from current_season_blend import add_current_season_blend  # noqa: E402

from nflverse_pull.current_roster import (  # noqa: E402
    attach_real_rookie_season,
    compute_current_starters,
    fetch_depth_charts,
    fetch_seasonal_rosters,
    resolve_scored_population,
)
from nflverse_pull.efficiency import fetch_pbp  # noqa: E402
from nflverse_pull.receiving_stats import (  # noqa: E402
    compute_player_season_ngs_receiving,
    compute_player_season_pass_play_participation,
    compute_player_season_red_zone_target_share,
    compute_team_season_receiving_stats,
    fetch_ngs_receiving,
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
TEAM_RATINGS_SHEET = "Team Ratings"

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

METRICS = [
    {"key": "epa", "col": "Receiving EPA/Target", "label": "Receiving\nEPA/Target",
     "fmt": "0.000"},
    {"key": "success", "col": "Reception Success Rate", "label": "Reception\nSuccess Rate",
     "fmt": "0.00"},
    {"key": "ypt", "col": "YPT", "label": "YPT", "fmt": "0.00"},
    {"key": "sep", "col": "Avg Separation", "label": "Avg Separation\n(NGS)", "fmt": "0.00",
     "partial_coverage": True},
    {"key": "yacoe", "col": "YAC Over Expectation", "label": "YAC Over\nExpectation (NGS)",
     "fmt": "0.00", "partial_coverage": True},
    # claude_code_spec_route_redzone_usage.md. Two real USAGE signals (how often this player
    # is actually involved), not efficiency like the five above -- BOTH default to weight 0
    # (Model Assumptions C125/C126) per the spec's own explicit instruction: usage share and
    # efficiency are different kinds of signal that shouldn't be silently mixed into the
    # existing score. Both still flow through the full Section 1->3->4->5 pipeline exactly
    # like every other metric -- only the WEIGHT is zero, so activating either later is a
    # single-cell change, not a rebuild. "Pass-Play Snap Participation %" is a real,
    # honestly-labeled PROXY for what the spec called "Route Participation" -- see
    # receiving_stats.py's own docstring for why true route-run data isn't free anywhere.
    {"key": "pass_play_participation", "col": "Pass-Play Snap Participation %",
     "label": "Pass-Play Snap\nParticipation %", "fmt": "0.00"},
    {"key": "rz_target_share", "col": "Red-Zone Target Share", "label": "Red-Zone\nTarget Share",
     "fmt": "0.00"},
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
        (83, "WR/TE Corps Quality Points-to-Game-Points Conversion", 0.05,
         "claude_code_spec_consolidated_fixes.md Part 3 -- appended here rather than "
         "inserted next to C49-C51 to avoid shifting every later tab's hardcoded row "
         "references (same convention as RB's C82, OL's C81). A starting guess, like "
         "every other coefficient in this model. Smaller than QB's/RB's own conversion "
         "constants since this measures corps DEPTH QUALITY, a real but less direct "
         "signal than a true starter/backup swap -- see 'WR-TE Value Index' Section 6's "
         "own closing note for why this is a top-3-of-4 blend, not a Replacement Value "
         "swap."),
        (84, "Avg Separation Weight (WR/TE Index, pts per SD, real NFL Next Gen Stats)", 0.25,
         "Real route-running/get-open skill (yards of separation at the catch) that "
         "this tab's outcome-based metrics (EPA/Target, Success Rate, YPT) don't "
         "isolate on their own -- appended here rather than inserted next to C49-C51 "
         "to avoid shifting every later tab's hardcoded row references (same "
         "convention as RB's C82, OL's C81, this tab's own C83)."),
        (85, "YAC Over Expectation Weight (WR/TE Index, pts per SD, real NFL Next Gen "
             "Stats)", 0.25,
         "Real after-catch playmaking isolated from the type of catch (actual YAC "
         "minus a model's expected YAC) -- the RB Index RYOE/Att equivalent for "
         "receivers. Weighted equal with Avg Separation: both are real, partial-"
         "coverage NGS skill-isolation signals distinct from the outcome-based "
         "metrics above."),
        (125, "Pass-Play Snap Participation % Weight (WR/TE Index, pts per SD)", 0.0,
         "claude_code_spec_route_redzone_usage.md -- DEFAULTS TO 0 (informational "
         "only). A real usage signal (see receiving_stats.py's own docstring for why "
         "this is a Pass-Play Snap Participation % proxy, not confirmed route-run "
         "data), not efficiency -- the spec's own explicit instruction is to keep "
         "usage share out of the existing weighted composite by default. Set above 0 "
         "to activate deliberately."),
        (126, "Red-Zone Target Share Weight (WR/TE Index, pts per SD)", 0.0,
         "claude_code_spec_route_redzone_usage.md -- DEFAULTS TO 0 (informational "
         "only), same reasoning as C125."),
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
    print(f"Pulling {HISTORICAL_YEARS} play-by-play data for receiving stats...")
    pbp = fetch_pbp(HISTORICAL_YEARS)
    season_stats = compute_team_season_receiving_stats(pbp)

    # claude_code_spec_consolidated_fixes.md Part 1: receiving_stats' own Is Rookie Season
    # is a "first season observed in the pulled window" proxy -- overwrite it with real
    # per-season entry_year data (confirmed live this was contaminating the Rookie Baseline
    # with real veterans: Ertz, Beckham, Diggs, Andrews all had a pulled-window season
    # wrongly flagged True).
    print(f"Pulling {HISTORICAL_YEARS} seasonal rosters for real Is Rookie Season data...")
    seasonal_rosters = fetch_seasonal_rosters(HISTORICAL_YEARS)
    season_stats = attach_real_rookie_season(season_stats, seasonal_rosters)

    print(f"Pulling {HISTORICAL_YEARS} Next Gen Stats receiving data for real Avg "
          "Separation / YAC Over Expectation...")
    ngs_receiving = fetch_ngs_receiving(HISTORICAL_YEARS)
    ngs = compute_player_season_ngs_receiving(ngs_receiving)
    # Left join -- a real, qualifying-here player without a real NGS row (below NGS's own,
    # higher volume threshold) genuinely has no NGS value; left blank, not zero-filled.
    season_stats = season_stats.merge(ngs, on=["Player ID", "Season", "Team"], how="left")
    n_missing_ngs = season_stats["Avg Separation"].isna().sum()
    print(f"{len(season_stats) - n_missing_ngs} of {len(season_stats)} WR/TE-seasons have "
          f"real NGS Avg Separation / YAC Over Expectation values ({n_missing_ngs} below "
          "NGS's own qualifying threshold).")

    print("Computing Pass-Play Snap Participation % / Red-Zone Target Share "
          "(claude_code_spec_route_redzone_usage.md)...")
    participation = compute_player_season_pass_play_participation(pbp)
    season_stats = season_stats.merge(
        participation, on=["Player ID", "Season", "Team"], how="left"
    )
    rz_share = compute_player_season_red_zone_target_share(pbp)
    season_stats = season_stats.merge(rz_share, on=["Player ID", "Season", "Team"], how="left")
    # Both are real 0.0s when the merge finds no row (a qualifying receiver-season truly had
    # zero real red-zone targets, or -- practically impossible above MIN_QUALIFYING_TARGETS
    # -- zero on-field pass plays), not a missing-data blank like the partial-coverage NGS
    # metrics above.
    season_stats["Pass-Play Snap Participation %"] = (
        season_stats["Pass-Play Snap Participation %"].fillna(0.0)
    )
    season_stats["Red-Zone Target Share"] = season_stats["Red-Zone Target Share"].fillna(0.0)

    print(f"Pulling {CURRENT_ROSTER_YEAR} depth charts for current-roster WR/TE population...")
    depth_charts = fetch_depth_charts([CURRENT_ROSTER_YEAR])
    current_starters = compute_current_starters(depth_charts)

    populations = []
    for pos in ("WR", "TE"):
        pop = resolve_scored_population(current_starters, overrides, pos)
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
        market_source = "FFC ADP"
        print(f"  {position}: using FFC Dynasty Rookie ADP, {len(ranking)} ranked.")
    else:
        fc = fetch_fantasycalc_values()
        is_pos = fc["player.position"] == position
        is_this_class = fc["player.maybeDraftInfo.year"] == CURRENT_ROSTER_YEAR
        pos_rookies = fc[is_pos & is_this_class]
        ranking = rank_rookie_class(
            pos_rookies, rank_col="value", ascending=False, name_col="player.name"
        )
        market_source = "FantasyCalc"
        print(f"  {position}: FFC empty, using fantasycalc.com dynasty trade values, "
              f"{len(ranking)} ranked.")

    assumptions = assign_rookie_assumptions(
        ranking, tier_averages, metric_cols, flat_baseline, all_rookie_names=names,
        market_source=market_source,
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
    wb = openpyxl.load_workbook(workbook_path)
    overrides = read_existing_overrides(wb, SHEET_NAME, ["WR1", "WR2", "WR3", "TE1"])
    print(f"Read back {len(overrides)} existing manual-override row(s) from Section 7 "
          "before rebuilding the sheet.")

    data = _pull_data(overrides)
    season_stats = data["season_stats"]
    population = data["population"]
    n_players = len(population)

    rookie = _build_rookie_assumptions(season_stats, population)
    rookie_table = rookie["table"]

    add_model_assumptions_weights(wb)

    if SHEET_NAME in wb.sheetnames:
        del wb[SHEET_NAME]
    insert_after = RB_INDEX_SHEET if RB_INDEX_SHEET in wb.sheetnames else QB_INDEX_SHEET
    ws = wb.create_sheet(SHEET_NAME, index=wb.sheetnames.index(insert_after) + 1)
    ws.column_dimensions["A"].width = 18.0
    ws.column_dimensions["C"].width = 20.0

    ws.merge_cells("A1:M1")
    t = ws.cell(row=1, column=1, value=(
        "WR/TE Value Index -- Multi-Year Decay-Weighted Receiving Rating (Receiving "
        "EPA/Target, Reception Success Rate, YPT, real NGS Avg Separation / YAC Over "
        "Expectation). Scores WR1/WR2/WR3 and TE1 per team -- NOT a Starter/Backup binary "
        "like QB/RB Index."
    ))
    t.font = Font(name="Arial", size=12, bold=True)

    # ==== Section 1: Raw 3-year data per receiver-season ===================================
    sec1_first_row = 5
    sec1_last_row = sec1_first_row + len(season_stats) - 1
    _section_title(
        ws, 3, 13,
        "Section 1 \u2014 Raw 3-Year Data per Receiver-Season (from nflverse pbp; no "
        "Position or historical Role column -- see this tab's closing note). Avg "
        "Separation / YAC Over Expectation (J/K) are real NFL Next Gen Stats data with "
        "their OWN, higher qualifying threshold than this tab's -- a blank cell means a "
        "real, qualifying receiver-season with no real NGS value, not a zero. Pass-Play "
        "Snap Participation % / Red-Zone Target Share (L/M, "
        "claude_code_spec_route_redzone_usage.md) are real USAGE signals -- see this "
        "tab's closing note for why their composite weight defaults to 0.",
    )
    _header_row(
        ws, 4,
        ["Player Name", "Player ID", "Team", "Season", "Targets", "Receiving EPA/Target",
         "Reception Success Rate", "YPT", "Is Rookie Season", "Avg Separation\n(NGS)",
         "YAC Over\nExpectation (NGS)", "Pass-Play Snap\nParticipation %",
         "Red-Zone\nTarget Share"],
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

        sep_v = float(r["Avg Separation"]) if pd.notna(r.get("Avg Separation")) else None
        yac_raw = r.get("YAC Over Expectation")
        yac_v = float(yac_raw) if pd.notna(yac_raw) else None
        sep_cell = ws.cell(row=row, column=10, value=sep_v)
        yac_cell = ws.cell(row=row, column=11, value=yac_v)
        sep_cell.font = INPUT_FONT
        yac_cell.font = INPUT_FONT
        sep_cell.number_format = "0.00"
        yac_cell.number_format = "0.00"

        pp_cell = ws.cell(
            row=row, column=12, value=float(r["Pass-Play Snap Participation %"])
        )
        rz_cell = ws.cell(row=row, column=13, value=float(r["Red-Zone Target Share"]))
        pp_cell.font = INPUT_FONT
        rz_cell.font = INPUT_FONT
        pp_cell.number_format = "0.00"
        rz_cell.number_format = "0.00"

    id_range = f"$B${sec1_first_row}:$B${sec1_last_row}"
    season_range = f"$D${sec1_first_row}:$D${sec1_last_row}"
    rookie_range = f"$I${sec1_first_row}:$I${sec1_last_row}"
    sec1_col_of = {
        "epa": "F", "success": "G", "ypt": "H", "sep": "J", "yacoe": "K",
        "pass_play_participation": "L", "rz_target_share": "M",
    }
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
                # pd.notna(), not `v is not None` -- a partial-coverage metric's tier
                # average can be a real NaN (e.g. a tier with zero real NGS-covered rookie
                # comps in the pulled window); `v is not None` doesn't catch that (Python's
                # `float('nan') is not None` is True) and would write an invalid literal.
                cell = ws.cell(row=row, column=6 + j, value=float(v) if pd.notna(v) else None)
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

            extra_existence_criteria = f",{mrange},\"<>\"" if m.get("partial_coverage") else ""

            def _ysub(offset: int, mrange=mrange, flat_cell=flat_cell,
                       twob_metric_range=twob_metric_range,
                       extra_existence_criteria=extra_existence_criteria,
                       partial_coverage=bool(m.get("partial_coverage"))) -> str:
                index_match = f"INDEX({twob_metric_range},MATCH($B{row},{sec2b_id_range},0))"
                if partial_coverage:
                    rookie_sub = f"IF(ISBLANK({index_match}),{flat_cell},{index_match})"
                    rookie_sub = f"IFERROR({rookie_sub},{flat_cell})"
                else:
                    rookie_sub = f"IFERROR({index_match},{flat_cell})"
                return (
                    f"=IF(COUNTIFS({id_range},$B{row},{season_range},"
                    f"'Model Assumptions'!$C$18-{offset}{extra_existence_criteria})=0,"
                    f"{rookie_sub},"
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

    # claude_code_spec_current_season_blending.md: blend Section 3's Projected Baseline
    # with a real Current-Season value, using the EXACT SAME Blend Weight mechanism Team
    # Ratings' own PPG blend already uses (Model Assumptions C12/C13/C14). Games Played is
    # cross-referenced from Team Ratings' own col H, not re-entered here.
    proj_baseline_col = {
        m["key"]: get_column_letter(metric_block_start_col[m["key"]] + 6) for m in METRICS
    }
    blended_cols = add_current_season_blend(
        ws, team_col="C", sec3_first_row=sec3_first_row, sec3_last_row=sec3_last_row,
        start_col=sec3_last_col + 1,
        metrics=[
            {"key": m["key"], "label": m["label"], "pb_col": proj_baseline_col[m["key"]]}
            for m in METRICS
        ],
    )

    _section_title(
        ws, sec4_title_row, 4,
        "Section 4 \u2014 League Average & Std. Dev. of the 3-Yr, Current-Season-Blended "
        "Baselines (see the new columns appended to the right of Section 3)",
    )
    _header_row(ws, sec4_header_row, ["Stat", *[m["label"] for m in METRICS]], height=18)

    ws.cell(row=avg_row, column=1, value="League Average").font = FORMULA_FONT
    ws.cell(row=std_row, column=1, value="League Std. Dev.").font = FORMULA_FONT

    for j, m in enumerate(METRICS):
        pcol = blended_cols[m["key"]]
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

    sec5_last_col = 5 + len(METRICS) + 4  # player info + Z's + weighted sum + score + YH + key
    _section_title(
        ws, sec5_title_row, sec5_last_col,
        "Section 5 \u2014 Z-Scores and WR/TE Index Score (all five metrics are \"higher is "
        "better\" -- no sign-flip needed. Baseline/points-per-SD reuse QB Index's own Model "
        "Assumptions cells C37/C38, same design choice as RB Index.)",
    )
    _header_row(
        ws, sec5_header_row,
        ["Player Name", "Player ID", "Team", "Position", "Role",
         *[f"{m['label']}\nZ" for m in METRICS], "Weighted\nZ-Score Sum",
         "WR/TE Index\nScore (Points)", "Years of\nReal History", "Team|Role\n(helper)"],
    )

    avg_cell_ref = {
        m["key"]: f"${get_column_letter(2 + j)}${avg_row}" for j, m in enumerate(METRICS)
    }
    std_cell_ref = {
        m["key"]: f"${get_column_letter(2 + j)}${std_row}" for j, m in enumerate(METRICS)
    }
    weight_cells = {
        "epa": "$C$49", "success": "$C$50", "ypt": "$C$51",
        "sep": "$C$84", "yacoe": "$C$85",
        "pass_play_participation": "$C$125", "rz_target_share": "$C$126",
    }

    for i in range(n_players):
        sec3_row = sec3_first_row + i
        row = sec5_first_row + i
        for col, src_col in ((1, "A"), (2, "B"), (3, "C"), (4, "D"), (5, "E")):
            f = ws.cell(row=row, column=col, value=f"={src_col}{sec3_row}")
            f.font = FORMULA_FONT

        z_cols = []
        for j, m in enumerate(METRICS):
            pcol = blended_cols[m["key"]]
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

        # Team|Role helper key (claude_code_spec_consolidated_fixes.md Part 3) -- Section 6
        # needs to look up "this team's WR2 score" directly, but WR and TE rows are NOT
        # interleaved by team (population is all-WR-by-team, then all-TE-by-team -- see
        # _pull_data()), so a single-criteria MATCH against Team alone can't find a
        # specific role. A concatenated key avoids a two-criteria array formula (CSE/
        # SUMPRODUCT), consistent with this project's no-array-formula convention.
        key = ws.cell(row=row, column=wz_col + 3, value=f"=C{row}&\"|\"&E{row}")
        key.font = FORMULA_FONT

    # ==== Section 6: WR/TE Corps Quality (pts) -- claude_code_spec_consolidated_fixes.md ===
    # Part 3. NOT a Replacement Value swap (no clean "backup corps" concept for a 4-role
    # group) -- a direct quality measure instead, same pattern as Kicking/OL/Special Teams'
    # own unconditional Team Ratings adjustments. Per the spec's own guidance: blends the
    # team's TOP 3 of its 4 scored roles (WR1/WR2/WR3/TE1) via LARGE(), so a TE1 who
    # outscores that team's WR3 correctly displaces WR3 in the blend rather than being
    # ignored -- a fixed "always WR1+WR2+WR3" average could never do that. Simple average
    # of the top 3, not target-share-weighted -- a real, free target-share proxy isn't
    # available without a separate pull this phase doesn't build (documented simplification,
    # same as every other "future extension" noted elsewhere in this project).
    # Column letters computed from len(METRICS), not hardcoded -- Section 5's layout shifts
    # whenever METRICS grows (verified needed when Avg Separation/YAC Over Expectation were
    # added: with 3 metrics wz_col=I/score=J/key=L, with 5 metrics wz_col=K/score=L/key=N).
    sec5_wz_col = 6 + len(METRICS)
    sec5_score_col = get_column_letter(sec5_wz_col + 1)
    sec5_key_col = get_column_letter(sec5_wz_col + 3)
    key_range = f"${sec5_key_col}${sec5_first_row}:${sec5_key_col}${sec5_last_row}"
    score_range = f"${sec5_score_col}${sec5_first_row}:${sec5_score_col}${sec5_last_row}"

    sec6_title_row = sec5_last_row + 2
    sec6_header_row = sec6_title_row + 1
    sec6_first_row = sec6_header_row + 1
    sec6_last_row = sec6_first_row + len(TEAM_ORDER) - 1

    _section_title(
        ws, sec6_title_row, 9,
        "Section 6 — WR/TE Corps Quality (pts) -- a DIRECT quality measure (average of "
        "the team's top 3 of its 4 scored roles' WR/TE Index Scores, via LARGE(), minus the "
        "league-average baseline of 50, converted to game points), NOT a Replacement Value "
        "swap like QB/RB Index -- there's no clean 'backup corps' concept for a 4-role "
        "group. Unconditional, applied to every team every time (see closing note).",
    )
    _header_row(ws, sec6_header_row, [
        "Team", "WR1 Score", "WR2 Score", "WR3 Score", "TE1 Score",
        "Top-3 Corps\nScore (avg)", "Corps Adjustment\n(Index Points)",
        "Corps Adjustment\n(Game Points)",
    ])

    for i, team in enumerate(TEAM_ORDER):
        row = sec6_first_row + i
        t = ws.cell(row=row, column=1, value=team)
        t.font = INPUT_FONT

        role_cols = {"WR1": 2, "WR2": 3, "WR3": 4, "TE1": 5}
        for role, col in role_cols.items():
            c = ws.cell(row=row, column=col, value=(
                f'=IFERROR(INDEX({score_range},MATCH("{team}|{role}",{key_range},0)),"")'
            ))
            c.font = FORMULA_FONT
            c.number_format = "0.0;(0.0)"

        role_range = f"B{row}:E{row}"
        top3 = ws.cell(row=row, column=6, value=(
            f'=IFERROR((LARGE({role_range},1)+LARGE({role_range},2)+LARGE({role_range},3))/3,"")'
        ))
        top3.font = FORMULA_FONT
        top3.number_format = "0.0;(0.0)"

        adj_index = ws.cell(row=row, column=7, value=(
            f'=IF(F{row}="","",F{row}-\'Model Assumptions\'!$C$37)'
        ))
        adj_game = ws.cell(row=row, column=8, value=(
            f'=IF(G{row}="","",G{row}*\'Model Assumptions\'!$C$83)'
        ))
        adj_index.font = FORMULA_FONT
        adj_game.font = FORMULA_FONT
        adj_index.number_format = "0.0;(0.0)"
        adj_game.number_format = "0.00;(0.00)"

    # ---- Closing note --------------------------------------------------------------------
    note_row = sec6_last_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=sec5_last_col)
    note = ws.cell(row=note_row, column=1, value=(
        "Phase 2 of the multi-phase roadmap (claude_code_spec_rb_index.md) -- no separate "
        "written spec, designed directly. Scores 4 roles per team (WR1/WR2/WR3, TE1), not a "
        "Starter/Backup binary like QB/RB Index -- TE2 is a documented future extension. "
        "UPDATED: Avg Separation / YAC Over Expectation (real NFL Next Gen Stats) are now "
        "SCORED alongside the original 3 outcome-based metrics -- unlike QB Index's own NGS "
        "context additions (Time to Throw / Aggressiveness, deliberately unscored), both of "
        "these have an unambiguous \"higher is better\" direction and isolate a real skill "
        "(route-running, after-catch playmaking) the outcome-based metrics don't on their "
        "own -- same treatment as RB Index's RYOE/Att, including the same partial-coverage "
        "handling (NGS applies its own higher qualifying threshold; a real, qualifying "
        "receiver-season with no real NGS value shows blank and falls back to the Rookie "
        "Baseline in Section 3, not a fabricated 0). "
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
        "current-roster population. SECTION 6 (claude_code_spec_consolidated_fixes.md Part "
        "3) is a DIRECT quality adjustment wired into Team Ratings, NOT a Replacement Value "
        "swap -- QB/RB's Replacement Value is a clean Starter-minus-Backup swap; there's no "
        "equally clean equivalent for a 4-role group, so this instead blends the team's top "
        "3 of 4 role scores (see Section 6's own title text for why LARGE(), not a fixed "
        "WR1+WR2+WR3 average). A team missing a role shows blank in that role's column but "
        "does not break the top-3 blend (LARGE ignores blank/text cells). The 2026 "
        "depth-chart snapshot this tab's population is built from was pulled BEFORE final "
        "53-man roster cuts -- same caveat as every other current-roster-driven tab in this "
        "workbook. Pass-Play Snap Participation % / Red-Zone Target Share (Section 1 cols "
        "L/M, claude_code_spec_route_redzone_usage.md) are real USAGE signals (how often "
        "this player is actually involved), not efficiency -- both flow through the full "
        "Section 1->3->4->5 pipeline like every other metric, but their composite weights "
        "(Model Assumptions C125/C126) DEFAULT TO 0 so they stay informational-only rather "
        "than silently changing what the WR/TE Index Score means. Pass-Play Snap "
        "Participation % is an HONEST PROXY for the spec's own \"Route Participation\" "
        "concept, not confirmed route-run data -- see receiving_stats.py's own docstring "
        "for why true route-run data isn't free anywhere (verified live before building "
        "this, reported to and confirmed by the user)."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    # ==== Wire into Team Ratings (new, unconditional additive column) ======================
    tr = wb[TEAM_RATINGS_SHEET]
    tr.cell(row=2, column=24, value="WR/TE Corps\nQuality Adj (pts)").font = HEADER_FONT
    tr.cell(row=2, column=24).fill = HEADER_FILL
    tr.cell(row=2, column=24).alignment = HEADER_ALIGN

    adj_game_range = f"'{SHEET_NAME}'!$H${sec6_first_row}:$H${sec6_last_row}"
    adj_team_range = f"'{SHEET_NAME}'!$A${sec6_first_row}:$A${sec6_last_row}"

    for row in range(3, 3 + len(TEAM_ORDER)):
        adj = tr.cell(row=row, column=24, value=(
            f"=IFERROR(INDEX({adj_game_range},MATCH(A{row},{adj_team_range},0)),0)"
        ))
        adj.font = LINK_FONT
        adj.number_format = "0.00;(0.00)"

    note_row_tr = 3 + len(TEAM_ORDER) + 8
    tr.merge_cells(start_row=note_row_tr, start_column=1, end_row=note_row_tr, end_column=24)
    tr_note = tr.cell(row=note_row_tr, column=1, value=(
        "WR/TE Corps Quality Adjustment (X) is unconditional, same reasoning as Kicking "
        "(S) / OL (T) / Front-7 (U) / Secondary (V) / Special Teams (W) -- there's no "
        "'backup WR/TE corps' to switch to. It pulls directly from 'WR-TE Value Index' "
        "Section 6 (that team's top-3-of-4-role blended score minus the league-average "
        "baseline, converted to game points) and applies to Net Power Rating (N) for "
        "every team, every time. NOT included in Net Power Rating's formula by THIS "
        "script (build_wr_te_index.py runs before Kicking/OL/Defense/Secondary/Special "
        "Teams in main.py's pipeline, none of which know about column X) -- Special "
        "Teams' build script owns the final, most-complete N formula and was updated to "
        "include X. See main.py's own pipeline-ordering comment."
    ))
    tr_note.font = NOTE_FONT
    tr_note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Built '{SHEET_NAME}': Section 1 {len(season_stats)} rows, Section 2B {n_2b} rows, "
        f"Section 3/5 {n_players} WR/TE roles. Wired into '{TEAM_RATINGS_SHEET}' (col X)."
    )
    print(f"Saved to {workbook_path}")
    return {
        "sec1_rows": len(season_stats), "n_players": n_players, "n_2b": n_2b,
        "sec3_range": (sec3_first_row, sec3_last_row),
        "sec5_range": (sec5_first_row, sec5_last_row),
        "sec6_range": (sec6_first_row, sec6_last_row),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: uv run python scripts/build_wr_te_index.py "path/to/workbook.xlsx"')
        sys.exit(1)
    build(sys.argv[1])
