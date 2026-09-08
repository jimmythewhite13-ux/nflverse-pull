"""
Builds "Simple Summary Page" per claude_code_spec_simple_summary_page.md -- a pure
presentation/formatting tab, zero new computation. Every number on this tab is a plain
INDEX/MATCH reference into a real calculation that already exists on Season Matchups, Market
Comparison & Confidence, or Player Prop Projections, converted from a raw signed number or a
technical label into a plain-language sentence via IF-statement text formatting -- never
recomputed independently. There is deliberately NO add_model_assumptions_weights() in this
script: the spec's own "What NOT to include" section bans any Model Assumptions reference on
this tab, and there is no new tunable constant to add -- every threshold this tab's plain-
language labels depend on (the spread/total Recommended Play threshold, the Confidence tier
cutoffs) already lives on, and is already applied by, the tab being referenced.

One row per real game (272 rows, same real schedule as Season Matchups/Market Comparison &
Confidence), split into:

Reader-facing columns (what a plain-language reader actually sees):
  Matchup | Predicted Score | Model Lean | Market Line (Spread) | Recommended Play (Spread) |
  Model Total | Market Total | Recommended Play (Total) | Moneyline (Model) | Moneyline
  (Market) | Recommended Play (Moneyline) | Confidence | Top Reason | Top Prop #1/#2/#3.

  Every "No Edge" case (spread, total, moneyline) displays as exactly "Pass" -- never the raw
  "No Edge" label, never an ambiguous blank. The Moneyline (Model) sentence is always shown
  when computable (Market Comparison & Confidence's own Model Win Probability formula only
  depends on the real Model Margin, not on a market moneyline being entered) -- but the
  Moneyline (Market) sentence and the Moneyline recommendation both correctly show as
  "not yet entered" / "Pass" when no real moneyline has been entered for that game yet,
  never a fabricated market-implied percentage.

Internal reference columns (cols U-AH): the raw values/labels the reader-facing sentences are
built from -- kept as their own columns (not inlined into one giant formula per cell) so each
sentence formula stays a single, simple, auditable IF/TEXT wrapper around one already-computed
number, matching this project's "reference existing formulas via INDEX/MATCH only" convention.

Prop slot helper columns (cols AI onward, 20 slots x 2 columns = 40 columns): the real,
per-game "Top 3 Player Props" mechanism. Every current-roster team has EXACTLY 6 scored
player-roles (QB Starter, RB Starter, WR1, WR2, WR3, TE1 -- current_roster.
POSITION_ROLE_LABELS), so every real game has EXACTLY 20 candidate props, always: 1 Passing
Yards + 1 Rushing Yards + (3 WR x 2 stat types) + (1 TE x 2 stat types) = 10, times 2 sides.
This is FIXED, deterministic roster structure, not data -- so each of the 20 slots is a
literal, hardcoded (Side, Position, Role, Stat Label, Unit) tuple known at build time, found
per real game via Player Prop Projections' own real Team|Position|Role|Week helper key (a
single-criterion MATCH, avoiding a 4-criteria array match). For each slot: one column holds a
fully-formatted plain-language candidate sentence (blank if that prop has no real Sportsbook
Line entered yet), the other holds that slot's real |Edge| for ranking. The reader-facing
Top Prop #1/#2/#3 columns then apply the exact same LARGE()-based top-N technique already
established in this project (WR-TE Value Index's Corps Quality calculation; also the
Explosive Play Matchup Explanation Engine's Primary/Secondary Advantage columns) -- LARGE()
and MATCH() applied to a real, already-materialized plain cell range on THIS row, never to a
computed array expression, the same CSE-avoidance discipline used everywhere else. Each of
the 3 ranks is independently IFERROR-guarded, so a game with only 1-2 real prop lines entered
still shows whichever ranks are actually available rather than erroring the whole row; a game
with zero real lines entered anywhere shows a plain "No player prop lines entered yet for
this game" message for every rank, never a fabricated example prop.

Usage:
    uv run python scripts/build_simple_summary_page.py "C:\\path\\to\\NFL_Prediction_Model.xlsx"
"""
from __future__ import annotations

import sys
from pathlib import Path

import openpyxl
from openpyxl.styles import Alignment, Font, PatternFill
from openpyxl.utils import get_column_letter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parent))

SHEET_NAME = "Simple Summary Page"
SEASON_SHEET = "Season Matchups"
MARKET_SHEET = "Market Comparison & Confidence"
PPP_SHEET = "Player Prop Projections"

TITLE_FONT = Font(name="Arial", size=10, bold=True)
TITLE_FILL = PatternFill("solid", fgColor="FFD9E1F2")
HEADER_FONT = Font(name="Arial", size=10, bold=True, color="FFFFFFFF")
HEADER_FILL = PatternFill("solid", fgColor="FF1F4E78")
HEADER_ALIGN = Alignment(wrap_text=True, horizontal="center", vertical="center")
INPUT_FONT = Font(name="Arial", size=10, color="FF0000FF")
FORMULA_FONT = Font(name="Arial", size=10, color="FF000000")
LINK_FONT = Font(name="Arial", size=10, color="FF008000")
NOTE_FONT = Font(name="Arial", size=9, color="FF808080")
# Reader-facing cells get a slightly larger, bolder font -- this tab exists specifically to
# be read by someone who doesn't want to squint at a dense 10pt technical grid.
READER_FONT = Font(name="Arial", size=11, color="FF000000")
HELPER_FILL = PatternFill("solid", fgColor="FFF2F2F2")

# Every scored player-role, per real team (current_roster.POSITION_ROLE_LABELS) -- 6 roles,
# fixed and identical for all 32 teams, so every real game has exactly 2x this many = 20 real
# candidate props. Position is part of each slot (not just Role) because QB and RB share the
# literal Role label "Starter" -- see build_player_prop_projections.py's own helper-key
# docstring for the same collision, caught live before it shipped there.
PROP_SLOTS = [
    ("QB", "Starter", "Passing Yards", "yards", "0", False),
    ("RB", "Starter", "Rushing Yards", "yards", "0", False),
    ("WR", "WR1", "Receiving Yards", "yards", "0", False),
    ("WR", "WR1", "Receptions", "receptions", "0.0", True),
    ("WR", "WR2", "Receiving Yards", "yards", "0", False),
    ("WR", "WR2", "Receptions", "receptions", "0.0", True),
    ("WR", "WR3", "Receiving Yards", "yards", "0", False),
    ("WR", "WR3", "Receptions", "receptions", "0.0", True),
    ("TE", "TE1", "Receiving Yards", "yards", "0", False),
    ("TE", "TE1", "Receptions", "receptions", "0.0", True),
]

# The real 20 candidate props for one real game -- PROP_SLOTS (10 roles' worth of stat types)
# for the Away side, then the identical 10 again for the Home side. Built ONCE here (not
# separately for the column list and the per-row formulas) so the two can never drift apart --
# a real bug caught before this shipped: an earlier version derived the column list from
# len(PROP_SLOTS)*2 without actually doubling the slot definitions themselves, silently
# collapsing Away's and Home's props onto the SAME 10 helper-column pairs (Home's QB Passing
# Yards prop would overwrite Away's in the same cell, every row).
ALL_PROP_SLOTS = [("Away", *slot) for slot in PROP_SLOTS] + [("Home", *slot) for slot in PROP_SLOTS]

READER_COLUMNS = [
    "Matchup", "Predicted Score", "Model Lean", "Market Line\n(Spread)",
    "Recommended Play\n(Spread)", "Model Total", "Market Total",
    "Recommended Play\n(Total)", "Moneyline\n(Model)", "Moneyline\n(Market)",
    "Recommended Play\n(Moneyline)", "Confidence", "Top Reason",
    "Top Prop #1", "Top Prop #2", "Top Prop #3",
]
REF_COLUMNS = [
    "Model Home Score\n(ref)", "Model Away Score\n(ref)", "Model Margin\n(ref)",
    "DK Spread\n(Home, ref)", "Model Total\n(ref)", "DK Total\n(ref)",
    "Recommended Spread Play\n(raw, ref)", "Recommended Total Play\n(raw, ref)",
    "Home Moneyline\n(raw, ref)", "Model Win Prob\n(Home, ref)",
    "De-Vigged Prob\n(Home, ref)", "Moneyline Edge\n(Home, ref)",
    "Confidence Tier\n(raw, ref)", "Primary Advantage\n(raw, ref)",
]
# Two separate contiguous blocks -- all 20 Sentence columns, then all 20 |Edge| columns --
# rather than interleaving Sentence/Edge pairs per slot. An interleaved layout would still be
# mathematically correct here (the two 20-cell "start-to-start" range strings Excel builds
# from the first/last column of each block would each stay offset by the same constant 1
# column as every individual Sentence-Edge pair, so INDEX/MATCH's relative positions would
# still line up) -- verified this by hand before rejecting it anyway, because that
# correctness depends on an invariant a future reader can't see just from the formula text,
# exactly the kind of "looks wrong, is actually right" formula this project avoids
# elsewhere. Two separate blocks make INDEX(sentence_block, MATCH(LARGE(edge_block,k),
# edge_block,0)) obviously correct on inspection instead.
PROP_COLUMNS = [f"Prop {n} Sentence\n(helper)" for n in range(1, len(ALL_PROP_SLOTS) + 1)]
PROP_COLUMNS += [f"Prop {n} |Edge|\n(helper)" for n in range(1, len(ALL_PROP_SLOTS) + 1)]

COLUMNS = (
    ["Week", "Away Team", "Home Team", "Game Key\n(helper)"]
    + READER_COLUMNS + REF_COLUMNS + PROP_COLUMNS
)
COL = {name: i + 1 for i, name in enumerate(COLUMNS)}
LET = {name: get_column_letter(i + 1) for i, name in enumerate(COLUMNS)}


def _section_title(ws, row: int, last_col: int, text: str) -> None:
    ws.merge_cells(start_row=row, start_column=1, end_row=row, end_column=last_col)
    cell = ws.cell(row=row, column=1, value=text)
    cell.font = TITLE_FONT
    cell.fill = TITLE_FILL


def build(workbook_path: str) -> dict:
    wb = openpyxl.load_workbook(workbook_path)

    if SHEET_NAME in wb.sheetnames:
        del wb[SHEET_NAME]
    if PPP_SHEET in wb.sheetnames:
        insert_after = PPP_SHEET
    else:
        insert_after = wb.sheetnames[-1]
    ws = wb.create_sheet(SHEET_NAME, index=wb.sheetnames.index(insert_after) + 1)
    ws.column_dimensions["A"].width = 20.0
    for name in READER_COLUMNS:
        ws.column_dimensions[LET[name]].width = 26.0

    n_reader_cols = 4 + len(READER_COLUMNS)
    ws.merge_cells(f"A1:{get_column_letter(n_reader_cols)}1")
    t = ws.cell(row=1, column=1, value=(
        "Simple Summary Page -- plain-language view of the model's real predictions. Every "
        "number here is a direct reference to a real calculation on Season Matchups, Market "
        "Comparison & Confidence, or Player Prop Projections -- nothing on this tab is "
        "computed independently. See the closing note for the full disclosure."
    ))
    t.font = Font(name="Arial", size=12, bold=True)

    # ---- Real ranges on the source tabs, discovered dynamically (survives any row-count -----
    # shift -- same convention build_market_comparison_confidence.py's own sm_col() uses). ----
    sm = wb[SEASON_SHEET]
    sm_first, sm_last = 3, 3
    while sm.cell(row=sm_last + 1, column=1).value is not None:
        sm_last += 1

    def sm_col(letter: str) -> str:
        return f"'{SEASON_SHEET}'!${letter}${sm_first}:${letter}${sm_last}"

    sm_key_range = sm_col(get_column_letter(110))  # Game Key

    mc = wb[MARKET_SHEET]
    mc_first, mc_last = 4, 4
    while mc.cell(row=mc_last + 1, column=1).value is not None:
        mc_last += 1

    def mc_col(letter: str) -> str:
        return f"'{MARKET_SHEET}'!${letter}${mc_first}:${letter}${mc_last}"

    mc_key_range = mc_col("D")  # Game Key

    ppp = wb[PPP_SHEET]
    ppp_header_row = None
    for r in range(1, ppp.max_row + 1):
        if ppp.cell(row=r, column=1).value == "Player Name":
            ppp_header_row = r
            break
    if ppp_header_row is None:
        raise ValueError(f"Could not find the main header row on '{PPP_SHEET}'.")
    ppp_first = ppp_header_row + 1
    ppp_last = ppp_first
    while ppp.cell(row=ppp_last + 1, column=1).value is not None:
        ppp_last += 1

    def ppp_col(letter: str) -> str:
        return f"'{PPP_SHEET}'!${letter}${ppp_first}:${letter}${ppp_last}"

    ppp_key_range = ppp_col("AA")  # Team|Position|Role|Week

    # Season Matchups schedule, read for row order (Week/Away/Home) -- same 272 real games,
    # same order, as every other consolidation tab in this project.
    schedule = []
    for r in range(sm_first, sm_last + 1):
        schedule.append({
            "Week": sm.cell(row=r, column=1).value,
            "Away Team": sm.cell(row=r, column=3).value,
            "Home Team": sm.cell(row=r, column=4).value,
        })

    header_row = 3
    ws.row_dimensions[header_row].height = 34
    for name in COLUMNS:
        c = ws.cell(row=header_row, column=COL[name], value=name)
        c.font = HEADER_FONT
        c.fill = HEADER_FILL
        c.alignment = HEADER_ALIGN

    def L(name: str, row: int) -> str:
        return f"{LET[name]}{row}"

    first_row = header_row + 1
    for i, rec in enumerate(schedule):
        row = first_row + i
        week = int(rec["Week"])
        away, home = rec["Away Team"], rec["Home Team"]
        game_key = f"{week}|{away}|{home}"

        for name, val in (
            ("Week", week), ("Away Team", away), ("Home Team", home),
            ("Game Key\n(helper)", game_key),
        ):
            cell = ws.cell(row=row, column=COL[name], value=val)
            cell.font = INPUT_FONT
        ws.cell(row=row, column=COL["Week"]).number_format = "0"

        ref = {
            "away": L("Away Team", row), "home": L("Home Team", row),
            "week": L("Week", row), "key": L("Game Key\n(helper)", row),
            "hscore": L("Model Home Score\n(ref)", row),
            "ascore": L("Model Away Score\n(ref)", row),
            "margin": L("Model Margin\n(ref)", row),
            "dk_spread": L("DK Spread\n(Home, ref)", row),
            "mtotal": L("Model Total\n(ref)", row),
            "dk_total": L("DK Total\n(ref)", row),
            "rec_spread_raw": L("Recommended Spread Play\n(raw, ref)", row),
            "rec_total_raw": L("Recommended Total Play\n(raw, ref)", row),
            "home_ml_raw": L("Home Moneyline\n(raw, ref)", row),
            "model_wp": L("Model Win Prob\n(Home, ref)", row),
            "devig_wp": L("De-Vigged Prob\n(Home, ref)", row),
            "ml_edge": L("Moneyline Edge\n(Home, ref)", row),
            "conf_raw": L("Confidence Tier\n(raw, ref)", row),
            "primary_raw": L("Primary Advantage\n(raw, ref)", row),
        }

        # ==== Internal reference columns (real INDEX/MATCH pulls, one per source number) ====
        ref_defs = [
            ("Model Home Score\n(ref)", sm_col(get_column_letter(26)), sm_key_range, ref["key"]),
            ("Model Away Score\n(ref)", sm_col(get_column_letter(27)), sm_key_range, ref["key"]),
            ("Model Margin\n(ref)", sm_col(get_column_letter(29)), sm_key_range, ref["key"]),
            ("DK Spread\n(Home, ref)", sm_col(get_column_letter(30)), sm_key_range, ref["key"]),
            ("Model Total\n(ref)", sm_col(get_column_letter(28)), sm_key_range, ref["key"]),
            ("DK Total\n(ref)", sm_col(get_column_letter(31)), sm_key_range, ref["key"]),
            ("Recommended Spread Play\n(raw, ref)", sm_col(get_column_letter(35)), sm_key_range,
             ref["key"]),
            ("Recommended Total Play\n(raw, ref)", sm_col(get_column_letter(36)), sm_key_range,
             ref["key"]),
            ("Home Moneyline\n(raw, ref)", sm_col(get_column_letter(111)), sm_key_range,
             ref["key"]),
            ("Model Win Prob\n(Home, ref)", mc_col("M"), mc_key_range, ref["key"]),
            ("De-Vigged Prob\n(Home, ref)", mc_col("BF"), mc_key_range, ref["key"]),
            ("Moneyline Edge\n(Home, ref)", mc_col("BH"), mc_key_range, ref["key"]),
            ("Confidence Tier\n(raw, ref)", mc_col("U"), mc_key_range, ref["key"]),
            ("Primary Advantage\n(raw, ref)", mc_col("AW"), mc_key_range, ref["key"]),
        ]
        for name, value_range, key_range, key_cell in ref_defs:
            is_cross_sheet = value_range.startswith("'")
            cell = ws.cell(row=row, column=COL[name], value=(
                f'=IFERROR(INDEX({value_range},MATCH({key_cell},{key_range},0)),"")'
            ))
            cell.font = LINK_FONT if is_cross_sheet else FORMULA_FONT

        # ==== Reader-facing plain-language columns ==========================================
        matchup = ws.cell(
            row=row, column=COL["Matchup"], value=f'={ref["away"]}&" @ "&{ref["home"]}'
        )

        home_wins_text = (
            f'{ref["home"]}&" "&ROUND({ref["hscore"]},0)&", "&{ref["away"]}&" "&'
            f'ROUND({ref["ascore"]},0)'
        )
        away_wins_text = (
            f'{ref["away"]}&" "&ROUND({ref["ascore"]},0)&", "&{ref["home"]}&" "&'
            f'ROUND({ref["hscore"]},0)'
        )
        score = ws.cell(row=row, column=COL["Predicted Score"], value=(
            f'=IF(OR({ref["hscore"]}="",{ref["ascore"]}=""),"",'
            f'IF({ref["hscore"]}>={ref["ascore"]},{home_wins_text},{away_wins_text}))'
        ))

        lean = ws.cell(row=row, column=COL["Model Lean"], value=(
            f'=IF({ref["margin"]}="","",IF({ref["margin"]}=0,"Even matchup -- no lean",'
            f'"Model favors "&IF({ref["margin"]}>0,{ref["home"]},{ref["away"]})&" by "&'
            f'TEXT(ABS({ref["margin"]}),"0.0")))'
        ))

        market_line = ws.cell(row=row, column=COL["Market Line\n(Spread)"], value=(
            f'=IF({ref["dk_spread"]}="","","DraftKings has "&{ref["home"]}&" "&'
            f'TEXT({ref["dk_spread"]},"+0.0;-0.0"))'
        ))

        rec_spread = ws.cell(row=row, column=COL["Recommended Play\n(Spread)"], value=(
            f'=IF({ref["rec_spread_raw"]}="","",IF({ref["rec_spread_raw"]}="No Edge","Pass",'
            f'"Lean "&IF({ref["rec_spread_raw"]}="Home",{ref["home"]},{ref["away"]})))'
        ))

        model_total = ws.cell(row=row, column=COL["Model Total"], value=(
            f'=IF({ref["mtotal"]}="","","Model projects "&TEXT({ref["mtotal"]},"0.0")&'
            f'" total points")'
        ))

        market_total = ws.cell(row=row, column=COL["Market Total"], value=(
            f'=IF({ref["dk_total"]}="","","DraftKings has the total at "&'
            f'TEXT({ref["dk_total"]},"0.0"))'
        ))

        rec_total = ws.cell(row=row, column=COL["Recommended Play\n(Total)"], value=(
            f'=IF({ref["rec_total_raw"]}="","",IF({ref["rec_total_raw"]}="No Edge","Pass",'
            f'"Lean "&{ref["rec_total_raw"]}))'
        ))

        ml_model = ws.cell(row=row, column=COL["Moneyline\n(Model)"], value=(
            f'=IF({ref["model_wp"]}="","","Model gives "&{ref["home"]}&" a "&'
            f'TEXT({ref["model_wp"]},"0%")&" chance to win")'
        ))

        ml_market = ws.cell(row=row, column=COL["Moneyline\n(Market)"], value=(
            f'=IF({ref["home_ml_raw"]}="","Moneyline not yet entered for this game",'
            f'IF({ref["devig_wp"]}="","","DraftKings\' moneyline implies "&'
            f'TEXT({ref["devig_wp"]},"0%")&" (after removing the vig)"))'
        ))

        rec_ml = ws.cell(row=row, column=COL["Recommended Play\n(Moneyline)"], value=(
            f'=IF({ref["ml_edge"]}="","Pass",IF({ref["ml_edge"]}>=0,"Lean "&{ref["home"]},'
            f'"Lean "&{ref["away"]}))'
        ))

        confidence = ws.cell(row=row, column=COL["Confidence"], value=(
            f'=IF({ref["conf_raw"]}="","",{ref["conf_raw"]}&" Confidence")'
        ))

        top_reason = ws.cell(row=row, column=COL["Top Reason"], value=(
            f'=IF({ref["primary_raw"]}="","No standout factor this week",'
            f'"Biggest factor: "&{ref["primary_raw"]})'
        ))

        for cell in (matchup, score, lean, market_line, rec_spread, model_total, market_total,
                     rec_total, ml_model, ml_market, rec_ml, confidence, top_reason):
            cell.font = READER_FONT
            cell.alignment = Alignment(wrap_text=True, vertical="top")

        # ==== Prop slot helpers (20 slots x 2 columns) =======================================
        slot_edge_letters = []
        slot_sentence_letters = []
        for slot_i, (side, position, role, label, unit, fmt, use_rec) in enumerate(
            ALL_PROP_SLOTS, start=1
        ):
            side_team = ref["away"] if side == "Away" else ref["home"]
            key_expr = f'{side_team}&"|{position}|{role}|"&{ref["week"]}'
            edge_letter = "Y" if use_rec else "V"
            line_letter = "X" if use_rec else "U"
            proj_letter = "T" if use_rec else "S"
            match_expr = f"MATCH({key_expr},{ppp_key_range},0)"
            edge_expr = f"INDEX({ppp_col(edge_letter)},{match_expr})"
            name_expr = f"INDEX({ppp_col('A')},{match_expr})"
            line_expr = f"INDEX({ppp_col(line_letter)},{match_expr})"
            proj_expr = f"INDEX({ppp_col(proj_letter)},{match_expr})"

            sent_col = f"Prop {slot_i} Sentence\n(helper)"
            edgecol_col = f"Prop {slot_i} |Edge|\n(helper)"

            sent_cell = ws.cell(row=row, column=COL[sent_col], value=(
                f'=IFERROR(IF({edge_expr}="","",{name_expr}&" "&IF({edge_expr}>=0,"Over",'
                f'"Under")&" "&{line_expr}&" {label} (Model: "&TEXT({proj_expr},"{fmt}")&'
                f'" {unit}, "&IF({edge_expr}>=0,"+","")&TEXT({edge_expr},"0.0")&" edge)"),"")'
            ))
            edge_cell = ws.cell(row=row, column=COL[edgecol_col], value=(
                f'=IFERROR(ABS({edge_expr}),"")'
            ))
            sent_cell.font = NOTE_FONT
            edge_cell.font = NOTE_FONT
            sent_cell.fill = HELPER_FILL
            edge_cell.fill = HELPER_FILL
            slot_edge_letters.append(LET[edgecol_col])
            slot_sentence_letters.append(LET[sent_col])

        edge_range_span = f"{slot_edge_letters[0]}{row}:{slot_edge_letters[-1]}{row}"
        sent_range_span = f"{slot_sentence_letters[0]}{row}:{slot_sentence_letters[-1]}{row}"
        # LARGE()/MATCH() over a real, already-materialized plain range on THIS row (never a
        # computed array expression) -- the exact CSE-avoidance discipline WR-TE Value Index's
        # own Corps Quality LARGE() calculation and the Explosive Play Matchup Explanation
        # Engine's Primary/Secondary Advantage columns already established in this project.
        for k in (1, 2, 3):
            prop_cell = ws.cell(row=row, column=COL[f"Top Prop #{k}"], value=(
                f'=IFERROR(INDEX({sent_range_span},MATCH(LARGE({edge_range_span},{k}),'
                f'{edge_range_span},0)),"No player prop lines entered yet for this game")'
            ))
            prop_cell.font = READER_FONT
            prop_cell.alignment = Alignment(wrap_text=True, vertical="top")

    last_row = first_row + len(schedule) - 1

    note_row = last_row + 2
    ws.merge_cells(start_row=note_row, start_column=1, end_row=note_row, end_column=16)
    note = ws.cell(row=note_row, column=1, value=(
        "Pure presentation tab -- zero new computation. Predicted Score/Model Lean/Market "
        "Line/Model Total/Market Total reference Season Matchups' own Model Home/Away "
        "Score, Model Margin, DraftKings Spread/Total (cols Z/AA/AC/AD/AB/AE). Recommended "
        "Play (Spread/Total) reference Season Matchups' own DK Recommended Spread/Total "
        "Play (cols AI/AJ) -- \"No Edge\" is always shown as \"Pass\", never the raw label. "
        "Moneyline (Model) references Market Comparison & Confidence's own real Model Win "
        "Probability (col M, always computable from the real Model Margin, independent of "
        "whether a market moneyline has been entered); Moneyline (Market) and Recommended "
        "Play (Moneyline) reference its own real De-Vigged Probability and Moneyline Edge "
        "(cols BF/BH) and correctly show as \"not yet entered\"/\"Pass\" -- never a "
        "fabricated percentage -- when no real moneyline exists for that game yet. "
        "Confidence references its own real Confidence Tier (col U); Top Reason references "
        "its own real Primary Advantage (col AW, the Explanation Engine's own #1-ranked "
        "factor). Top 3 Player Props reference Player Prop Projections' own real Projected "
        "Yards/Receptions, Sportsbook Line, and Edge columns for that game's exactly 20 "
        "real candidate props (every team has exactly 6 scored roles: QB Starter, RB "
        "Starter, WR1-3, TE1), ranked by real |Edge| via LARGE()/MATCH() over materialized "
        "helper cells on each row -- never a computed array expression. No Z-scores, no "
        "decay weights, no Model Assumptions references anywhere on this tab."
    ))
    note.font = NOTE_FONT
    note.alignment = Alignment(wrap_text=True, vertical="top")

    wb.save(workbook_path)
    print(f"Built '{SHEET_NAME}': {len(schedule)} real games, {len(PROP_SLOTS) * 2} real "
          "candidate props per game.")
    print(f"Saved to {workbook_path}")
    return {"main_range": (first_row, last_row), "n_games": len(schedule)}


if __name__ == "__main__":
    if len(sys.argv) != 2:
        print('Usage: uv run python scripts/build_simple_summary_page.py "path/to/workbook.xlsx"')
        sys.exit(1)
    build(sys.argv[1])
