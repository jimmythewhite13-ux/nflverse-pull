"""
Single entry point for the nflverse-pull pipeline. Run it any time you want a full refresh:

    uv run python -m nflverse_pull.main "C:\\path\\to\\NFL_Prediction_Model.xlsx"

Two stages:
  1. update_workbook.py -- writes fresh PPG and efficiency data into YoY Baseline Engine /
     Advanced Efficiency Metrics Section 1 (fixed 96/32-row shape, values refreshed in
     place).
  2. QB Index / Replacement Value / Manual Override table / RB Value Index / WR-TE Value
     Index / Kicking Index / Offensive Line Index / Front Seven Index / Secondary Index /
     Special Teams Index / Availability Index / Pass Defense Matchup / Run Defense Matchup
     / the Defensive Matchup Engine's Week 1 Matchups wiring / EDGE-IDL Index / LB Index /
     CB-S Index / Special Teams Player Index / Pass Rush Generation Index / the OL vs. Pass
     Rush Matchup wiring / QB Environment Model / the Effective QB Rating wiring -- fully
     REBUILT from scratch each run (not a Section-1-only value refresh), because their row
     counts are inherently dynamic: which players currently qualify as a Starter/Backup, how
     many games have been played this season, etc. Skipped, non-fatally, on a workbook that
     doesn't have 'Advanced Efficiency Metrics' yet (run scripts/build_efficiency_engine.py
     once first).

     Order matters here and is NOT arbitrary: build_qb_index.py deletes and recreates the
     whole 'QB Index' sheet, which wipes Section 6 (Replacement Value) and Section 7 (Manual
     Override) along with it -- those two must be rebuilt AFTER it, every run, or a scheduled
     run silently leaves the sheet missing its override input cells. This was a real bug
     (found while verifying the RB Value Index build): RB Value Index and the Section 7
     rebuild were never wired into this pipeline at all, so a scheduled run left Section 7
     gone and RB Value Index stale after the very first QB Index rebuild that followed it.

Emailing a results summary is not part of this pipeline -- it's not a required step. If you
want that on demand, run nflverse_pull.email_results directly (see its module docstring for
the Gmail App Password setup it needs).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import openpyxl

from nflverse_pull.update_workbook import EFFICIENCY_SHEET, YOY_SHEET, update_workbook

DEFAULT_YEARS = [2023, 2024, 2025]

# scripts/ isn't part of the installed package (it's one-off/dev tooling, per its own
# module docstrings) -- reached via sys.path, same trick those scripts use to reach src/.
# Only works running from within this project checkout via `uv run`, which is the only way
# this project is ever actually run; not meant to survive a real package install elsewhere.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent.parent / "scripts"


def _rebuild_qb_and_availability(workbook_path: str) -> None:
    wb = openpyxl.load_workbook(workbook_path, read_only=True)
    has_efficiency_engine = EFFICIENCY_SHEET in wb.sheetnames
    wb.close()
    if not has_efficiency_engine:
        print(
            f"Skipped QB Index / RB Value Index / Availability Index: this workbook doesn't "
            f"have '{EFFICIENCY_SHEET}' yet (run scripts/build_efficiency_engine.py once "
            f"first)."
        )
        return

    if str(SCRIPTS_DIR) not in sys.path:
        sys.path.insert(0, str(SCRIPTS_DIR))
    import add_manual_override_table
    import build_availability_index
    import build_cb_s_index
    import build_defense_index
    import build_defensive_matchup_wiring
    import build_edge_idl_index
    import build_effective_qb_rating_wiring
    import build_kicking_index
    import build_lb_index
    import build_ol_pass_rush_wiring
    import build_oline_index
    import build_pass_defense_matchup
    import build_pass_rush_generation_index
    import build_qb_environment_model
    import build_qb_index
    import build_rb_index
    import build_replacement_value
    import build_run_defense_matchup
    import build_secondary_index
    import build_special_teams_index
    import build_special_teams_player_index
    import build_wr_te_index

    # NOTE: these scripts each pull their own fixed [2023, 2024, 2025] internally -- the
    # `years` argument to this module's run()/main() does not (yet) override them.
    #
    # Order is load-bearing (see the module docstring): build_qb_index deletes/recreates the
    # whole 'QB Index' sheet, so Section 6 (Replacement Value) and Section 7 (Manual
    # Override) must be rebuilt immediately after it, every run. build_rb_index,
    # build_kicking_index, build_oline_index, build_defense_index, build_secondary_index,
    # and build_special_teams_index EACH rewrite Team Ratings' Net Power Rating (column N)
    # formula wholesale with whatever set of adjustment terms that script knows about.
    # build_wr_te_index (claude_code_spec_consolidated_fixes.md Part 3) touches 'Team
    # Ratings' too -- it writes its own new column X (WR/TE Corps Quality Adjustment) -- but
    # deliberately does NOT touch column N itself, since it runs before every N-rewriting
    # script above and N gets rewritten wholesale by each of them anyway; only build_special_
    # teams_index's own N formula (at that point in the sequence) summed through column X.
    # build_edge_idl_index / build_lb_index / build_cb_s_index similarly write their own new
    # columns (Y/Z/AA) without touching N, for the same reason -- they run after build_
    # special_teams_index, so its N formula still wins until something later rewrites it.
    # build_special_teams_player_index -- the LAST Team-Ratings-wired script in this
    # function -- is the one that currently owns the complete N formula (column AB, summing
    # every term through Y/Z/AA/AB). If a future phase adds another Team-Ratings-wired tab,
    # update ITS Net Power Rating formula to include every prior term too (or, if it runs
    # before the N-rewriting scripts, just add its own new column and update whichever
    # script currently owns N instead), and keep whichever script owns the complete N
    # formula last in this function.
    #
    # claude_code_spec_consolidated_fixes.md Part 2 generalized the Manual Roster Override
    # table from QB-Index-only to every tab that resolves a current-roster population --
    # each add_manual_override_table.build(...) call below rebuilds THAT tab's own Section 7
    # (with that tab's real role labels) immediately after the tab it belongs to, same
    # reasoning as QB's original placement: the tab's own build script deletes/recreates the
    # whole sheet, wiping any override table along with it, so it must be rebuilt every run.
    build_qb_index.build(workbook_path)
    build_replacement_value.build(workbook_path)
    add_manual_override_table.build(workbook_path, "QB Index", ["Starter", "Backup"])
    build_rb_index.build(workbook_path)
    add_manual_override_table.build(workbook_path, "RB Value Index", ["Starter", "Backup"])
    build_wr_te_index.build(workbook_path)
    add_manual_override_table.build(
        workbook_path, "WR-TE Value Index", ["WR1", "WR2", "WR3", "TE1"]
    )
    build_kicking_index.build(workbook_path)
    add_manual_override_table.build(workbook_path, "Kicking Index", ["K1"])
    build_oline_index.build(workbook_path)
    add_manual_override_table.build(
        workbook_path, "Offensive Line Index", ["LT", "LG", "C", "RG", "RT"]
    )
    build_defense_index.build(workbook_path)
    build_secondary_index.build(workbook_path)
    build_special_teams_index.build(workbook_path)
    build_availability_index.build(workbook_path)

    # claude_code_spec_defensive_matchup_engine.md Part B/C. Pass/Run Defense Matchup are
    # independent of the pipeline above (pure pbp-based, no current-roster population, no
    # Team Ratings wiring) -- position doesn't matter relative to the N-rewriting scripts
    # above. build_defensive_matchup_wiring MUST run last of these three: it requires QB
    # Index, RB Value Index, AND both Defense Matchup tabs to already exist (reads each
    # one's real Section 5 Score/Team|Role-key columns to wire the phase-specific matchup
    # differential into Week 1 Matchups' Model Home/Away Score formula, additively --
    # see that script's own module docstring for why this is treated with more caution
    # than a typical adjustment column).
    build_pass_defense_matchup.build(workbook_path)
    build_run_defense_matchup.build(workbook_path)
    build_defensive_matchup_wiring.build(workbook_path)

    # claude_code_spec_defensive_player_index.md Part B/C, folding in P/KR/PR per the
    # user's own "fold in P/KR/PR now too" decision. Each of these four writes its own new
    # Team Ratings column (Y/Z/AA/AB) WITHOUT touching N, same convention build_wr_te_index
    # already established -- EXCEPT build_special_teams_player_index, which runs LAST of
    # the four and therefore owns the updated "most complete" N formula (taking over from
    # build_special_teams_index above), per this project's established convention: whichever
    # Team-Ratings-wired script runs last owns N. Order among these four doesn't otherwise
    # matter -- they're independent of each other and of the Defensive Matchup Engine tabs
    # above (own current-roster populations, own Team Ratings columns).
    build_edge_idl_index.build(workbook_path)
    add_manual_override_table.build(
        workbook_path, "EDGE-IDL Index",
        ["LDE", "LDE2", "RDE", "RDE2", "LDT", "LDT2", "RDT", "RDT2", "NT", "NT2"],
    )
    build_lb_index.build(workbook_path)
    add_manual_override_table.build(
        workbook_path, "LB Index",
        ["WLB", "WLB2", "SLB", "SLB2", "MLB", "MLB2", "LILB", "LILB2"],
    )
    build_cb_s_index.build(workbook_path)
    add_manual_override_table.build(
        workbook_path, "CB-S Index",
        ["LCB", "LCB2", "RCB", "RCB2", "NB", "NB2", "FS", "FS2", "SS", "SS2"],
    )
    build_special_teams_player_index.build(workbook_path)
    add_manual_override_table.build(
        workbook_path, "Special Teams Player Index", ["P1", "P2", "KR1", "KR2", "PR1", "PR2"]
    )

    # claude_code_spec_ol_vs_pass_rush_matchup.md. Extends the Defensive Matchup Engine
    # pattern to Offensive Line vs. opposing pass rush. build_pass_rush_generation_index
    # requires 'Pass Defense Matchup' to already exist (it's a 100% live-referenced
    # composite of that tab's own Sack Rate/Pressure Proxy/Blitz Rate columns -- no new data
    # pull of its own). build_ol_pass_rush_wiring requires both 'Offensive Line Index' and
    # 'Pass Rush Generation Index', and appends to the SAME Week 1 Matchups Z/AA formulas
    # build_defensive_matchup_wiring already appended to above -- append_term_once makes the
    # order between the two wiring scripts functionally irrelevant, but this one places its
    # own closing note a few rows below the Defensive Matchup Engine's, so it runs after for
    # a sensible reading order. Neither of these two scripts touches Team Ratings or the N
    # formula -- same reasoning as Pass/Run Defense Matchup: a matchup-specific differential,
    # not a static team-quality number.
    build_pass_rush_generation_index.build(workbook_path)
    build_ol_pass_rush_wiring.build(workbook_path)

    # claude_code_spec_qb_environment_model.md. build_qb_environment_model requires QB
    # Index and Availability Index (both already built above); build_effective_qb_rating_
    # wiring requires it, plus Offensive Line Index and the OL vs. Pass Rush Matchup wiring
    # (both already built above too) -- it OVERWRITES Week 1 Matchups' AU/AX cells (Home/
    # Away Starter QB Index Score) to reference the new Effective QB Rating instead, so it
    # must run AFTER build_defensive_matchup_wiring (which originally wrote AU/AX) -- see
    # that script's own module docstring for why this overwrite is safe (AU/AX are read
    # only by the Pass Matchup Differential, AW/AZ, which picks up the new value with no
    # changes of its own). Neither script touches Team Ratings or the N formula.
    build_qb_environment_model.build(workbook_path)
    build_effective_qb_rating_wiring.build(workbook_path)


def run(workbook_path: str, years: list[int] | None = None) -> None:
    years = years or DEFAULT_YEARS

    result = update_workbook(workbook_path, years)
    print(
        f"Updated {result['yoy_rows']} rows in '{YOY_SHEET}' and "
        f"{result['efficiency_rows']} rows in '{EFFICIENCY_SHEET}'."
    )

    _rebuild_qb_and_availability(workbook_path)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("workbook_path", help="Path to the NFL Prediction Model .xlsx file")
    parser.add_argument(
        "--years", type=int, nargs="+", default=None,
        help="Seasons to pull, e.g. --years 2023 2024 2025 (default: 2023 2024 2025)",
    )
    args = parser.parse_args()
    run(args.workbook_path, args.years)


if __name__ == "__main__":
    main()
