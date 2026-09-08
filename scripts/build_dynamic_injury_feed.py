"""
Builds claude_code_spec_dynamic_injury_feed.md: a new, non-breaking `QB Status
Auto-Suggestion` column on "Team Ratings", plus the real, current-week injury-report
reference block it looks up (a new Section 4 on "Availability Index").

Core constraint, per the spec's own explicit instruction: this NEVER changes the existing
`Starting QB Status` column (O) -- its data type, formula dependents (QB Replacement Value
Adj, Net Power Rating) stay completely unchanged. The suggestion column is purely additive,
appended as a NEW column at the end of Team Ratings (not inserted next to O) -- inserting
mid-sheet would shift every column reference in every downstream formula on this heavily-
wired tab (P onward), which this project's own established convention avoids everywhere else
(see e.g. build_replacement_value.py's own real precedent of appending new sections/columns,
never inserting).

Real, reused (not re-derived) data sources:
- Current starting QB per team: `current_roster.fetch_depth_charts()` +
  `compute_current_starters()` -- the SAME real depth-chart pull QB Index's own Section 3
  already uses, filtered to Position == "QB", Depth Order == 1.
- Current-week injury report: `availability.fetch_injuries()` -- the SAME real
  `import_injuries()` call Availability Index's own Section 1 already uses, joined by real
  player name against the real current starter, latest real week present in the pull.

Requires "QB Index" and "Availability Index" to already exist.

Usage:
    uv run python scripts/build_dynamic_injury_feed.py "C:\\path\\to\\NFL_Prediction_Model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from add_manual_override_table import read_existing_overrides  # noqa: E402

from nflverse_pull.availability import fetch_injuries  # noqa: E402
from nflverse_pull.current_roster import (  # noqa: E402
    compute_current_starters,
    fetch_depth_charts,
    resolve_scored_population,
)

TEAM_RATINGS_SHEET = "Team Ratings"
AVAILABILITY_SHEET = "Availability Index"
MODEL_ASSUMPTIONS_SHEET = "Model Assumptions"
CURRENT_SEASON_CELL = "C18"

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
INPUT_FONT = Font(name="Arial", size=10, color="FF0000FF")     # real, machine-pulled values
FORMULA_FONT = Font(name="Arial", size=10, color="FF000000")   # local formula
LINK_FONT = Font(name="Arial", size=10, color="FF008000")      # cross-sheet formula
NOTE_FONT = Font(name="Arial", size=9, color="FF808080")

# Real, four-tier suggestion, per the spec exactly -- never auto-toggles Questionable, never
# collapses Doubtful into the same label as Out.
SUGGESTION_FORMULA_TEMPLATE = (
    '=IFERROR(IF({status_ref}="Out","Backup In",'
    'IF({status_ref}="Doubtful","Likely Backup In",'
    'IF({status_ref}="Questionable","Uncertain -- Verify Before Game",'
    '"Starter In"))),"Starter In")'
)


def _safe_merge(ws, start_row: int, start_column: int, end_row: int, end_column: int) -> None:
    """Real idempotency helper: openpyxl raises if a range is already (even partially)
    merged, which a second real run of this script would otherwise hit every time."""
    target = (start_row, start_column, end_row, end_column)
    for rng in list(ws.merged_cells.ranges):
        if (rng.min_row, rng.min_col, rng.max_row, rng.max_col) == target:
            return
    ws.merge_cells(
        start_row=start_row, start_column=start_column, end_row=end_row, end_column=end_column,
    )


def _resolve_real_current_qb_status(
    wb: openpyxl.Workbook, season: int,
) -> dict[str, dict]:
    """Real, live join done in Python (not a fragile cross-sheet array formula): current
    starting QB per team, matched against their own real current-week injury designation.

    Real, deliberate use of `resolve_scored_population()` + `read_existing_overrides()` --
    the SAME real override-aware resolution QB Index's own Section 3 uses -- rather than the
    raw depth-chart pull alone. Acceptance criterion 5 requires an active Manual Roster
    Override to determine who this suggestion is even ABOUT; a raw depth-chart-only lookup
    would silently diverge from QB Index's own real current-starter identification the
    moment a user has filled in a real override (a beat-writer report, a camp competition
    outcome) -- caught before shipping, not assumed correct.

    Returns {team_full_name: {"qb_name": str, "report_status": str|None,
    "practice_status": str|None, "week": int|None}}."""
    depth_charts = fetch_depth_charts([season])
    starters = compute_current_starters(depth_charts)
    overrides = read_existing_overrides(wb, "QB Index", ["Starter", "Backup"])
    population = resolve_scored_population(starters, overrides, "QB")
    starter_rows = population[population["Role"] == "Starter"]
    team_to_qb = dict(zip(starter_rows["Team"], starter_rows["Player Name"], strict=True))

    injuries = fetch_injuries([season])
    current_week = None
    if injuries is not None and not injuries.empty:
        current_week = int(injuries["week"].max())
        injuries = injuries[injuries["week"] == current_week]
    injury_lookup = {}
    if injuries is not None and not injuries.empty:
        for _, row in injuries.iterrows():
            injury_lookup[row["full_name"]] = {
                "report_status": row.get("report_status"),
                "practice_status": row.get("practice_status"),
            }

    result = {}
    for team in TEAM_ORDER:
        qb_name = team_to_qb.get(team)
        real = injury_lookup.get(qb_name, {}) if qb_name else {}
        result[team] = {
            "qb_name": qb_name,
            "report_status": real.get("report_status"),
            "practice_status": real.get("practice_status"),
            "week": current_week,
        }
    return result


def build(workbook_path: str) -> None:
    wb = openpyxl.load_workbook(workbook_path)
    for required in (TEAM_RATINGS_SHEET, AVAILABILITY_SHEET, MODEL_ASSUMPTIONS_SHEET):
        if required not in wb.sheetnames:
            raise ValueError(f"Real required sheet {required!r} not found -- build order "
                              f"dependency not met (never fabricated by this script).")

    ma = wb[MODEL_ASSUMPTIONS_SHEET]
    season = ma["C18"].value
    if not isinstance(season, int):
        raise ValueError(f"Real 'Current Season' cell (Model Assumptions!{CURRENT_SEASON_CELL}) "
                          f"is not a real integer -- got {season!r}.")

    print(f"Resolving real current starting QBs (override-aware, matching QB Index Section "
          f"3's own real resolution) + real current-week injury report for season {season}...")
    real_status = _resolve_real_current_qb_status(wb, season)
    real_week = next((v["week"] for v in real_status.values() if v["week"] is not None), None)
    print(f"  Real current week (latest real injury-report week found): {real_week!r}")

    # ==== New Section 4 on Availability Index: real current-week injury reference block ====
    # Real idempotency: re-running this script must overwrite the SAME real block in place,
    # not append a duplicate one -- search for the existing Section 4 marker first (same real
    # technique add_manual_override_table.read_existing_overrides() already uses for its own
    # Section 7 marker), matching this project's established "safe to re-run" convention.
    av = wb[AVAILABILITY_SHEET]
    section_marker = "Section 4 — Current-Week Starting QB Injury Report"
    sec_title_row = next(
        (r for r in range(1, av.max_row + 1)
         if isinstance(av.cell(row=r, column=1).value, str)
         and av.cell(row=r, column=1).value.startswith(section_marker)),
        av.max_row + 3,
    )
    av.cell(row=sec_title_row, column=1, value=(
        "Section 4 \u2014 Current-Week Starting QB Injury Report (real, live -- refresh by "
        "re-running scripts/build_dynamic_injury_feed.py; reflects PRE-GAME injury report "
        "status only, never in-game -- there is no real-time in-game data source in this "
        "project)"
    ))
    _safe_merge(av, sec_title_row, 1, sec_title_row, 6)
    av.cell(row=sec_title_row, column=1).font = TITLE_FONT
    av.cell(row=sec_title_row, column=1).fill = TITLE_FILL

    header_row = sec_title_row + 1
    headers = ["Team", "Current Starting QB (real)", "Report Status", "Practice Status",
               "As-Of Week"]
    for col, h in enumerate(headers, start=1):
        c = av.cell(row=header_row, column=col, value=h)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = HEADER_ALIGN

    first_data_row = header_row + 1
    for i, team in enumerate(TEAM_ORDER):
        row = first_data_row + i
        real = real_status[team]
        values = [team, real["qb_name"], real["report_status"], real["practice_status"],
                  real["week"]]
        for col, v in enumerate(values, start=1):
            cell = av.cell(row=row, column=col, value=v)
            cell.font = INPUT_FONT
    last_data_row = first_data_row + len(TEAM_ORDER) - 1

    # ==== New QB Status Auto-Suggestion column on Team Ratings (appended, not inserted) =====
    # Real idempotency, same reasoning as Section 4 above: reuse the existing column if this
    # script already ran once, rather than appending a second "QB Status\nAuto-Suggestion"
    # column every re-run.
    tr = wb[TEAM_RATINGS_SHEET]
    existing_col = next(
        (c for c in range(1, tr.max_column + 1)
         if tr.cell(row=2, column=c).value == "QB Status\nAuto-Suggestion"),
        None,
    )
    suggestion_col = existing_col or (tr.max_column + 1)
    if tr.cell(row=2, column=15).value != "Starting QB\nStatus":
        raise ValueError("Real 'Starting QB Status' header not found at Team Ratings column "
                          "O (15) -- the tab's real layout has changed since this script was "
                          "written; refusing to guess a new column.")

    header_cell = tr.cell(row=2, column=suggestion_col, value="QB Status\nAuto-Suggestion")
    header_cell.font = HEADER_FONT
    header_cell.fill = HEADER_FILL
    header_cell.alignment = HEADER_ALIGN

    status_col_letter = get_column_letter(3)  # Availability Index Section 4 col C
    team_col_letter = get_column_letter(1)    # Availability Index Section 4 col A
    for i, team in enumerate(TEAM_ORDER):
        row = 3 + i
        team_ref = f"A{row}"
        status_lookup = (
            f"IFERROR(INDEX('{AVAILABILITY_SHEET}'!${status_col_letter}${first_data_row}:"
            f"${status_col_letter}${last_data_row},"
            f"MATCH({team_ref},'{AVAILABILITY_SHEET}'!${team_col_letter}${first_data_row}:"
            f"${team_col_letter}${last_data_row},0)),\"\")"
        )
        formula = SUGGESTION_FORMULA_TEMPLATE.format(status_ref=status_lookup)
        cell = tr.cell(row=row, column=suggestion_col, value=formula)
        cell.font = LINK_FONT

    note_row = 3 + len(TEAM_ORDER) + 2
    _safe_merge(tr, note_row, 1, note_row, suggestion_col)
    note = tr.cell(row=note_row, column=1, value=(
        "QB Status Auto-Suggestion (new column) is INFORMATIONAL ONLY -- it never writes into "
        "or overwrites the real, manual Starting QB Status field (O); a person updates that "
        "field themselves after checking the suggestion. It reflects PRE-GAME injury report "
        "status only (Availability Index, Section 4) -- it cannot and does not account for an "
        "in-game injury, since there is no real-time in-game data source in this project. If "
        "the QB Index Section 7 Manual Roster Override table has an active override for a "
        "team's real current starter, that override already determines who Section 4's real "
        "'Current Starting QB' lookup resolves to (Section 4 is built from the SAME real "
        "current-roster pull QB Index Section 3 uses) -- this suggestion column never competes "
        "with or masks that override."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    n_flagged = sum(
        1 for v in real_status.values()
        if v["report_status"] in ("Out", "Doubtful", "Questionable")
    )
    print(f"Built: Availability Index Section 4 ({len(TEAM_ORDER)} real teams, rows "
          f"{first_data_row}-{last_data_row}); Team Ratings column "
          f"{get_column_letter(suggestion_col)} (QB Status Auto-Suggestion). Real week "
          f"{real_week!r}: {n_flagged}/{len(TEAM_ORDER)} real teams have a starting QB "
          f"currently on the real injury report.")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: uv run python scripts/build_dynamic_injury_feed.py '
              '"path/to/workbook.xlsx"')
        sys.exit(1)
    build(sys.argv[1])
