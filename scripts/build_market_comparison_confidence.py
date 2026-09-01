"""
Builds "Market Comparison & Confidence" -- claude_code_spec_market_comparison_confidence_
explanation_engine.md (Version 8, partial). Scope note from the spec itself, carried onto
this tab: this deliberately does NOT build the full 6-stage cascading module architecture
from the original roadmap (OL -> Pressure -> QB -> Passing -> Explosive -> Points) -- that
needs validated coefficients between each stage, which this project doesn't have without a
backtesting harness. The existing OL-Pressure-to-Effective-QB-Rating link (QB Environment
Model spec) is the full extent of cascading here; nothing further is chained.

Part A -- Market Comparison: mostly consolidation, not new data. Every value here is a real
INDEX/MATCH reference into Season Matchups' own already-computed columns (via that tab's own
real Game Key helper, col DF -- a single-criteria MATCH, not the unwrapped multi-criteria
array MATCH pattern this project already caught and removed as a real bug earlier this
session). The one genuinely new piece: Win Probability, a standard logistic conversion of
Model Margin -- `1/(1+EXP(-Margin/K))`, K a NEW tunable Model Assumptions constant (NOT a
fixed formula), since the correct slope really should come from backtesting eventually.

Part B -- Confidence Score: built from REAL, already-computable signals only:
  - Sample Size: real Games Played (Team Ratings col H) for both teams, averaged and scaled
    against a real 17-game season.
  - QB/Injury certainty: whether THIS game's own real Starting QB Status shows "Backup In"
    (Season Matchups AQ/AR), or a real Manual Override is set on QB Index's own Section 7 for
    either team -- an override being in use signals the automated pull was uncertain or
    stale. Scoped to QB Index's own override table specifically (the position with the
    largest real single-game impact); RB/WR-TE/Kicking/OL overrides are not additionally
    checked here, a documented scope trim, not an oversight.
  - OL continuity: the spec's own explicit fallback -- "until [OL Full-Line Risk] lands, use
    the existing Center-only risk flag" -- real Is Rookie Starter flag, filtered to Position
    "C" specifically (SUMPRODUCT 2-criteria lookup -- Offensive Line Index Section 6 is
    grouped by POSITION not by team, verified live before writing this).
  - Matchup agreement: real sign-agreement across 3 already-computed per-game adjustment
    differentials (Phase Matchup, OL Pressure, Explosive Play) against the model's own final
    Margin sign -- literally checking signs of existing columns, per the spec's own
    instruction, no new signal invented.
  - NO fabricated "model variance" component -- omitted entirely (not even a placeholder
    input), per the spec's own explicit instruction; a real prediction-residual variance
    needs backtesting data this project doesn't have yet.
Combined via a tunable weighted score (Model Assumptions) into a Low/Medium/Medium-High/High
tier.

Part C -- Explanation Engine: a templated SORT of REAL, already-computed adjustment values,
not free-text generation. 9 named "Net Home Advantage (pts)" values (Home side minus Away
side, or the single asymmetric term where only one side gets it) are computed from columns
that already feed Z/AA -- Rest, Manual Injury, QB Replacement, Phase Matchup, OL Pressure,
Explosive Play, HFA Delta, Road Fatigue, Travel Direction. Ranked by absolute magnitude using
LARGE()/MATCH() (the same ranking technique WR-TE Value Index's own Corps Quality already
established), never SORT/FILTER/UNIQUE/SEQUENCE. Weather/Division are deliberately excluded
from this ranking -- verified live before building this that both feed Z AND AA identically
(+U/2 to each, +Y/2 to each), so neither one differentiates which team it favors; they affect
the game TOTAL, not the split.

Usage:
    uv run python scripts/build_market_comparison_confidence.py "C:\\path\\to\\model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nflverse_pull.availability import fetch_schedules_with_dates  # noqa: E402
from nflverse_pull.season_schedule import (  # noqa: E402
    compute_roof_fallback,
    compute_season_schedule,
)

HISTORICAL_YEARS = [2023, 2024, 2025]
CURRENT_SEASON = 2026
SHEET_NAME = "Market Comparison & Confidence"
SEASON_SHEET = "Season Matchups"
QB_INDEX_SHEET = "QB Index"
OL_SHEET = "Offensive Line Index"
TEAM_RATINGS_SHEET = "Team Ratings"

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

# Column layout, by NAME -- avoids hand-counted literal column numbers scattered through the
# row-writing loop (the exact class of bug an earlier draft of this script fell into).
COLUMNS = [
    "Week", "Away Team", "Home Team", "Game Key",
    "Team A (Away)\nProjected Score", "Team B (Home)\nProjected Score",
    "Model Spread\n(Home-Away)", "Market Spread\n(DK, Home)", "Spread Edge\n(Model-DK)",
    "Model\nTotal", "Market Total\n(DK)", "Total Edge\n(Model-DK)",
    "Win Probability\n(Home)",
    "Home Games\nPlayed (ref)", "Away Games\nPlayed (ref)", "Sample Size\nComponent",
    "QB/Override\nCertainty Component", "OL Center\nContinuity Component",
    "Matchup Agreement\nComponent", "Confidence\nComposite (0-1)", "Confidence\nTier",
    "Rest Net Home\nAdv. (pts)", "Injury Net Home\nAdv. (pts)", "QB Repl. Net Home\nAdv. (pts)",
    "Phase Matchup Net\nHome Adv. (pts)", "OL Pressure Net\nHome Adv. (pts)",
    "Explosive Play Net\nHome Adv. (pts)", "HFA Delta Net\nHome Adv. (pts)",
    "Road Fatigue Net\nHome Adv. (pts)", "Travel Direction\nNet Home Adv. (pts)",
    # Same-sign-as-Margin / opposite-sign |value| helper cells -- REAL, plain per-cell
    # formulas (never an array expression) so LARGE()/MATCH() below can operate on them
    # exactly the same safe way WR-TE Value Index's own Corps Quality already does (LARGE
    # applied to a plain cell range, never to a computed array -- verified live against
    # that tab's own real formula before building this).
    "Rest SS", "Injury SS", "QB Repl. SS", "Phase SS", "OL Press. SS", "Explosive SS",
    "HFA SS", "Road Fat. SS", "Travel SS",
    "Rest OS", "Injury OS", "QB Repl. OS", "Phase OS", "OL Press. OS", "Explosive OS",
    "HFA OS", "Road Fat. OS", "Travel OS",
    "Primary\nAdvantage", "Secondary\nAdvantage", "Negative /\nRisk",
    # claude_code_spec_season_win_total_moneyline.md Part B -- standard, well-established
    # conversions, not new modeling. Home/Away Moneyline are real refs into Season
    # Matchups' own new manual input columns (DG/DH); everything else here is a direct,
    # standard formula.
    "Home\nMoneyline (ref)", "Away\nMoneyline (ref)",
    "Model WP -> ML\n(Home)", "Model WP -> ML\n(Away)",
    "Home Raw Implied\nProbability", "Away Raw Implied\nProbability",
    "Home De-Vigged\nProbability", "Away De-Vigged\nProbability",
    "Moneyline Edge\n(Home)", "Moneyline Edge\n(Away)",
]
COL = {name: i + 1 for i, name in enumerate(COLUMNS)}
LET = {name: get_column_letter(i + 1) for i, name in enumerate(COLUMNS)}

# The 9 named adjustments feeding the Explanation Engine ranking, in column order (must
# match the COLUMNS list above from "Rest Net Home Adv." through "Travel Direction...").
ADJUSTMENT_NAMES = [
    "Rest", "Injury", "QB Replacement", "Phase Matchup", "OL Pressure", "Explosive Play",
    "HFA Delta", "Road Fatigue", "Travel Direction",
]
ADJUSTMENT_COLS = [
    "Rest Net Home\nAdv. (pts)", "Injury Net Home\nAdv. (pts)", "QB Repl. Net Home\nAdv. (pts)",
    "Phase Matchup Net\nHome Adv. (pts)", "OL Pressure Net\nHome Adv. (pts)",
    "Explosive Play Net\nHome Adv. (pts)", "HFA Delta Net\nHome Adv. (pts)",
    "Road Fatigue Net\nHome Adv. (pts)", "Travel Direction\nNet Home Adv. (pts)",
]
SS_COLS = [
    "Rest SS", "Injury SS", "QB Repl. SS", "Phase SS", "OL Press. SS", "Explosive SS",
    "HFA SS", "Road Fat. SS", "Travel SS",
]
OS_COLS = [
    "Rest OS", "Injury OS", "QB Repl. OS", "Phase OS", "OL Press. OS", "Explosive OS",
    "HFA OS", "Road Fat. OS", "Travel OS",
]


def _find_title_row(ws, needle: str) -> int:
    for row in range(1, ws.max_row + 1):
        val = ws.cell(row=row, column=1).value
        if val and str(val).strip().startswith(needle):
            return row
    raise ValueError(f"Could not find a row starting with {needle!r} in '{ws.title}'.")


def add_model_assumptions_weights(wb: openpyxl.Workbook) -> None:
    ws = wb["Model Assumptions"]
    title_row = 170
    ws.merge_cells(f"A{title_row}:D{title_row}")
    title = ws.cell(row=title_row, column=1, value=(
        "Market Comparison, Confidence & Explanation Engine (see 'Market Comparison & "
        "Confidence' tab)"
    ))
    title.font = HEADER_FONT
    title.fill = HEADER_FILL

    rows = [
        (171, "Win Probability Logistic Slope (pts per logit)", 10.5,
         "A starting guess, like every other coefficient in this model -- the correct "
         "slope really should come from backtesting eventually. Converts Model Margin "
         "into Win Probability via 1/(1+EXP(-Margin/K)); larger K = a flatter curve "
         "(less confident swings per point of margin)."),
        (172, "Confidence: Sample Size Weight", 0.25,
         "Real Games Played (Team Ratings col H), averaged across both teams and scaled "
         "against a real 17-game season."),
        (173, "Confidence: QB/Override Certainty Weight", 0.25,
         "Real signal: this game's own Starting QB Status ('Backup In') and whether QB "
         "Index's own Manual Override table is set for either team -- more active "
         "overrides/backup flags lowers this component."),
        (174, "Confidence: OL Center Continuity Weight", 0.25,
         "Real signal: the existing Center-only Is Rookie Starter flag (Offensive Line "
         "Index Section 6) -- the spec's own explicit interim proxy until OL Full-Line "
         "Risk lands."),
        (175, "Confidence: Matchup Agreement Weight", 0.25,
         "Real signal: sign-agreement across Phase Matchup / OL Pressure / Explosive "
         "Play adjustment differentials against the model's own final Margin sign -- "
         "literally checking signs of existing columns, no new signal invented."),
        (176, "Confidence Tier Threshold -- Low/Medium (composite, 0-1)", 0.40, None),
        (177, "Confidence Tier Threshold -- Medium/Medium-High (composite, 0-1)", 0.60, None),
        (178, "Confidence Tier Threshold -- Medium-High/High (composite, 0-1)", 0.80, None),
    ]
    for row, label, value, note in rows:
        ws.cell(row=row, column=2, value=label)
        c = ws.cell(row=row, column=3, value=value)
        c.font = INPUT_FONT
        c.fill = ASSUMPTION_FILL
        c.number_format = "0.00"
        if note:
            n = ws.cell(row=row, column=4, value=note)
            n.font = NOTE_FONT
            n.alignment = Alignment(wrap_text=True, vertical="top")

    note_row = 179
    ws.merge_cells(f"A{note_row}:D{note_row}")
    n = ws.cell(row=note_row, column=1, value=(
        "NO 'model variance' component exists anywhere in the Confidence Score -- a real "
        "prediction-residual variance needs backtesting data this project doesn't have "
        "yet (see claude_code_spec_market_comparison_confidence_explanation_engine.md's "
        "own explicit instruction). Not even a placeholder input here; see the "
        "'Market Comparison & Confidence' tab's own closing note."
    ))
    n.font = NOTE_FONT
    n.alignment = Alignment(wrap_text=True, vertical="top")


def _pull_schedule():
    sched_multi = fetch_schedules_with_dates(HISTORICAL_YEARS)
    sched_current = fetch_schedules_with_dates([CURRENT_SEASON])
    roof_fallback = compute_roof_fallback(sched_multi)
    return compute_season_schedule(sched_current, CURRENT_SEASON, roof_fallback)


def build(workbook_path: str) -> dict:
    schedule = _pull_schedule()

    wb = openpyxl.load_workbook(workbook_path)
    for required in (SEASON_SHEET, QB_INDEX_SHEET, OL_SHEET, TEAM_RATINGS_SHEET):
        if required not in wb.sheetnames:
            raise ValueError(
                f"'{required}' not found -- run its own build script first (see this "
                "script's own module docstring for the required order)."
            )
    add_model_assumptions_weights(wb)

    if SHEET_NAME in wb.sheetnames:
        del wb[SHEET_NAME]
    ws = wb.create_sheet(SHEET_NAME, index=wb.sheetnames.index(SEASON_SHEET) + 1)
    ws.column_dimensions["B"].width = 18.0
    ws.column_dimensions["C"].width = 18.0

    ws.merge_cells("A1:M1")
    t = ws.cell(row=1, column=1, value=(
        "Market Comparison & Confidence -- Version 8 (partial): consolidated market "
        "comparison + Win Probability (Part A), real-signal Confidence Score (Part B), "
        "mechanical Explanation Engine (Part C). Full 6-stage cascade NOT built -- only "
        "the existing OL-Pressure-to-Effective-QB-Rating link."
    ))
    t.font = Font(name="Arial", size=12, bold=True)

    # ---- Real ranges on Season Matchups, discovered dynamically (survives any row-count
    # shift, e.g. a future season with a different real schedule length). ----------------
    sm = wb[SEASON_SHEET]
    sm_first, sm_last = 3, 3
    while sm.cell(row=sm_last + 1, column=1).value is not None:
        sm_last += 1
    key_range = f"'{SEASON_SHEET}'!$DF${sm_first}:$DF${sm_last}"

    def sm_col(col_letter: str) -> str:
        return f"'{SEASON_SHEET}'!${col_letter}${sm_first}:${col_letter}${sm_last}"

    # QB Index Section 7 (Manual Roster Override) real range.
    qb_ws = wb[QB_INDEX_SHEET]
    qb_sec7_title = _find_title_row(qb_ws, "Section 7")
    qb_sec7_first = qb_sec7_title + 2
    qb_sec7_last = qb_sec7_first
    while qb_ws.cell(row=qb_sec7_last + 1, column=1).value is not None:
        qb_sec7_last += 1
    qb_ov_team = f"'{QB_INDEX_SHEET}'!$A${qb_sec7_first}:$A${qb_sec7_last}"
    qb_ov_starter = f"'{QB_INDEX_SHEET}'!$B${qb_sec7_first}:$B${qb_sec7_last}"
    qb_ov_backup = f"'{QB_INDEX_SHEET}'!$C${qb_sec7_first}:$C${qb_sec7_last}"

    # Offensive Line Index Section 6 (Individual Starters) real range -- grouped by
    # POSITION, not team, so a Center-only lookup needs a real 2-criteria match.
    ol_ws = wb[OL_SHEET]
    ol_sec6_title = _find_title_row(ol_ws, "Section 6")
    ol_sec6_first = ol_sec6_title + 2
    ol_sec6_last = ol_sec6_first
    while ol_ws.cell(row=ol_sec6_last + 1, column=1).value is not None:
        ol_sec6_last += 1
    ol_team_range = f"'{OL_SHEET}'!$A${ol_sec6_first}:$A${ol_sec6_last}"
    ol_pos_range = f"'{OL_SHEET}'!$B${ol_sec6_first}:$B${ol_sec6_last}"
    ol_rookie_range = f"'{OL_SHEET}'!$F${ol_sec6_first}:$F${ol_sec6_last}"

    ws.row_dimensions[2].height = 32
    for name in COLUMNS:
        c = ws.cell(row=2, column=COL[name], value=name)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = HEADER_ALIGN

    def L(name: str, row: int) -> str:
        return f"{LET[name]}{row}"

    first_row = 3
    for i, rec in enumerate(schedule.to_dict("records")):
        row = first_row + i
        week = int(rec["Week"])
        away, home = rec["Away Team"], rec["Home Team"]
        game_key = f"{week}|{away}|{home}"

        for name, val in (
            ("Week", week), ("Away Team", away), ("Home Team", home), ("Game Key", game_key),
        ):
            cell = ws.cell(row=row, column=COL[name], value=val)
            cell.font = INPUT_FONT

        # Precomputed cell references (a plain dict lookup, not an inline L("...\n...", row)
        # call) -- Python's f-string grammar on this project's Python version disallows a
        # backslash (the \n in several real column names) inside an f-string's {} braces.
        ref = {
            "home": L("Home Team", row), "away": L("Away Team", row),
            "key": L("Game Key", row),
            "margin": L("Model Spread\n(Home-Away)", row),
            "home_gp": L("Home Games\nPlayed (ref)", row),
            "away_gp": L("Away Games\nPlayed (ref)", row),
            "sample": L("Sample Size\nComponent", row),
            "override": L("QB/Override\nCertainty Component", row),
            "olcont": L("OL Center\nContinuity Component", row),
            "agree": L("Matchup Agreement\nComponent", row),
            "composite": L("Confidence\nComposite (0-1)", row),
        }

        # ==== Part A: Market Comparison (real refs into Season Matchups) ==================
        refs = [
            ("Team A (Away)\nProjected Score", "AA"), ("Team B (Home)\nProjected Score", "Z"),
            ("Model Spread\n(Home-Away)", "AC"), ("Market Spread\n(DK, Home)", "AD"),
            ("Spread Edge\n(Model-DK)", "AG"), ("Model\nTotal", "AB"),
            ("Market Total\n(DK)", "AE"), ("Total Edge\n(Model-DK)", "AH"),
        ]
        for colname, sm_letter in refs:
            cell = ws.cell(row=row, column=COL[colname], value=(
                f'=IFERROR(INDEX({sm_col(sm_letter)},MATCH({L("Game Key", row)},'
                f'{key_range},0)),"")'
            ))
            cell.font = LINK_FONT
            cell.number_format = "0.0;(0.0)"

        wp = ws.cell(row=row, column=COL["Win Probability\n(Home)"], value=(
            f'=IF({ref["margin"]}="","",1/(1+EXP(-{ref["margin"]}/'
            f"'Model Assumptions'!$C$171)))"
        ))
        wp.font = FORMULA_FONT
        wp.number_format = "0.0%"

        # ==== Part B: Confidence Score ======================================================
        hgp = ws.cell(row=row, column=COL["Home Games\nPlayed (ref)"], value=(
            f"=IFERROR(INDEX('{TEAM_RATINGS_SHEET}'!$H$3:$H$34,"
            f"MATCH({L('Home Team', row)},'{TEAM_RATINGS_SHEET}'!$A$3:$A$34,0)),0)"
        ))
        agp = ws.cell(row=row, column=COL["Away Games\nPlayed (ref)"], value=(
            f"=IFERROR(INDEX('{TEAM_RATINGS_SHEET}'!$H$3:$H$34,"
            f"MATCH({L('Away Team', row)},'{TEAM_RATINGS_SHEET}'!$A$3:$A$34,0)),0)"
        ))
        hgp.font = LINK_FONT
        agp.font = LINK_FONT

        sample = ws.cell(row=row, column=COL["Sample Size\nComponent"], value=(
            f'=MIN(1,(({ref["home_gp"]}+{ref["away_gp"]})/2)/17)'
        ))
        sample.font = FORMULA_FONT
        sample.number_format = "0.00"

        home_qb_backup = (
            f'--(INDEX({sm_col("AQ")},MATCH({L("Game Key", row)},{key_range},0))="Backup In")'
        )
        away_qb_backup = (
            f'--(INDEX({sm_col("AR")},MATCH({L("Game Key", row)},{key_range},0))="Backup In")'
        )
        home_qb_override = (
            f'--OR(IFERROR(INDEX({qb_ov_starter},MATCH({L("Home Team", row)},{qb_ov_team},0))'
            f'<>"",FALSE),IFERROR(INDEX({qb_ov_backup},MATCH({L("Home Team", row)},'
            f'{qb_ov_team},0))<>"",FALSE))'
        )
        away_qb_override = (
            f'--OR(IFERROR(INDEX({qb_ov_starter},MATCH({L("Away Team", row)},{qb_ov_team},0))'
            f'<>"",FALSE),IFERROR(INDEX({qb_ov_backup},MATCH({L("Away Team", row)},'
            f'{qb_ov_team},0))<>"",FALSE))'
        )
        override = ws.cell(row=row, column=COL["QB/Override\nCertainty Component"], value=(
            f"=1-((IFERROR({home_qb_backup},0)+IFERROR({away_qb_backup},0)+"
            f"IFERROR({home_qb_override},0)+IFERROR({away_qb_override},0))/4)"
        ))
        override.font = FORMULA_FONT
        override.number_format = "0.00"

        home_center_rookie = (
            f'SUMPRODUCT(({ol_team_range}={L("Home Team", row)})*({ol_pos_range}="C")*'
            f'{ol_rookie_range})'
        )
        away_center_rookie = (
            f'SUMPRODUCT(({ol_team_range}={L("Away Team", row)})*({ol_pos_range}="C")*'
            f'{ol_rookie_range})'
        )
        olcont = ws.cell(row=row, column=COL["OL Center\nContinuity Component"], value=(
            f"=1-(({home_center_rookie}+{away_center_rookie})/2)"
        ))
        olcont.font = FORMULA_FONT
        olcont.number_format = "0.00"

        # ==== Part C: 9 named Net Home Advantage values (also feed Matchup Agreement) =====
        adj_formula = {
            "Rest": lambda: (
                f'=IFERROR(INDEX({sm_col("O")},MATCH({L("Game Key", row)},{key_range},0)),0)'
            ),
            "Injury": lambda: (
                f'=IFERROR(INDEX({sm_col("V")},MATCH({L("Game Key", row)},{key_range},0))-'
                f'INDEX({sm_col("W")},MATCH({L("Game Key", row)},{key_range},0)),0)'
            ),
            "QB Replacement": lambda: (
                f'=IFERROR(INDEX({sm_col("AS")},MATCH({L("Game Key", row)},{key_range},0))-'
                f'INDEX({sm_col("AT")},MATCH({L("Game Key", row)},{key_range},0)),0)'
            ),
            "Phase Matchup": lambda: (
                f'=IFERROR(INDEX({sm_col("BG")},MATCH({L("Game Key", row)},{key_range},0))-'
                f'INDEX({sm_col("BH")},MATCH({L("Game Key", row)},{key_range},0)),0)'
            ),
            "OL Pressure": lambda: (
                f'=IFERROR(INDEX({sm_col("BO")},MATCH({L("Game Key", row)},{key_range},0))-'
                f'INDEX({sm_col("BP")},MATCH({L("Game Key", row)},{key_range},0)),0)'
            ),
            "Explosive Play": lambda: (
                f'=IFERROR(INDEX({sm_col("CO")},MATCH({L("Game Key", row)},{key_range},0))-'
                f'INDEX({sm_col("CP")},MATCH({L("Game Key", row)},{key_range},0)),0)'
            ),
            "HFA Delta": lambda: (
                f'=IFERROR(INDEX({sm_col("CR")},MATCH({L("Game Key", row)},{key_range},0))-'
                f'INDEX({sm_col("CS")},MATCH({L("Game Key", row)},{key_range},0)),0)'
            ),
            "Road Fatigue": lambda: (
                f'=IFERROR(INDEX({sm_col("CV")},MATCH({L("Game Key", row)},{key_range},0))-'
                f'INDEX({sm_col("CW")},MATCH({L("Game Key", row)},{key_range},0)),0)'
            ),
            "Travel Direction": lambda: (
                f'=IFERROR(-INDEX({sm_col("DA")},MATCH({L("Game Key", row)},{key_range},0)),0)'
            ),
        }
        for adj_name, colname in zip(ADJUSTMENT_NAMES, ADJUSTMENT_COLS, strict=True):
            cell = ws.cell(row=row, column=COL[colname], value=adj_formula[adj_name]())
            cell.font = FORMULA_FONT
            cell.number_format = "0.00;(0.00)"

        agreement_source_cols = (
            "Phase Matchup Net\nHome Adv. (pts)", "OL Pressure Net\nHome Adv. (pts)",
            "Explosive Play Net\nHome Adv. (pts)",
        )
        agree_terms = "+".join(
            f'--(SIGN({L(colname, row)})=SIGN({ref["margin"]}))'
            for colname in agreement_source_cols
        )
        agree = ws.cell(row=row, column=COL["Matchup Agreement\nComponent"], value=(
            f'=IF({ref["margin"]}="","",({agree_terms})/3)'
        ))
        agree.font = FORMULA_FONT
        agree.number_format = "0.00"

        composite = ws.cell(row=row, column=COL["Confidence\nComposite (0-1)"], value=(
            f"={ref['sample']}*'Model Assumptions'!$C$172+"
            f"{ref['override']}*'Model Assumptions'!$C$173+"
            f"{ref['olcont']}*'Model Assumptions'!$C$174+"
            f"IF({ref['agree']}=\"\",0,{ref['agree']})*'Model Assumptions'!$C$175"
        ))
        composite.font = FORMULA_FONT
        composite.number_format = "0.00"

        tier = ws.cell(row=row, column=COL["Confidence\nTier"], value=(
            f"=IF({ref['composite']}>='Model Assumptions'!$C$178,\"High\","
            f"IF({ref['composite']}>='Model Assumptions'!$C$177,"
            f"\"Medium-High\",IF({ref['composite']}>="
            f"'Model Assumptions'!$C$176,\"Medium\",\"Low\")))"
        ))
        tier.font = FORMULA_FONT

        # ==== Part C: rank the 9 named adjustments by |magnitude|, via LARGE()/MATCH() ====
        # (no SORT/FILTER/UNIQUE/SEQUENCE -- the same technique WR-TE Value Index's own
        # Corps Quality already established for top-N selection). Real, PLAIN per-cell
        # formulas materialize the same-sign/opposite-sign |value| first (a sentinel -1
        # when the sign doesn't match, so it never wins a LARGE() ranking) -- LARGE()/
        # MATCH() then operate on a real cell RANGE, never a computed array expression
        # (which would silently need CSE entry to evaluate correctly, the exact class of
        # bug this project already caught and removed once this session).
        margin_ref = ref["margin"]
        for adj_colname, ss_colname, os_colname in zip(
            ADJUSTMENT_COLS, SS_COLS, OS_COLS, strict=True
        ):
            adj_cell = L(adj_colname, row)
            ss = ws.cell(row=row, column=COL[ss_colname], value=(
                f'=IF({margin_ref}="",-1,IF(SIGN({adj_cell})=SIGN({margin_ref}),'
                f'ABS({adj_cell}),-1))'
            ))
            os_ = ws.cell(row=row, column=COL[os_colname], value=(
                f'=IF({margin_ref}="",-1,IF(SIGN({adj_cell})<>SIGN({margin_ref}),'
                f'ABS({adj_cell}),-1))'
            ))
            ss.font = FORMULA_FONT
            os_.font = FORMULA_FONT
            ss.number_format = "0.00"
            os_.number_format = "0.00"

        ss_range = f'{L(SS_COLS[0], row)}:{L(SS_COLS[-1], row)}'
        os_range = f'{L(OS_COLS[0], row)}:{L(OS_COLS[-1], row)}'
        label_array = '{"' + '","'.join(ADJUSTMENT_NAMES) + '"}'
        adj_range = f'{L(ADJUSTMENT_COLS[0], row)}:{L(ADJUSTMENT_COLS[-1], row)}'

        def _explanation(rank: int, use_same_sign: bool) -> str:
            source_range = ss_range if use_same_sign else os_range
            large = f'LARGE({source_range},{rank})'
            match_pos = f'MATCH({large},{source_range},0)'
            label = f'INDEX({label_array},{match_pos})'
            raw_val = f'INDEX({adj_range},{match_pos})'
            return (
                f'=IF(OR({margin_ref}="",{large}<0),"",{label}&": "&'
                f'TEXT({raw_val},"+0.0;-0.0")&" pts")'
            )

        primary = ws.cell(row=row, column=COL["Primary\nAdvantage"], value=_explanation(1, True))
        secondary = ws.cell(
            row=row, column=COL["Secondary\nAdvantage"], value=_explanation(2, True)
        )
        risk = ws.cell(row=row, column=COL["Negative /\nRisk"], value=_explanation(1, False))
        for cell in (primary, secondary, risk):
            cell.font = FORMULA_FONT

        # ==== claude_code_spec_season_win_total_moneyline.md Part B: Moneyline ============
        # Standard, well-established conversions -- not new modeling.
        home_ml = ws.cell(row=row, column=COL["Home\nMoneyline (ref)"], value=(
            f'=IFERROR(INDEX({sm_col("DG")},MATCH({ref["key"]},{key_range},0)),"")'
        ))
        away_ml = ws.cell(row=row, column=COL["Away\nMoneyline (ref)"], value=(
            f'=IFERROR(INDEX({sm_col("DH")},MATCH({ref["key"]},{key_range},0)),"")'
        ))
        home_ml.font = LINK_FONT
        away_ml.font = LINK_FONT

        home_ml_ref = L("Home\nMoneyline (ref)", row)
        away_ml_ref = L("Away\nMoneyline (ref)", row)

        wp_ref = L("Win Probability\n(Home)", row)
        wp_to_ml_home = ws.cell(row=row, column=COL["Model WP -> ML\n(Home)"], value=(
            f'=IF({wp_ref}="","",IF({wp_ref}>=0.5,-({wp_ref}/(1-{wp_ref}))*100,'
            f'((1-{wp_ref})/{wp_ref})*100))'
        ))
        wp_to_ml_away = ws.cell(row=row, column=COL["Model WP -> ML\n(Away)"], value=(
            f'=IF({wp_ref}="","",IF((1-{wp_ref})>=0.5,-((1-{wp_ref})/{wp_ref})*100,'
            f'({wp_ref}/(1-{wp_ref}))*100))'
        ))
        wp_to_ml_home.font = FORMULA_FONT
        wp_to_ml_away.font = FORMULA_FONT
        wp_to_ml_home.number_format = "+0;-0"
        wp_to_ml_away.number_format = "+0;-0"

        home_raw = ws.cell(row=row, column=COL["Home Raw Implied\nProbability"], value=(
            f'=IF({home_ml_ref}="","",IF({home_ml_ref}<0,-{home_ml_ref}/(-{home_ml_ref}+100),'
            f'100/({home_ml_ref}+100)))'
        ))
        away_raw = ws.cell(row=row, column=COL["Away Raw Implied\nProbability"], value=(
            f'=IF({away_ml_ref}="","",IF({away_ml_ref}<0,-{away_ml_ref}/(-{away_ml_ref}+100),'
            f'100/({away_ml_ref}+100)))'
        ))
        home_raw.font = FORMULA_FONT
        away_raw.font = FORMULA_FONT
        home_raw.number_format = "0.0%"
        away_raw.number_format = "0.0%"

        home_raw_ref = L("Home Raw Implied\nProbability", row)
        away_raw_ref = L("Away Raw Implied\nProbability", row)
        home_devig = ws.cell(row=row, column=COL["Home De-Vigged\nProbability"], value=(
            f'=IF(OR({home_raw_ref}="",{away_raw_ref}=""),"",'
            f'{home_raw_ref}/({home_raw_ref}+{away_raw_ref}))'
        ))
        away_devig = ws.cell(row=row, column=COL["Away De-Vigged\nProbability"], value=(
            f'=IF(OR({home_raw_ref}="",{away_raw_ref}=""),"",'
            f'{away_raw_ref}/({home_raw_ref}+{away_raw_ref}))'
        ))
        home_devig.font = FORMULA_FONT
        away_devig.font = FORMULA_FONT
        home_devig.number_format = "0.0%"
        away_devig.number_format = "0.0%"

        home_devig_ref = L("Home De-Vigged\nProbability", row)
        away_devig_ref = L("Away De-Vigged\nProbability", row)
        ml_edge_home = ws.cell(row=row, column=COL["Moneyline Edge\n(Home)"], value=(
            f'=IF(OR({wp_ref}="",{home_devig_ref}=""),"",{wp_ref}-{home_devig_ref})'
        ))
        ml_edge_away = ws.cell(row=row, column=COL["Moneyline Edge\n(Away)"], value=(
            f'=IF(OR({wp_ref}="",{away_devig_ref}=""),"",(1-{wp_ref})-{away_devig_ref})'
        ))
        ml_edge_home.font = FORMULA_FONT
        ml_edge_away.font = FORMULA_FONT
        ml_edge_home.number_format = "0.0%;(0.0%)"
        ml_edge_away.number_format = "0.0%;(0.0%)"

    last_row = first_row + len(schedule) - 1

    note_row = last_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=15)
    note = ws.cell(row=note_row, column=1, value=(
        "claude_code_spec_market_comparison_confidence_explanation_engine.md (Version 8, "
        "partial). Full 6-stage cascade NOT built -- only the existing OL-Pressure-to-"
        "Effective-QB-Rating link (QB Environment Model spec). Part A is pure consolidation "
        "-- every value here is a real reference into Season Matchups' own already-computed "
        "columns via its real Game Key helper (single-criteria MATCH). Win Probability is a "
        "standard logistic conversion of Model Margin, its slope a NEW tunable constant "
        "(C171), NOT yet validated by backtesting. Part B's Confidence Score uses ONLY real "
        "signals (Sample Size, QB/Override Certainty, OL Center Continuity, Matchup "
        "Agreement) -- NO fabricated 'model variance' component exists anywhere here, "
        "omitted entirely per the spec's own explicit instruction; a real prediction-"
        "residual variance needs backtesting data this project doesn't have yet. Part C's "
        "Primary/Secondary/Risk labels are a mechanical LARGE()/MATCH() ranking of 9 real, "
        "already-computed 'Net Home Advantage' values -- never free-text generation. "
        "Weather and Divisional adjustments are deliberately excluded from this ranking: "
        "both feed Z AND AA identically (+U/2 and +Y/2 to each side), so neither "
        "differentiates which team it favors -- they affect the game TOTAL, not the split. "
        "claude_code_spec_season_win_total_moneyline.md Part B (Moneyline) was added here: "
        "Model Win Probability -> American Moneyline and Sportsbook Moneyline -> de-vigged "
        "implied probability are both standard, well-established conversions, not new "
        "modeling. De-vigging normalizes both teams' raw implied probabilities (which sum "
        "to MORE than 100% due to the book's own margin) so they sum to exactly 100% before "
        "computing Moneyline Edge -- comparing the model against the raw, un-de-vigged "
        "number would unfairly make the model look better than it is."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(f"Built '{SHEET_NAME}': {len(schedule)} real games.")
    print(f"Saved to {workbook_path}")
    return {"game_rows": list(range(first_row, last_row + 1))}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print(
            'Usage: uv run python scripts/build_market_comparison_confidence.py '
            '"path/to/workbook.xlsx"'
        )
        sys.exit(1)
    build(sys.argv[1])
