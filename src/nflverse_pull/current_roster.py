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
