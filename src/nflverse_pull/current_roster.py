"""
Pulls current-season QB/RB/WR/TE depth-chart data to identify each team's actual current
Starter/Backup (or, for WR/TE, current WR1/WR2/WR3/TE1) -- replacing the historical-
attempts-ranking proxy that QB Index (and, from the start, RB Index) otherwise uses, which
silently breaks for a trade, a retirement, or a true rookie with no play-by-play history at
all. See claude_code_spec_current_roster_fix.md. WR/TE support was added for the WR/TE Value
Index (Phase 2 of the multi-phase roadmap in claude_code_spec_rb_index.md) -- that spec's
own note that WR/TE "isn't a clean binary" is why WR gets THREE scored slots (a 3-WR
personnel group) instead of a Starter/Backup pair, and TE gets one (TE1 only -- a second
scored TE slot is a documented future extension, not built here).

Source and confidence: nflverse's depth_charts feed (nfl_data_py.import_depth_charts) is
used as the primary source -- verified live against the installed package (not assumed):
it carries a `dt` snapshot timestamp per row (this pull's snapshot was dated the same day
it was run), and pos_rank directly encodes depth order. seasonal_rosters was checked as the
documented fallback but wasn't needed -- depth_charts returned rich, current QB/RB data.

IMPORTANT, confirmed by inspecting the actual pulled roster data (not assumed): as of this
writing, 2026 rosters are NOT yet cut to 53 (import_seasonal_rosters([2026]) shows ~88-94
'ACT' players per team, and only 3 total 'CUT' statuses league-wide -- nowhere near a real
cutdown). claude_code_spec_rookie_adp_crosswalk.md explicitly gates its entire build on this
pull being run AFTER final roster cuts. Depth-chart-based Starter/Backup identification
itself is likely still reasonably stable pre-cuts (cuts mostly remove bottom-of-roster
players, not starters), but re-run this pull once cuts are confirmed final before doing
anything in that addendum.

Same fetch/pure-transform split as the rest of nflverse_pull.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES

# Kicker is "PK" (Place Kicker) in nflverse depth-chart data, NOT "K" -- verified live
# against the real 2026 pull before writing this (a bare "K" pos_abb doesn't exist at all;
# "PK" has all 32 teams' PK1 populated). Offensive line positions are "LT"/"LG"/"C"/"RG"/
# "RT" -- each already a distinct, real depth-chart position abbreviation (not a generic
# "OL" grouping the way import_seasonal_rosters uses); verified live that all 32 teams have
# a rank-1 starter at each of the 5 spots.
#
# Front-seven defensive positions ("LDE"/"RDE"/"LDT"/"RDT"/"NT"/"MLB"/"WLB"/"SLB"/"LILB"/
# "RILB") are each real, distinct depth-chart position abbreviations too, but split by real
# SCHEME rather than a clean fixed count the way OL is -- verified live against the real
# 2026 pull (properly deduplicated to each slot's latest snapshot, per compute_
# current_starters' own logic; an earlier un-deduplicated check inflated these into the
# hundreds and was wrong): LDE/RDE are populated for all 32 teams (2 EDGE slots, always).
# The interior line varies 1-3 rank-1 starters per team (20 teams: 1, 11 teams: 2, 1 team:
# 3) depending on whether that team's scheme labels a true nose tackle (NT), two 4-3
# tackles (LDT/RDT), or some mix. Linebacker varies 3-4 rank-1 starters per team (11 teams:
# 3 -- a 4-3's MLB/WLB/SLB; 21 teams: 4 -- a 3-4's WLB/SLB/LILB/RILB). build_defense_
# index.py maps these onto fixed EDGE1/EDGE2, IDL1/IDL2, and LB1/LB2/LB3 slots (a real,
# documented priority order per scheme, not fabrication -- the rare extra real starter a
# 3-4 team's 4th linebacker represents is a documented scope limit, same as WR4+ elsewhere).
# Secondary defensive positions ("LCB"/"RCB"/"NB"/"FS"/"SS") are each real, distinct
# depth-chart abbreviations too -- and much cleaner than the front seven: verified live that
# all 32 teams have exactly one rank-1 starter at each of the 5 spots, always (no scheme-
# variation juggling needed the way interior line/linebacker required).
# Special teams positions ("P"/"KR"/"PR") are each real, distinct depth-chart abbreviations
# too -- verified live that all 32 teams have exactly one rank-1 starter at each of the 3
# spots, always. "P" (punter) never collides with "PK" (kicker) -- they're already distinct
# real abbreviations in nflverse's own depth-chart data.
POSITIONS = [
    "QB", "RB", "WR", "TE", "PK", "LT", "LG", "C", "RG", "RT",
    "LDE", "RDE", "LDT", "RDT", "NT", "MLB", "WLB", "SLB", "LILB", "RILB",
    "LCB", "RCB", "NB", "FS", "SS",
    "P", "KR", "PR",
]

# Each position's scored depth-chart slots, mapped to the Role label used throughout
# Section 3/5/6 downstream. QB/RB keep the existing Starter/Backup binary. WR scores three
# slots (WR1/WR2/WR3 -- a 3-WR personnel group). TE, PK (kicker), the 5 OL spots, and each
# of the 10 front-seven abbreviations score one apiece (a team has at most one rank-1
# starter per real depth-chart label, so there's no Backup concept to score, same reasoning
# as PK). A depth-order beyond what's listed here for a position (e.g. WR4+, or a backup
# lineman/front-seven player) is not scored downstream.
POSITION_ROLE_LABELS: dict[str, dict[int, str]] = {
    "QB": {1: "Starter", 2: "Backup"},
    "RB": {1: "Starter", 2: "Backup"},
    "WR": {1: "WR1", 2: "WR2", 3: "WR3"},
    "PK": {1: "K1"},
    "TE": {1: "TE1"},
    "LT": {1: "LT"},
    "LG": {1: "LG"},
    "C": {1: "C"},
    "RG": {1: "RG"},
    "RT": {1: "RT"},
    # UPDATED per claude_code_spec_defensive_player_index.md: a real 2nd depth-chart slot
    # (verified live against the real 2026 pull before adding this -- see that spec's own
    # per-position coverage counts, e.g. 32/32 real teams list a real 2nd LDE/RDE/WLB/SLB/
    # LCB/RCB/NB/FS, 31/32 for SS, fewer for the scheme-variable interior-line/off-ball-LB
    # slots that don't exist on every real defense to begin with) feeds Defensive Player
    # Index's per-SLOT Replacement Value (EDGE1 vs its own real backup, IDL1 vs its own,
    # etc. -- NOT a single team-wide Starter/Backup pair, since these positions already
    # have 2 real "starters" apiece unlike QB/RB). A team without a real 2nd-string player
    # at a given slot simply has no row for it, same "missing means blank" handling used
    # everywhere else in this project.
    "LDE": {1: "LDE", 2: "LDE2"},
    "RDE": {1: "RDE", 2: "RDE2"},
    "LDT": {1: "LDT", 2: "LDT2"},
    "RDT": {1: "RDT", 2: "RDT2"},
    "NT": {1: "NT", 2: "NT2"},
    "MLB": {1: "MLB", 2: "MLB2"},
    "WLB": {1: "WLB", 2: "WLB2"},
    "SLB": {1: "SLB", 2: "SLB2"},
    "LILB": {1: "LILB", 2: "LILB2"},
    "RILB": {1: "RILB", 2: "RILB2"},
    "LCB": {1: "LCB", 2: "LCB2"},
    "RCB": {1: "RCB", 2: "RCB2"},
    "NB": {1: "NB", 2: "NB2"},
    "FS": {1: "FS", 2: "FS2"},
    "SS": {1: "SS", 2: "SS2"},
    # UPDATED per claude_code_spec_defensive_player_index.md's special-teams expansion:
    # a 2nd real depth-chart slot exists for all three (verified live against the real
    # 2026 depth-chart pull before adding this -- KR/PR commonly list several real
    # candidates per team since return duty is often shared/committee'd, P less so: only
    # 14 of 32 real teams currently roster a real 2nd punter at all). A team without a
    # real 2nd-string player at any of these positions simply has no row for that slot --
    # same "missing means blank, not zero" handling every other Backup/2nd-slot position
    # in this project already uses (e.g. a team with no real 2nd interior lineman).
    "P": {1: "P1", 2: "P2"},
    "KR": {1: "KR1", 2: "KR2"},
    "PR": {1: "PR1", 2: "PR2"},
}

OUTPUT_COLUMNS = ["Team", "Position", "Player Name", "Player ID", "Depth Order", "Source"]


def fetch_depth_charts(years: list[int]) -> pd.DataFrame:
    """Network call -- pulls nflverse depth-chart snapshots for the given season(s)."""
    import nfl_data_py as nfl  # imported lazily so tests don't require it installed

    return nfl.import_depth_charts(years)


def compute_current_starters(depth_charts: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. For each (team, position, depth-order-slot) -- e.g. "ARI's
    QB1 slot" -- keeps only the most recent snapshot (max `dt`). This is deliberately keyed
    by the SLOT, not by player: if a depth-chart competition changed hands between two
    snapshots, this correctly reports whoever holds the slot NOW, rather than whichever
    player happened to sort first. This is also how a trade is picked up correctly (e.g. a
    QB1 slot's most recent occupant reflects a mid-window trade), without needing to track
    player movement explicitly.

    Output: Team | Position | Player Name | Player ID | Depth Order | Source
    """
    qb_rb = depth_charts[depth_charts["pos_abb"].isin(POSITIONS)].copy()
    # Each position has its OWN scored depth-order ceiling (QB/RB stop at 2, WR at 3, TE at
    # 1) -- can't filter with one global depth-order list once positions differ.
    max_depth_order = {pos: max(labels) for pos, labels in POSITION_ROLE_LABELS.items()}
    qb_rb = qb_rb[qb_rb["pos_rank"] <= qb_rb["pos_abb"].map(max_depth_order)]

    idx = qb_rb.groupby(["team", "pos_abb", "pos_rank"])["dt"].idxmax()
    latest = qb_rb.loc[idx].copy()

    unmapped = sorted(set(latest["team"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")

    out = pd.DataFrame({
        "Team": latest["team"].map(TEAM_NAMES),
        "Position": latest["pos_abb"],
        "Player Name": latest["player_name"],
        "Player ID": latest["gsis_id"],
        "Depth Order": latest["pos_rank"].astype(int),
        "Source": "depth_charts",
    })
    out = out.sort_values(["Team", "Position", "Depth Order"]).reset_index(drop=True)
    return out


def resolve_scored_population(
    current_starters: pd.DataFrame,
    overrides: pd.DataFrame,
    position: str,
) -> pd.DataFrame:
    """
    Pure function, no network. Combines Part 1's pulled current-roster data with Part 2's
    manual overrides into the final Team | Role | Player Name | Player ID population to be
    scored in a Section 3/5 -- this is what makes Part 3's "a true rookie still gets a full
    row" possible: current_starters carries a Player ID (gsis_id) for every player
    regardless of whether he has any historical stats, so a true zero-history rookie
    identified here flows straight into the existing Section 3
    IF(COUNTIFS(...)=0, RookieBaseline, ...) formula chain (unchanged -- no new Excel
    formula logic needed) and correctly gets a full row: all three Y-1/Y-2/Y-3 slots
    substituted with the Rookie Baseline, Years of Real History = 0. The formula mechanism
    already exists; this function is what ensures such a player is even a scoring candidate
    in the first place, which the old historical-attempts-only population never could be,
    since it only ever considered players who already had a qualifying historical season.

    `overrides` columns: Team | Manual {Role} Override... -- one override column per real
    Role label this position uses (e.g. "Manual Starter Override"/"Manual Backup Override"
    for QB/RB, "Manual WR1 Override"/"Manual WR2 Override"/"Manual WR3 Override" for WR,
    "Manual LT Override"/.../"Manual RT Override" for OL -- see claude_code_spec_
    consolidated_fixes.md Part 2, which generalized this from the original QB/RB-only
    Starter/Backup pair). Any column may be blank/NaN per row -- blank means "use the pulled
    data for that role". A filled-in override name takes precedence over the pulled
    current-roster player for that team+role. The override is matched against
    `current_starters` first (covers a name already on SOME team's depth chart, just not
    this slot) and, if not found there, is returned with a null Player ID and
    Source="override (unresolved -- no Player ID found)" rather than silently dropped or
    guessed at; a caller can still use the row (e.g. flag it for the user to supply an ID by
    hand) but it won't feed a decay-weighted formula chain without one. A missing override
    column entirely (e.g. an old-format overrides table with fewer roles than this position
    now has) is treated the same as an all-blank column -- no error, no override applied.
    """
    role_labels = POSITION_ROLE_LABELS.get(position)
    if role_labels is None:
        raise ValueError(f"No Role labels defined for position {position!r}")

    pos_data = current_starters[current_starters["Position"] == position]
    by_team_role: dict[tuple[str, str], dict] = {}
    for row in pos_data.to_dict("records"):
        role = role_labels.get(row["Depth Order"])
        if role is None:
            continue  # a depth-order beyond what's scored for this position (e.g. WR4+)
        by_team_role[(row["Team"], role)] = {
            "Player Name": row["Player Name"], "Player ID": row["Player ID"],
            "Source": row["Source"],
        }

    # Build a name -> Player ID lookup from the pulled data, for resolving an override.
    name_to_id = {r["Player Name"]: r["Player ID"] for r in pos_data.to_dict("records")}

    # Generalized to every real Role label this position uses (claude_code_fixes.md Part 2)
    # -- column name is always "Manual {role} Override", so this works unchanged for
    # QB/RB's Starter/Backup pair, WR's WR1/WR2/WR3, TE's TE1, Kicking's K1, and OL's
    # LT/LG/C/RG/RT. A position whose override table hasn't been built yet on its tab simply
    # passes an empty `overrides` DataFrame -- to_dict("records") is then an empty list and
    # this loop is a correct no-op, same behavior as before generalizing.
    override_cols = [(role, f"Manual {role} Override") for role in role_labels.values()]
    for orow in overrides.to_dict("records"):
        team = orow["Team"]
        for role, col in override_cols:
            name = orow.get(col)
            is_blank = name is None or (isinstance(name, float) and pd.isna(name))
            if is_blank or str(name).strip() == "":
                continue
            name = str(name).strip()
            player_id = name_to_id.get(name)
            source = "override" if player_id else "override (unresolved -- no Player ID found)"
            by_team_role[(team, role)] = {
                "Player Name": name, "Player ID": player_id, "Source": source,
            }

    out_rows = [
        {"Team": team, "Role": role, **info} for (team, role), info in by_team_role.items()
    ]
    out = pd.DataFrame(out_rows, columns=["Team", "Role", "Player Name", "Player ID", "Source"])
    # Sort by each role's own depth-order priority (Starter=1/Backup=2 for QB/RB,
    # WR1=1/WR2=2/WR3=3 for WR, ...) rather than alphabetically -- an alphabetical sort would
    # put "Backup" before "Starter" (needing an explicit descending flag, as this used to
    # rely on) and "WR3" before "WR1" (which no explicit flag fixes), so this generalizes
    # correctly to any number of roles instead of only the QB/RB binary.
    role_priority = {name: order for order, name in role_labels.items()}
    out["_priority"] = out["Role"].map(role_priority)
    out = out.sort_values(["Team", "_priority"]).drop(columns="_priority").reset_index(drop=True)
    return out


def fetch_seasonal_rosters(years: list[int]) -> pd.DataFrame:
    """Network call -- nflverse's seasonal roster data, carrying real years_exp/entry_year."""
    import nfl_data_py as nfl  # imported lazily so tests don't require it installed

    return nfl.import_seasonal_rosters(years)


def attach_experience(population: pd.DataFrame, rosters: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Joins a resolve_scored_population() output against real
    roster data (years_exp) by Player ID -- REAL NFL experience, not a fabricated skill
    grade. Built for the Offensive Line Index's individual-level component: there is no
    honest free per-lineman performance grade (see oline_stats.py's module docstring), but
    a real starter's real experience is a legitimate, well-established football-analytics
    proxy for continuity/communication risk (a true rookie making his first NFL start at
    left tackle is a genuinely different risk profile than a 10-year veteran, independent
    of any grade).

    A player not found in `rosters` (e.g. a very recent practice-squad promotion the
    roster snapshot hasn't caught up to) gets None rather than a guessed value -- "Is
    Rookie" is None (unknown), not False, when experience itself is unknown.

    Output: same columns as `population`, plus Years of NFL Experience | Is Rookie
    """
    rosters = rosters.dropna(subset=["player_id"])
    rosters = rosters[~rosters["player_id"].duplicated(keep="first")]
    exp_lookup = rosters.set_index("player_id")["years_exp"]

    out = population.copy()
    years_exp = out["Player ID"].map(exp_lookup)
    out["Years of NFL Experience"] = years_exp
    out["Is Rookie"] = years_exp.apply(lambda v: bool(v == 0) if pd.notna(v) else None)
    return out


def attach_real_rookie_season(season_stats: pd.DataFrame, rosters: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Fixes claude_code_spec_consolidated_fixes.md Part 1: every
    stats module's own `Is Rookie Season` (qb_stats.py, rb_stats.py, receiving_stats.py,
    kicking_stats.py) is a PROXY -- "the first season this player_id appears with a
    qualifying sample in the years we happened to pull" -- which silently mislabels any
    veteran whose real career started before the pull window as a rookie in his first
    pulled season (confirmed live: Mahomes/Allen/Jackson/Hurts/Lawrence in QB Index,
    Henry/Barkley/Kamara/McCaffrey in RB Value Index, Ertz/Beckham/Diggs/Andrews in WR-TE
    Value Index, Butker/McPherson in Kicking Index -- all real veterans, all contaminating
    each tab's flat Rookie Baseline).

    Real fix: join `season_stats` to nflverse's seasonal rosters (the same real years_exp/
    entry_year source attach_experience() already uses for Offensive Line Index) by
    (Player ID, Season) -- NOT by Player ID alone like attach_experience(), since
    years_exp/entry_year are season-specific and a player's rookie season is a one-time
    real historical fact, not a function of which years we happened to pull. A player's
    real rookie season is definitionally the season real draft/entry data says he entered
    the league (verified live: Mahomes' 2023/2024/2025 rows all carry entry_year=2017;
    Caleb Williams' 2024 row carries entry_year=2024, his 2025 row still entry_year=2024 --
    correctly a sophomore, not a rookie again).

    A (Player ID, Season) with no roster match gets Is Rookie Season = False, not True --
    we cannot positively confirm rookie status without a real match, and defaulting to
    False is the safer failure mode for a Rookie Baseline pool (excludes an unverified
    player-season rather than risk a false positive contaminating the baseline again).

    Output: same columns as `season_stats`, with Is Rookie Season overwritten using real
    per-season entry_year data.
    """
    rosters = rosters.dropna(subset=["player_id", "season"])
    rosters = rosters[~rosters[["player_id", "season"]].duplicated(keep="first")]
    entry_lookup = rosters.set_index(["player_id", "season"])["entry_year"]

    out = season_stats.copy()
    keys = list(zip(out["Player ID"], out["Season"], strict=True))
    entry_years = pd.Series(
        [entry_lookup.get(k) for k in keys], index=out.index, dtype="object"
    )
    out["Is Rookie Season"] = [
        bool(s == e) if pd.notna(e) else False
        for s, e in zip(out["Season"], entry_years, strict=True)
    ]
    return out


def merge_with_historical_fallback(
    current_population: pd.DataFrame, historical_proxy: pd.DataFrame
) -> pd.DataFrame:
    """
    Pure function, no network. Part 4 of claude_code_spec_current_roster_fix.md: "falling
    back to the historical proxy only if no current data or override exists for that team."

    `current_population`: Team | Role | Player Name | Player ID | Source (Part 1/2's output
    from resolve_scored_population -- current-roster pull plus any manual override).
    `historical_proxy`: Team | Role | Player Name | Player ID (the OLD historical-attempts-
    ranking population -- e.g. QB Index's pre-fix "current season's Starters/Backups by
    dropback rank"). For every (Team, Role) present in `historical_proxy` but MISSING from
    `current_population` (the depth-chart pull had no slot for it, and no override filled
    the gap), adds a row sourced from the historical proxy -- tagged so it stays visible
    which path each row took. Never overrides a row current_population already has: current
    data (pulled or overridden) always wins when both exist for the same (Team, Role).
    """
    have = {(r["Team"], r["Role"]) for r in current_population.to_dict("records")}
    fallback_rows = [
        {
            "Team": r["Team"], "Role": r["Role"], "Player Name": r["Player Name"],
            "Player ID": r["Player ID"],
            "Source": "historical-proxy fallback (no current-roster or override data)",
        }
        for r in historical_proxy.to_dict("records")
        if (r["Team"], r["Role"]) not in have
    ]
    if not fallback_rows:
        return current_population.copy()
    combined = pd.concat(
        [current_population, pd.DataFrame(fallback_rows)], ignore_index=True
    )
    return combined.sort_values(["Team", "Role"], ascending=[True, False]).reset_index(drop=True)


def main(years: list[int] | None = None, output_path: str = "current_starters.csv") -> pd.DataFrame:
    years = years or [2026]
    depth_charts = fetch_depth_charts(years)
    out = compute_current_starters(depth_charts)
    out.to_csv(output_path, index=False)
    print(out.head(10))
    print(f"\nSaved {len(out)} rows to {output_path}")
    return out


if __name__ == "__main__":
    import sys

    cli_years = [int(a) for a in sys.argv[1:]] or None
    main(years=cli_years)
