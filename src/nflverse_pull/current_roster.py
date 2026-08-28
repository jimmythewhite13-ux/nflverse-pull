"""
Pulls current-season QB/RB depth-chart data to identify each team's actual current
Starter/Backup -- replacing the historical-attempts-ranking proxy that QB Index (and, from
the start, RB Index) otherwise uses, which silently breaks for a trade, a retirement, or a
true rookie with no play-by-play history at all. See claude_code_spec_current_roster_fix.md.

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

POSITIONS = ["QB", "RB"]
DEPTH_ORDERS = [1, 2]  # 1 = Starter, 2 = primary Backup; 3+ not scored downstream

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
    qb_rb = depth_charts[
        depth_charts["pos_abb"].isin(POSITIONS) & depth_charts["pos_rank"].isin(DEPTH_ORDERS)
    ].copy()

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

    `overrides` columns: Team | Manual Starter Override | Manual Backup Override (either
    override column may be blank/NaN per row -- blank means "use the pulled data for that
    role"). A filled-in override name takes precedence over the pulled current-roster
    starter/backup for that team+role. The override is matched against `current_starters`
    first (covers a name already on SOME team's depth chart, just not this slot) and, if not
    found there, is returned with a null Player ID and Source="override (unresolved -- no
    Player ID found)" rather than silently dropped or guessed at; a caller can still use the
    row (e.g. flag it for the user to supply an ID by hand) but it won't feed a
    decay-weighted formula chain without one.
    """
    pos_data = current_starters[current_starters["Position"] == position]
    by_team_role: dict[tuple[str, str], dict] = {}
    for row in pos_data.to_dict("records"):
        role = "Starter" if row["Depth Order"] == 1 else "Backup"
        by_team_role[(row["Team"], role)] = {
            "Player Name": row["Player Name"], "Player ID": row["Player ID"],
            "Source": row["Source"],
        }

    # Build a name -> Player ID lookup from the pulled data, for resolving an override.
    name_to_id = {r["Player Name"]: r["Player ID"] for r in pos_data.to_dict("records")}

    override_cols = [("Starter", "Manual Starter Override"), ("Backup", "Manual Backup Override")]
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
    return out.sort_values(["Team", "Role"], ascending=[True, False]).reset_index(drop=True)


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
