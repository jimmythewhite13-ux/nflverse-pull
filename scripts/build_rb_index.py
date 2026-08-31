"""
Builds Parts C and D of claude_code_spec_rb_index.md: a new "RB Value Index" workbook tab,
structurally mirroring "QB Index" (5-section decay-weighted/regressed pattern + Section 6
Replacement Value), plus the new "RB Value Index Weighting & Conversion" assumptions on
"Model Assumptions", plus Team Ratings wiring.

Key differences from QB Index (per claude_code_spec_rb_index.md and the kickoff prompt's
Step 3 instruction to use current-roster + ADP-informed rookie assumptions "natively",
not the historical-attempts-only proxy QB Index still uses as of this writing):

- Section 1 uses RB-specific metrics (Rushing EPA/Play, Rushing Success Rate, YPC, and --
  UPDATED, per explicit user instruction to incorporate NFL Next Gen Stats -- real,
  official RYOE/Att) and still computes a HISTORICAL, attempts-ranking Role per past season
  (rb_stats.compute_historical_rb_roles) -- used only to label Section 1 rows and filter
  Section 2's league averages to Starters+Backups, never to decide who is scored in
  Section 3/5/6. RYOE/Att is NOT full-coverage the way the other 3 metrics are (NGS applies
  its own, higher qualifying-volume threshold -- confirmed live: 51 NGS-tracked RBs vs. 78
  RBs this tab's own 50-carry threshold considers qualifying), so it needs its own
  existence check in Section 3 (see _ysub's partial_coverage branch) rather than the shared
  row-exists check the other 3 metrics use.
- Section 3/5/6 population comes from current_roster.resolve_scored_population's live
  2026 depth-chart pull instead -- a true zero-history rookie identified as a current
  Starter/Backup still gets a full row (see Section 2B below), which the old
  historical-ranking-only approach could never do (a rookie has no historical rank).
- NEW Section 2B -- Individual Rookie Assumptions (ADP/trade-value-informed): for each
  current-season Starter/Backup with zero qualifying pbp history, computes a per-player
  assumption (via nflverse_pull.rookie_crosswalk) from this draft class's market signal
  (Fantasy Football Calculator Dynasty Rookie ADP, primary; api.fantasycalc.com dynasty
  trade value, fallback -- see rookie_crosswalk.py's own module docstring for which one
  actually had live data as of this build). Section 3's missing-year substitution formula
  looks this table up FIRST (by Player ID), falling back to the flat, all-rookies Section 2
  Rookie Baseline only for a player not in this table (i.e. not a current zero-history
  rookie -- a 2nd-year player missing only Y-2/Y-3 still uses the flat league average,
  which is the correct interpretation for "what would a generic missing season look
  like," as opposed to "what should THIS specific incoming rookie be assumed to do").
- NEW Carry Share (Y-1) column on Section 6 -- the committee-vs-bell-cow signal the spec
  calls for, computed by rb_stats.compute_carry_share() (a Python input, like Section 1's
  raw stats, not a live in-sheet formula -- there's no clean single-cell Excel formula for
  "this player's most recent qualifying season's carries" without a large helper range).
- Section 4/5 reuse the QB Index's own points-scale constants (Model Assumptions C37/C38)
  per the spec's explicit instruction, rather than creating RB-specific ones -- a score of
  60 means "1 SD above average at this position" the same way for both tabs.
- Section 6's points-to-game-points conversion constant is a NEW, separate cell (Model
  Assumptions C47) -- explicitly NOT shared with QB's C39, per the spec (RB replacement
  impact is real but smaller in aggregate: one player touches every offensive snap, the
  other a subset of plays).
- Receiving work out of the backfield is explicitly OUT OF SCOPE for this version -- noted
  on the tab itself, not just in this docstring, so nobody mistakes this for a complete
  "RB value" measure.
- Roster-cuts caveat: per the same override the user approved for Step 2 (the rookie ADP/
  trade-value crosswalk), the 2026 depth-chart snapshot this tab is built from was pulled
  BEFORE final 53-man roster cuts -- see the tab's own closing note.

UPDATED (claude_code_spec_route_redzone_usage.md): added Red-Zone Carry Share as METRICS'
5th entry -- a real USAGE signal (rb_stats.compute_player_season_red_zone_carry_share),
flowing through the full Section 1/3/4/5 pipeline like every other metric, but with its
Section 5 composite weight defaulting to 0 (Model Assumptions C124) so the existing RB Index
Score is completely unchanged until someone deliberately activates it. Adding this 5th metric
shifted Section 6's Score/Team|Role-key columns by one letter (J/L -> K/M) -- fixed a second,
proactively-caught instance of the same "hardcoded column" bug class RYOE/Att's own key-column
fix found (score_range was still hardcoded to "$J$"; now computed dynamically like key_col
already was), and updated build_defensive_matchup_wiring.py's own RB_SCORE_COL/RB_KEY_COL
constants to match.

Usage:
    uv run python scripts/build_rb_index.py "C:\\path\\to\\NFL_Prediction_Model.xlsx"
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

from nflverse_pull.current_roster import (  # noqa: E402
    attach_real_rookie_season,
    compute_current_starters,
    fetch_depth_charts,
    fetch_seasonal_rosters,
    resolve_scored_population,
)
from nflverse_pull.efficiency import fetch_pbp  # noqa: E402
from nflverse_pull.rb_stats import (  # noqa: E402
    compute_carry_share,
    compute_historical_rb_roles,
    compute_player_season_red_zone_carry_share,
    compute_player_season_ryoe,
    compute_team_season_rb_stats,
    fetch_ngs_rushing,
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
SHEET_NAME = "RB Value Index"
QB_INDEX_SHEET = "QB Index"
TEAM_RATINGS_SHEET = "Team Ratings"

METRICS = [
    {"key": "epa", "col": "Rushing EPA/Play", "label": "Rushing\nEPA/Play", "fmt": "0.000"},
    {"key": "success", "col": "Rushing Success Rate", "label": "Rushing\nSuccess Rate",
     "fmt": "0.00"},
    {"key": "ypc", "col": "YPC", "label": "YPC", "fmt": "0.00"},
    # Real, official NFL Next Gen Stats data -- NOT full coverage the way the other 3
    # metrics are (NGS applies its own, higher qualifying-volume threshold), so this one
    # metric needs its own "does this player-season actually have a value" existence check
    # in Section 3, not the shared row-exists check the other 3 metrics use. See
    # rb_stats.py's own module docstring and this script's _ysub for the full reasoning.
    {"key": "ryoe", "col": "RYOE/Att", "label": "RYOE/Att\n(NGS)", "fmt": "0.00",
     "partial_coverage": True},
    # claude_code_spec_route_redzone_usage.md. A real USAGE signal (how often this player is
    # involved near the goal line), not an efficiency measure like the four above -- weight
    # DEFAULTS TO 0 (Model Assumptions C124) per the spec's own explicit instruction: usage
    # share and efficiency are different kinds of signal that shouldn't be silently mixed
    # into the existing score. Still flows through the full Section 1->3->4->5 pipeline
    # (real 3-yr decay-weighted history, real Z-score) exactly like every other metric --
    # only its WEIGHT is zero, so activating it later is a single-cell change, not a rebuild.
    {"key": "rz_share", "col": "Red-Zone Carry Share", "label": "Red-Zone\nCarry Share",
     "fmt": "0.00"},
]

# Same canonical 32-team row order as build_replacement_value.py (copied, not imported --
# that module's TEAM_ORDER is private to it; duplicating a short constant is simpler and
# safer than reaching into another script's module namespace).
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

# --- Styles (identical conventions to every prior tab) --------------------------------
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
    # No blank-row gap before this title -- matches the existing Availability Index
    # section, which sits directly below QB Index Weighting's last row (row 40) with no
    # separator either. Model Assumptions doesn't use the blank-row-per-section
    # convention the tab bodies do.
    title_row = 43
    ws.merge_cells(f"A{title_row}:D{title_row}")
    title = ws.cell(row=title_row, column=1, value=(
        "RB Value Index Weighting & Conversion (pts per std. dev.; reuses QB Index's "
        "points-scale constants C37/C38 -- see 'RB Value Index' tab)"
    ))
    title.font = HEADER_FONT
    title.fill = HEADER_FILL

    rows = [
        (44, "Rushing EPA/Play Weight (RB Index, pts per SD)", 0.35,
         "EPA/play is a complete single rushing stat -- weighted down from this tab's "
         "original 0.5 now that RYOE/Att (C82, real official NGS data) exists as a "
         "more precise, tracking-data-based isolate of the runner's own skill."),
        (45, "Rushing Success Rate Weight (RB Index, pts per SD)", 0.25,
         "Correlates with EPA but isolates consistency (positive-EPA rate) rather than "
         "magnitude -- weighted lower to avoid double-counting. Weighted down from 0.4 "
         "for the same 4-metric rebalancing as C44."),
        (46, "YPC Weight (RB Index, pts per SD)", 0.15,
         "Traditional, well-understood counting stat; plays the same role ANY/A plays "
         "for QB Index -- a sanity check alongside the EPA-based metrics, not the "
         "primary signal. Weighted down from 0.3 for the same rebalancing."),
        (47, "RB Index Points-to-Game-Points Conversion", 0.08,
         "A starting guess, like every other coefficient in this model -- deliberately "
         "smaller than QB's C39 (0.15): one RB touches the ball on a subset of "
         "offensive plays, unlike a QB who's on every snap, so replacement-value swings "
         "should have less aggregate scoring impact. This is a SEPARATE constant from "
         "C39 -- changing QB's conversion does not change this one, or vice versa."),
        (82, "RYOE/Att Weight (RB Index, pts per SD, real NFL Next Gen Stats)", 0.35,
         "Added after the fact once real, official NGS Rush Yards Over Expected data "
         "was found -- appended here rather than inserted next to C44-C46 to avoid "
         "shifting every row reference every later tab's build script already "
         "hardcodes (WR/TE/Kicking/OL/Front-Seven/Secondary/Special-Teams start at "
         "C48/C52/C57/C68/C73/C77, and OL's own appended weight is at C81). Weighted "
         "equal-highest with EPA/Play -- NGS's own tracking-data model of expected "
         "yards per carry is arguably the single most precise real signal available "
         "here, isolating the runner's own skill from blocking/scheme more directly "
         "than EPA (which conflates play-calling and blocking context) can."),
        (124, "Red-Zone Carry Share Weight (RB Index, pts per SD)", 0.0,
         "claude_code_spec_route_redzone_usage.md -- DEFAULTS TO 0 (informational only). "
         "Red-Zone Carry Share is a real USAGE signal, not an efficiency measure like "
         "every other weight above -- the spec's own explicit instruction is to keep "
         "usage share out of the existing weighted composite by default rather than "
         "silently change what a RB Index Score means. The metric itself is fully "
         "computed and flows through Section 1/3/4/5 like any other; set this above 0 "
         "to activate it deliberately."),
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
    print(f"Pulling {HISTORICAL_YEARS} play-by-play data for RB stats...")
    pbp = fetch_pbp(HISTORICAL_YEARS)
    season_stats = compute_team_season_rb_stats(pbp)
    historical_roles = compute_historical_rb_roles(season_stats)

    role_lookup = {
        (r["Player ID"], r["Season"]): r["Role"] for r in historical_roles.to_dict("records")
    }
    season_stats = season_stats.copy()
    season_stats["Role"] = [
        role_lookup.get((pid, season), "Other")
        for pid, season in zip(season_stats["Player ID"], season_stats["Season"], strict=True)
    ]
    season_stats = season_stats.sort_values(
        ["Team", "Season", "Carries"], ascending=[True, True, False]
    ).reset_index(drop=True)

    # claude_code_spec_consolidated_fixes.md Part 1: rb_stats' own Is Rookie Season is a
    # "first season observed in the pulled window" proxy -- overwrite it with real
    # per-season entry_year data (confirmed live this was contaminating the Rookie Baseline
    # with real veterans: Henry, Barkley, Kamara, McCaffrey all had a pulled-window season
    # wrongly flagged True).
    print(f"Pulling {HISTORICAL_YEARS} seasonal rosters for real Is Rookie Season data...")
    seasonal_rosters = fetch_seasonal_rosters(HISTORICAL_YEARS)
    season_stats = attach_real_rookie_season(season_stats, seasonal_rosters)

    print(f"Pulling {HISTORICAL_YEARS} Next Gen Stats rushing data for real RYOE/Att...")
    ngs_rushing = fetch_ngs_rushing(HISTORICAL_YEARS)
    ryoe = compute_player_season_ryoe(ngs_rushing)
    # Left join -- a real, qualifying-here player without a real NGS row (below NGS's own,
    # higher volume threshold) genuinely has no RYOE value; left blank, not zero-filled.
    season_stats = season_stats.merge(
        ryoe, on=["Player ID", "Season", "Team"], how="left"
    )
    n_missing_ryoe = season_stats["RYOE/Att"].isna().sum()
    print(f"{len(season_stats) - n_missing_ryoe} of {len(season_stats)} RB-seasons have a "
          f"real RYOE/Att value ({n_missing_ryoe} below NGS's own qualifying threshold).")

    print("Computing Red-Zone Carry Share (claude_code_spec_route_redzone_usage.md)...")
    rz_share = compute_player_season_red_zone_carry_share(pbp)
    season_stats = season_stats.merge(rz_share, on=["Player ID", "Season", "Team"], how="left")
    # Unlike RYOE/Att (a genuinely separate NGS pull with its own qualifying threshold), a
    # qualifying RB-season with zero real red-zone carries is a REAL 0.0, not a missing data
    # point -- the merge only fails to find a row when the player truly had none.
    season_stats["Red-Zone Carry Share"] = season_stats["Red-Zone Carry Share"].fillna(0.0)

    print(f"Pulling {CURRENT_ROSTER_YEAR} depth charts for current-roster RB population...")
    depth_charts = fetch_depth_charts([CURRENT_ROSTER_YEAR])
    current_starters = compute_current_starters(depth_charts)
    population = resolve_scored_population(current_starters, overrides, "RB")
    print(f"{len(population)} current-roster RB Starters/Backups identified.")

    carry_share = compute_carry_share(population, season_stats)

    return {
        "season_stats": season_stats,
        "population": population,
        "carry_share": carry_share,
    }


def _build_rookie_assumptions(season_stats: pd.DataFrame, population: pd.DataFrame) -> dict:
    """
    Returns {"table": DataFrame of individual rookie assumptions (may be empty),
    "zero_history_names": set of Player Name for current-roster RBs with zero qualifying
    pbp history at all}. See module docstring for why this is Section 2B.
    """
    metric_cols = [m["col"] for m in METRICS]
    known_ids = set(season_stats["Player ID"])
    zero_history = population[~population["Player ID"].isin(known_ids)]
    zero_history_names = list(zero_history["Player Name"])

    if not zero_history_names:
        print("No current-roster RB Starter/Backup has zero qualifying pbp history -- "
              "Section 2B will be empty.")
        return {"table": pd.DataFrame(), "zero_history_names": []}

    print(f"{len(zero_history_names)} current RB Starter/Backup(s) with zero qualifying "
          f"history: {zero_history_names} -- building ADP/trade-value-informed assumptions.")

    rookie_stats = season_stats[season_stats["Is Rookie Season"]]
    draft_info = fetch_draft_info()
    tier_averages = compute_historical_tier_averages(
        rookie_stats, draft_info, metric_cols, id_col="Player ID"
    )
    flat_baseline = {col: rookie_stats[col].mean() for col in metric_cols}

    market = fetch_ffc_dynasty_rookie_adp()
    if len(market):
        if "position" in market:
            rb_market = market[market["position"].str.upper() == "RB"]
        else:
            rb_market = market
        ranking = rank_rookie_class(rb_market, rank_col="adp", ascending=True, name_col="name")
        market_source = "FFC ADP"
        print(f"Using FFC Dynasty Rookie ADP: {len(ranking)} RBs ranked.")
    else:
        print("FFC Dynasty Rookie ADP returned no players (confirmed empty via direct curl "
              "before writing rookie_crosswalk.py -- too early in this draft cycle); "
              "falling back to api.fantasycalc.com dynasty trade values.")
        fc = fetch_fantasycalc_values()
        is_rb = fc["player.position"] == "RB"
        is_this_class = fc["player.maybeDraftInfo.year"] == CURRENT_ROSTER_YEAR
        rb_rookies = fc[is_rb & is_this_class]
        ranking = rank_rookie_class(
            rb_rookies, rank_col="value", ascending=False, name_col="player.name"
        )
        market_source = "FantasyCalc"
        print(f"Using fantasycalc.com dynasty trade values: {len(ranking)} rookie RBs ranked.")

    assumptions = assign_rookie_assumptions(
        ranking, tier_averages, metric_cols, flat_baseline,
        all_rookie_names=zero_history_names, market_source=market_source,
    )
    id_lookup = dict(zip(zero_history["Player Name"], zero_history["Player ID"], strict=True))
    team_lookup = dict(zip(zero_history["Player Name"], zero_history["Team"], strict=True))
    role_lookup = dict(zip(zero_history["Player Name"], zero_history["Role"], strict=True))
    assumptions = assumptions.copy()
    assumptions["Player ID"] = assumptions["Player Name"].map(id_lookup)
    assumptions["Team"] = assumptions["Player Name"].map(team_lookup)
    assumptions["Role"] = assumptions["Player Name"].map(role_lookup)
    return {"table": assumptions, "zero_history_names": zero_history_names}


def build(workbook_path: str) -> dict:
    wb = openpyxl.load_workbook(workbook_path)
    overrides = read_existing_overrides(wb, SHEET_NAME, ["Starter", "Backup"])
    print(f"Read back {len(overrides)} existing manual-override row(s) from Section 7 "
          "before rebuilding the sheet.")

    data = _pull_data(overrides)
    season_stats = data["season_stats"]
    population = data["population"]
    carry_share = data["carry_share"]
    n_rb = len(population)

    rookie = _build_rookie_assumptions(season_stats, population)
    rookie_table = rookie["table"]

    add_model_assumptions_weights(wb)

    if SHEET_NAME in wb.sheetnames:
        del wb[SHEET_NAME]
    ws = wb.create_sheet(SHEET_NAME, index=wb.sheetnames.index(QB_INDEX_SHEET) + 1)
    ws.column_dimensions["A"].width = 18.0
    ws.column_dimensions["C"].width = 20.0

    ws.merge_cells("A1:L1")
    t = ws.cell(row=1, column=1, value=(
        "RB Value Index -- Multi-Year Decay-Weighted RUSHING Rating (Rushing EPA/Play, "
        "Rushing Success Rate, YPC from nflverse pbp; RYOE/Att from real, official NFL "
        "Next Gen Stats). Receiving work out of the backfield is explicitly OUT OF SCOPE "
        "for this version -- a pass-catching RB will be undervalued here; see the closing "
        "note below before treating this as a complete RB value measure."
    ))
    t.font = Font(name="Arial", size=12, bold=True)

    # ==== Section 1: Raw 3-year data per RB-season =========================================
    sec1_first_row = 5
    sec1_last_row = sec1_first_row + len(season_stats) - 1
    _section_title(
        ws, 3, 12,
        "Section 1 \u2014 Raw 3-Year Data per RB-Season (from nflverse pbp; Role here is "
        "HISTORICAL attempts-ranking per past season -- labeling only, NOT used to pick "
        "who is scored in Section 3/5/6, see Section 3's population note). RYOE/Att (K) "
        "is real NFL Next Gen Stats data with its OWN, higher qualifying threshold -- "
        "blank means genuinely no real NGS value for that player-season, not zero. "
        "Red-Zone Carry Share (L, claude_code_spec_route_redzone_usage.md) is a real "
        "USAGE signal -- see this tab's closing note for why its composite weight "
        "defaults to 0.",
    )
    _header_row(
        ws, 4,
        ["Player Name", "Player ID", "Team", "Season", "Carries", "Rushing EPA/Play",
         "Rushing Success Rate", "YPC", "Is Rookie Season", "Role", "RYOE/Att\n(NGS)",
         "Red-Zone\nCarry Share"],
    )
    for i, r in enumerate(season_stats.to_dict("records")):
        row = sec1_first_row + i
        ryoe_v = float(r["RYOE/Att"]) if pd.notna(r.get("RYOE/Att")) else None
        values = [
            r["Player Name"], r["Player ID"], r["Team"], int(r["Season"]), int(r["Carries"]),
            float(r["Rushing EPA/Play"]), float(r["Rushing Success Rate"]), float(r["YPC"]),
            bool(r["Is Rookie Season"]), r["Role"], ryoe_v,
            float(r["Red-Zone Carry Share"]),
        ]
        for col, v in enumerate(values, start=1):
            cell = ws.cell(row=row, column=col, value=v)
            cell.font = INPUT_FONT
            if col == 6:
                cell.number_format = "0.000"
            elif col in (7, 8, 11, 12):
                cell.number_format = "0.00"

    id_range = f"$B${sec1_first_row}:$B${sec1_last_row}"
    season_range = f"$D${sec1_first_row}:$D${sec1_last_row}"
    rookie_range = f"$I${sec1_first_row}:$I${sec1_last_row}"
    role_range = f"$J${sec1_first_row}:$J${sec1_last_row}"
    sec1_col_of = {"epa": "F", "success": "G", "ypc": "H", "ryoe": "K", "rz_share": "L"}
    metric_ranges = {
        m["key"]: (
            f"${sec1_col_of[m['key']]}${sec1_first_row}:${sec1_col_of[m['key']]}${sec1_last_row}"
        )
        for m in METRICS
    }

    # ==== Section 2: League average per season (Starters+Backups, historical Role) + flat
    #      Rookie Baseline (all qualifying rookie seasons, any role, across pulled years) ====
    sec2_title_row = sec1_last_row + 2
    sec2_header_row = sec2_title_row + 1
    season_rows = {yr: sec2_header_row + 1 + i for i, yr in enumerate(HISTORICAL_YEARS)}
    rookie_baseline_row = sec2_header_row + 1 + len(HISTORICAL_YEARS)
    rookie_count_row = rookie_baseline_row + 1

    _section_title(
        ws, sec2_title_row, 1 + len(METRICS),
        "Section 2 \u2014 League Average per Season (historical Starters + Backups only) "
        "and flat Rookie Baseline (all qualifying rookie seasons, any role, across every "
        "pulled year -- the fallback used when a player isn't in Section 2B below)",
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
              "estimate with only 3 years pulled; recomputes automatically as more seasons "
              "are added",
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

    # ==== Section 2B: Individual Rookie Assumptions (ADP/trade-value-informed) =============
    sec2b_title_row = rookie_count_row + 2
    sec2b_header_row = sec2b_title_row + 1
    sec2b_first_row = sec2b_header_row + 1
    n_2b = len(rookie_table)
    sec2b_last_row = sec2b_first_row + max(n_2b, 1) - 1

    _section_title(
        ws, sec2b_title_row, 5 + len(METRICS),
        "Section 2B \u2014 Individual Rookie Assumptions (ADP/trade-value-informed, "
        "current draft class only -- see rookie_crosswalk.py / "
        "claude_code_spec_rookie_adp_crosswalk.md). Only lists current-roster RB "
        "Starters/Backups with ZERO qualifying pbp history; Section 3 looks this table up "
        "by Player ID FIRST for any missing year, falling back to the flat Section 2 "
        "Rookie Baseline for everyone else.",
    )
    _header_row(
        ws, sec2b_header_row,
        ["Player Name", "Player ID", "Team", "Role", *[m["label"] for m in METRICS],
         "Source"],
        height=20,
    )
    if n_2b:
        for i, r in enumerate(rookie_table.to_dict("records")):
            row = sec2b_first_row + i
            values = [r["Player Name"], r["Player ID"], r["Team"], r["Role"]]
            for col, v in enumerate(values, start=1):
                ws.cell(row=row, column=col, value=v).font = INPUT_FONT
            for j, m in enumerate(METRICS):
                v = r.get(m["col"])
                # pd.notna(), not `v is not None` -- a partial-coverage metric (RYOE/Att)
                # can legitimately produce a real NaN tier average (e.g. a whole tier with
                # zero real NGS-covered rookie seasons in the pulled window), and NaN is
                # NOT None in Python -- writing a literal NaN float into a cell produces an
                # invalid Excel value, not a blank one.
                cell = ws.cell(row=row, column=5 + j, value=float(v) if pd.notna(v) else None)
                cell.font = INPUT_FONT
                cell.number_format = m["fmt"]
            src = ws.cell(row=row, column=5 + len(METRICS), value=r.get("Source"))
            src.font = INPUT_FONT
    else:
        ws.merge_cells(
            start_row=sec2b_first_row, start_column=1, end_row=sec2b_first_row, end_column=8
        )
        empty_note = ws.cell(
            row=sec2b_first_row, column=1,
            value="(none currently -- no identified current-roster RB Starter/Backup has "
                  "zero qualifying pbp history; every missing year falls back to the flat "
                  "Section 2 Rookie Baseline)",
        )
        empty_note.font = NOTE_FONT

    sec2b_id_range = f"$B${sec2b_first_row}:$B${sec2b_last_row}"
    sec2b_metric_range = {
        m["key"]: (
            f"${get_column_letter(5 + j)}${sec2b_first_row}:"
            f"${get_column_letter(5 + j)}${sec2b_last_row}"
        )
        for j, m in enumerate(METRICS)
    }

    # ==== Section 3: Per-RB decay-weighted, regressed baseline, per metric ================
    # Population is the current-roster-identified Starters + Backups (Part B) -- NOT the
    # historical attempts-ranking used only to label Section 1 rows above.
    sec3_title_row = sec2b_last_row + 2
    sec3_header_row = sec3_title_row + 1
    sec3_first_row = sec3_header_row + 1
    sec3_last_row = sec3_first_row + n_rb - 1
    sec3_last_col = 5 + len(METRICS) * 7

    _section_title(
        ws, sec3_title_row, sec3_last_col,
        "Section 3 \u2014 Per-RB 3-Yr Decay-Weighted, Regressed Baseline. Population is "
        "the CURRENT-roster-identified Starters + Backups (from current_roster.py's live "
        "2026 depth-chart pull), not the historical attempts-ranking in Section 1's Role "
        "column -- a current RB1/RB2 who was a backup or unrostered in prior seasons is "
        "still scored here. Missing Y-2/Y-3 (or all 3, for a true rookie) substitute "
        "Section 2B's individual assumption first, falling back to the flat Section 2 "
        "Rookie Baseline -- same formula chain as QB Index Section 3 otherwise.",
    )
    headers = ["Player Name", "Player ID", "Team", "Role", "Years of\nReal History"]
    metric_block_start_col: dict[str, int] = {}
    col_cursor = 6
    for m in METRICS:
        metric_block_start_col[m["key"]] = col_cursor
        headers += [
            f"{m['label']} Y-1", f"{m['label']} Y-2", f"{m['label']} Y-3",
            f"Weighted\n{m['label']} Avg\n(3-Yr decay)", f"Team History\n{m['label']}",
            f"League Baseline\n{m['label']} (Y-1)", f"Projected 3-Yr\n{m['label']} Baseline",
        ]
        col_cursor += 7
    _header_row(ws, sec3_header_row, headers)

    for i, rb in enumerate(population.to_dict("records")):
        row = sec3_first_row + i
        ws.cell(row=row, column=1, value=rb["Player Name"]).font = FORMULA_FONT
        ws.cell(row=row, column=2, value=rb["Player ID"]).font = FORMULA_FONT
        ws.cell(row=row, column=3, value=rb["Team"]).font = FORMULA_FONT
        ws.cell(row=row, column=4, value=rb["Role"]).font = FORMULA_FONT

        years_hist_terms = "+".join(
            f"--(COUNTIFS({id_range},$B{row},{season_range},'Model Assumptions'!$C$18-{k})>0)"
            for k in (1, 2, 3)
        )
        yh = ws.cell(row=row, column=5, value=f"={years_hist_terms}")
        yh.font = FORMULA_FONT
        yh.number_format = "0"

        for m in METRICS:
            base = metric_block_start_col[m["key"]]
            y1, y2, y3, wavg, th, lb, pb = (get_column_letter(base + k) for k in range(7))
            mrange = metric_ranges[m["key"]]
            flat_cell = flat_rookie_cell[m["key"]]
            twob_metric_range = sec2b_metric_range[m["key"]]

            # RYOE/Att has its OWN, real qualifying threshold from NGS -- narrower than the
            # other 3 metrics' shared row-exists check. A player can have a real Section 1
            # row for a season (real EPA/Success/YPC) with a genuinely blank RYOE cell, so
            # RYOE's own existence check must ALSO require that specific cell to be
            # non-blank, not just that a row exists for that player-season.
            extra_existence_criteria = f",{mrange},\"<>\"" if m.get("partial_coverage") else ""

            def _ysub(offset: int, mrange=mrange, flat_cell=flat_cell,
                       twob_metric_range=twob_metric_range,
                       extra_existence_criteria=extra_existence_criteria,
                       partial_coverage=bool(m.get("partial_coverage"))) -> str:
                index_match = f"INDEX({twob_metric_range},MATCH($B{row},{sec2b_id_range},0))"
                if partial_coverage:
                    # A partial-coverage metric's Section 2B row can exist (player found)
                    # but hold a genuinely BLANK cell for this one metric (e.g. a whole
                    # historical tier with zero real NGS-covered rookie seasons) -- ISBLANK
                    # catches that; plain IFERROR alone would not, since a successful
                    # INDEX/MATCH returning blank isn't an error.
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

    # ==== Section 4: League average/std-dev of Section 3's Projected Baselines ============
    sec4_title_row = sec3_last_row + 2
    sec4_header_row = sec4_title_row + 1
    avg_row, std_row = sec4_header_row + 1, sec4_header_row + 2

    _section_title(
        ws, sec4_title_row, 1 + len(METRICS),
        "Section 4 \u2014 League Average & Std. Dev. of the 3-Yr Baselines",
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

    # ==== Section 5: Z-scores, weighted composite, points-scale RB Index Score ============
    sec5_title_row = std_row + 2
    sec5_header_row = sec5_title_row + 1
    sec5_first_row = sec5_header_row + 1
    sec5_last_row = sec5_first_row + n_rb - 1

    _section_title(
        ws, sec5_title_row, 7 + len(METRICS),
        "Section 5 \u2014 Z-Scores and RB Index Score (all four metrics are \"higher is "
        "better\" for a RB -- no sign-flip needed. Baseline/points-per-SD reuse QB "
        "Index's own Model Assumptions cells C37/C38 by design, so a score means the same "
        "thing on both tabs.)",
    )
    _header_row(
        ws, sec5_header_row,
        ["Player Name", "Player ID", "Team", "Role", *[f"{m['label']}\nZ" for m in METRICS],
         "Weighted\nZ-Score Sum", "RB Index\nScore (Points)", "Years of\nReal History"],
    )

    avg_cell_ref = {
        m["key"]: f"${get_column_letter(2 + j)}${avg_row}" for j, m in enumerate(METRICS)
    }
    std_cell_ref = {
        m["key"]: f"${get_column_letter(2 + j)}${std_row}" for j, m in enumerate(METRICS)
    }
    weight_cells = {
        "epa": "$C$44", "success": "$C$45", "ypc": "$C$46", "ryoe": "$C$82",
        "rz_share": "$C$124",
    }

    for i in range(n_rb):
        sec3_row = sec3_first_row + i
        row = sec5_first_row + i
        for col, src_col in ((1, "A"), (2, "B"), (3, "C"), (4, "D")):
            f = ws.cell(row=row, column=col, value=f"={src_col}{sec3_row}")
            f.font = FORMULA_FONT

        z_cols = []
        for j, m in enumerate(METRICS):
            pcol = proj_baseline_col[m["key"]]
            formula = f"=({pcol}{sec3_row}-{avg_cell_ref[m['key']]})/{std_cell_ref[m['key']]}"
            col = 5 + j
            cell = ws.cell(row=row, column=col, value=formula)
            cell.font = FORMULA_FONT
            cell.number_format = "0.00"
            z_cols.append(get_column_letter(col))

        weighted_terms = " + ".join(
            f"{z_cols[j]}{row}*'Model Assumptions'!{weight_cells[m['key']]}"
            for j, m in enumerate(METRICS)
        )
        wz_col = 5 + len(METRICS)
        wz = ws.cell(row=row, column=wz_col, value=f"={weighted_terms}")
        wz.font = FORMULA_FONT
        wz.number_format = "0.00"

        score = ws.cell(row=row, column=wz_col + 1, value=(
            f"='Model Assumptions'!$C$37+{get_column_letter(wz_col)}{row}*'Model Assumptions'!$C$38"
        ))
        score.font = FORMULA_FONT
        score.number_format = "0.0;(0.0)"

        yh_link = ws.cell(row=row, column=wz_col + 2, value=f"=E{sec3_row}")
        yh_link.font = FORMULA_FONT
        yh_link.number_format = "0"

    # ==== Section 6: Replacement Value Index (own conversion constant) + Carry Share ======
    sec6_title_row = sec5_last_row + 2
    sec6_header_row = sec6_title_row + 1
    sec6_first_row = sec6_header_row + 1
    sec6_last_row = sec6_first_row + len(TEAM_ORDER) - 1

    _section_title(
        ws, sec6_title_row, 10,
        "Section 6 \u2014 Replacement Value Index (Starter RB Index Score minus Backup RB "
        "Index Score, per team; can be negative -- a negative value means the backup rates "
        "HIGHER, and the game-point adjustment flips sign accordingly, same as QB Index). "
        "Carry Share (Y-1) flags committee backfields (near 50/50) vs. clear bell-cows "
        "(70/30 or more lopsided), where Replacement Value means less.",
    )
    _header_row(ws, sec6_header_row, [
        "Team", "Starter Name", "Starter RB\nIndex Score", "Backup Name", "Backup RB\nIndex Score",
        "Replacement Value\n(Index Points)", "Replacement Value\n(Game Points)",
        "Carry Share\n(Y-1)", "Starter Carries\n(Y-1)", "Backup Carries\n(Y-1)",
    ])

    # Real bug fixed here (found while wiring the Defensive Matchup Engine's Part C into
    # Week 1 Matchups, claude_code_spec_defensive_matchup_engine.md): this key column was
    # hardcoded to column 11 (K), which happened to be correct when RB Index had 3 METRICS
    # (wz_col=8, so wz_col+3=11=K) but silently started CLOBBERING Section 5's own "Years
    # of Real History" column once RYOE/Att expanded METRICS to 4 (wz_col=9, so Years of
    # Real History moved to wz_col+2=K, colliding with this hardcoded write) -- verified
    # live: every real RB's Years of Real History was being overwritten with the Team|Role
    # key string on every build since RYOE/Att shipped. Now computed as wz_col+3, matching
    # every other tab's own dynamic (not hardcoded) key-column convention.
    key_col = get_column_letter(wz_col + 3)
    # score_range had the SAME class of bug, caught here proactively before it repeated:
    # hardcoded to "$J$", which was only correct for the CURRENT METRICS count (4 -> wz_col=9
    # -> score=wz_col+1=10=J). claude_code_spec_route_redzone_usage.md's Red-Zone Carry
    # Share is METRICS' 5th entry, shifting score to column K -- a hardcoded "$J$" here would
    # have silently pointed Section 6's Starter/Backup score lookups (and therefore
    # Replacement Value) at the Weighted Z-Score Sum column instead of the real Score column.
    # Computed dynamically now, matching key_col's own fix above.
    score_col = get_column_letter(wz_col + 1)
    score_range = f"${score_col}${sec5_first_row}:${score_col}${sec5_last_row}"
    key_range = f"${key_col}${sec5_first_row}:${key_col}${sec5_last_row}"
    name_range = f"$A${sec5_first_row}:$A${sec5_last_row}"

    for r in range(sec5_first_row, sec5_last_row + 1):
        ws.cell(row=r, column=wz_col + 3, value=f'=C{r}&"|"&D{r}').font = FORMULA_FONT

    carry_lookup = {
        r["Team"]: r for r in carry_share.to_dict("records")
    }

    for i, team in enumerate(TEAM_ORDER):
        row = sec6_first_row + i
        t = ws.cell(row=row, column=1, value=team)
        t.font = INPUT_FONT

        starter_key = f'"{team}|Starter"'
        backup_key = f'"{team}|Backup"'

        starter_name = ws.cell(row=row, column=2, value=(
            f"=IFERROR(INDEX({name_range},MATCH({starter_key},{key_range},0)),\"\")"
        ))
        starter_score = ws.cell(row=row, column=3, value=(
            f"=IFERROR(INDEX({score_range},MATCH({starter_key},{key_range},0)),\"\")"
        ))
        backup_name = ws.cell(row=row, column=4, value=(
            f"=IFERROR(INDEX({name_range},MATCH({backup_key},{key_range},0)),\"\")"
        ))
        backup_score = ws.cell(row=row, column=5, value=(
            f"=IFERROR(INDEX({score_range},MATCH({backup_key},{key_range},0)),\"\")"
        ))
        for cell in (starter_name, starter_score, backup_name, backup_score):
            cell.font = FORMULA_FONT
        starter_score.number_format = "0.0;(0.0)"
        backup_score.number_format = "0.0;(0.0)"

        rv_index = ws.cell(row=row, column=6, value=(
            f'=IF(OR(C{row}="",E{row}=""),"",C{row}-E{row})'
        ))
        rv_game = ws.cell(row=row, column=7, value=(
            f'=IF(F{row}="","",F{row}*\'Model Assumptions\'!$C$47)'
        ))
        rv_index.font = FORMULA_FONT
        rv_game.font = FORMULA_FONT
        rv_index.number_format = "0.0;(0.0)"
        rv_game.number_format = "0.00;(0.00)"

        cs = carry_lookup.get(team)
        has_share = cs and cs["Carry Share (Y-1)"] is not None
        share_cell = ws.cell(
            row=row, column=8,
            value=float(cs["Carry Share (Y-1)"]) if has_share else None,
        )
        starter_carries_cell = ws.cell(
            row=row, column=9, value=int(cs["Starter Carries (Y-1)"]) if cs else None
        )
        backup_carries_cell = ws.cell(
            row=row, column=10, value=int(cs["Backup Carries (Y-1)"]) if cs else None
        )
        for cell in (share_cell, starter_carries_cell, backup_carries_cell):
            cell.font = INPUT_FONT
        share_cell.number_format = "0.0%"

    note_row = sec6_last_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=10)
    note = ws.cell(row=note_row, column=1, value=(
        "Replacement Value (Index Points) = Starter RB Index Score - Backup RB Index "
        "Score, per team; Replacement Value (Game Points) applies the RB Index "
        "Points-to-Game-Points Conversion (Model Assumptions C47 -- a SEPARATE constant "
        "from QB Index's C39). A team whose Starter or Backup never reached the "
        "50-carry qualifying threshold, or has zero real history AND no market-informed "
        "Section 2B assumption, shows blank rather than a misleading 0. Carry Share "
        "(Y-1) / Starter / Backup Carries (Y-1) are computed by "
        "nflverse_pull.rb_stats.compute_carry_share() at build time (a Python input, "
        "like Section 1's raw stats -- not a live in-sheet formula) from whichever "
        "season is each current Starter's/Backup's most recent qualifying one; blank "
        "means that team is missing a current Starter or Backup entirely. RECEIVING "
        "WORK OUT OF THE BACKFIELD IS NOT INCLUDED ANYWHERE ON THIS TAB -- a "
        "pass-catching specialist RB will be undervalued by this rushing-only index; "
        "this is a documented Phase 1 scope limit, not an oversight (see "
        "claude_code_spec_rb_index.md). RYOE/Att (Section 1 col K) is real, official NFL "
        "Next Gen Stats data with its OWN, higher qualifying-volume threshold than this "
        "tab's 50-carry minimum -- a real, qualifying RB-season with no real RYOE value "
        "shows blank there and correctly falls back to the flat Section 2 Rookie Baseline "
        "(or Section 2B's individual assumption) in Section 3, not a fabricated 0. The "
        "2026 depth-chart snapshot this tab's "
        "current-roster population (Section 3/5/6) is built from was pulled BEFORE "
        "final 53-man roster cuts -- same caveat as the rookie ADP/trade-value "
        "crosswalk in Section 2B, per the user's explicit decision to proceed anyway "
        "with this noted rather than wait. Red-Zone Carry Share (Section 1 col L, "
        "claude_code_spec_route_redzone_usage.md) is a real USAGE signal (how often "
        "this player is involved near the goal line), not efficiency -- it flows "
        "through the full Section 1->3->4->5 pipeline like every other metric, but its "
        "composite weight (Model Assumptions C124) DEFAULTS TO 0 so it stays "
        "informational-only rather than silently changing what the RB Index Score "
        "means; set C124 above 0 to activate it deliberately."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    # ==== Wire into Team Ratings (new, additive columns -- QB's O/P untouched) ============
    tr = wb[TEAM_RATINGS_SHEET]
    tr.cell(row=2, column=17, value="Starting RB\nStatus").font = HEADER_FONT
    tr.cell(row=2, column=17).fill = HEADER_FILL
    tr.cell(row=2, column=17).alignment = HEADER_ALIGN
    tr.cell(row=2, column=18, value="RB Replacement\nValue Adj (pts)").font = HEADER_FONT
    tr.cell(row=2, column=18).fill = HEADER_FILL
    tr.cell(row=2, column=18).alignment = HEADER_ALIGN

    rv_game_range = f"'{SHEET_NAME}'!$G${sec6_first_row}:$G${sec6_last_row}"
    rv_team_range = f"'{SHEET_NAME}'!$A${sec6_first_row}:$A${sec6_last_row}"

    for row in range(3, 3 + len(TEAM_ORDER)):
        status = tr.cell(row=row, column=17, value="RB1 In")
        status.font = INPUT_FONT
        # IFERROR wraps the negation too, not just INDEX/MATCH -- see build_replacement_
        # value.py's identical fix for the QB column: INDEX can succeed and still return
        # "" (a team whose Starter/Backup never reached the qualifying threshold), and
        # unary-minus on a blank string throws #VALUE! that a narrower
        # IFERROR(INDEX(...),0) would not catch.
        adj = tr.cell(row=row, column=18, value=(
            f'=IF(Q{row}="RB2 In",'
            f'IFERROR(-INDEX({rv_game_range},MATCH(A{row},{rv_team_range},0)),0),0)'
        ))
        adj.font = LINK_FONT
        adj.number_format = "0.00;(0.00)"

        # Net Power Rating (N) now also includes the RB Replacement Value adjustment,
        # additive alongside the existing QB one (P) -- neither disturbs the other.
        net = tr.cell(row=row, column=14, value=f"=J{row}-K{row}+L{row}+M{row}+P{row}+R{row}")
        net.font = FORMULA_FONT
        net.number_format = "0.0;(0.0)"

    note_row_tr = 3 + len(TEAM_ORDER) + 1
    # Extend the merged note range from build_replacement_value.py's (which stopped at P)
    # out to R so this new note doesn't collide with it -- write on the row just below.
    note_row_tr2 = note_row_tr + 1
    tr.merge_cells(start_row=note_row_tr2, start_column=1, end_row=note_row_tr2, end_column=18)
    tr_note = tr.cell(row=note_row_tr2, column=1, value=(
        "Starting RB Status (Q) is a manual per-team toggle: 'RB1 In' (default, no "
        "adjustment) or 'RB2 In'. When set to 'RB2 In', RB Replacement Value Adj (R) "
        "automatically pulls -(that team's Replacement Value in game points) from 'RB "
        "Value Index' Section 6 -- if the backup actually rates HIGHER than the starter "
        "(a negative Replacement Value), this correctly becomes a POSITIVE adjustment. "
        "This is fully separate from Starting QB Status (O) / QB Replacement Value Adj "
        "(P) above -- both apply additively to Net Power Rating (N) if both are set, "
        "and each uses its own conversion constant (Model Assumptions C39 for QB, C47 "
        "for RB)."
    ))
    tr_note.font = NOTE_FONT
    tr_note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(
        f"Built '{SHEET_NAME}': Section 1 {len(season_stats)} rows, Section 2B {n_2b} rows, "
        f"Section 3/5/6 {n_rb} RBs / {len(TEAM_ORDER)} teams. Wired into "
        f"'{TEAM_RATINGS_SHEET}' (cols Q/R)."
    )
    print(f"Saved to {workbook_path}")
    return {
        "sec1_rows": len(season_stats), "n_rb": n_rb, "n_2b": n_2b,
        "sec3_range": (sec3_first_row, sec3_last_row),
        "sec5_range": (sec5_first_row, sec5_last_row),
        "sec6_range": (sec6_first_row, sec6_last_row),
    }


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: uv run python scripts/build_rb_index.py "path/to/workbook.xlsx"')
        sys.exit(1)
    build(sys.argv[1])
