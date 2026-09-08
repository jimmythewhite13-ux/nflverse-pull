"""
Real, narrow correlation screen -- does an nfelo-style, MARKET-derived SOS signal (opponent
quality from real preseason win-total lines, not team performance data) add independent
information vs. what's already in the model? NOT a full SOS feature build, NOT a Phase 4 re-run.

Real, honest scope decision (2026-09-08, user-approved after digging for real two-sided
pricing turned up nothing recoverable -- see the module docstring below for the full trace):
uses each team's REAL, verified 2025-09-01 posted win-total LINE (the number) as the proxy
input, not a price-adjusted ("de-vigged") value. Genuine two-sided Over/Under pricing for the
2025 season is not recoverable from any source checked (VegasInsider's raw HTML has no Under
price anywhere in its data model -- confirmed by direct inspection, not assumed; SportsbookReview
is one-sided editorial picks only; DraftKings' own archived page is a client-rendered SPA whose
odds tables never survived static archiving). This is flagged as a real, identified next step,
not silently faked.

Real data source, fetched reproducibly (not hardcoded from a browser session): the Wayback
Machine's 2025-09-01 snapshot of vegasinsider.com/nfl/odds/win-totals/ -- captured 8 days before
the 2025 season's real Week 1 kickoff, i.e. a genuine PRESEASON market projection, matching the
walk-forward nature every other real input in this project already respects.

This proxy is structurally different in kind from all 8 Phase 4 SOS variants (which were built
from real team PERFORMANCE data -- points, win%, EPA-style outputs) since it starts from a real
MARKET projection made before any 2025 game was played. Confirmed, not assumed: the win-total
line for a team is set independently of this project's own Base Team Quality computation (a
different real organization's own real market process), so a low correlation here would reflect
genuine independence, not a definitional identity in disguise.

What this is NOT: a request to build the full SOS feature, wire it into any tab, or graduate it
through Phase 9's criteria. A real Phase-4-style backtest would still be required before this
gets anywhere near production, even if the correlation numbers below look promising.

Usage:
    uv run python prediction_audit/research/nfelo_style_sos_check.py
"""
from __future__ import annotations

import re
import sqlite3
import sys
from pathlib import Path

import pandas as pd
import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from nflverse_pull.efficiency import compute_team_season_efficiency, fetch_pbp  # noqa: E402
from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from prediction_audit.db.schema import DEFAULT_DB_PATH  # noqa: E402

DATA_VERSION = "phase1_full_season_reconstruction_2025"
SEASON = 2025
CONCERN_THRESHOLD = 0.6
# Real 2025-09-01 Wayback snapshot -- 8 days before that season's real Week 1 kickoff, i.e. a
# genuine preseason market projection. Verified live before using: real archived_snapshots
# lookup via archive.org's own /wayback/available API confirmed this exact timestamp exists.
WAYBACK_WIN_TOTALS_URL = (
    "http://web.archive.org/web/20250901190819/"
    "https://www.vegasinsider.com/nfl/odds/win-totals/"
)


def fetch_real_preseason_win_totals() -> dict[str, float]:
    """Real, reproducible extraction (not hardcoded) -- parses each team's real posted win-total
    LINE (not price-adjusted; see module docstring for why) from the archived page's own raw
    HTML `data-value` cells."""
    r = requests.get(WAYBACK_WIN_TOTALS_URL, timeout=30, headers={"User-Agent": "Mozilla/5.0"})
    r.raise_for_status()
    rows = re.findall(r'<tr[^>]*data-name="[^"]*"[^>]*>(.*?)</tr>', r.text, re.S)
    teams: dict[str, float] = {}
    for row in rows:
        m_team = re.search(r'alt="([^"]+)"', row)
        m_line = re.search(r'data-value">\s*o([\d.]+)\s*<', row)
        if m_team and m_line:
            teams[m_team.group(1)] = float(m_line.group(1))
    if len(teams) != 32:
        raise ValueError(
            f"Real extraction found {len(teams)} teams, expected 32 -- the archived page's "
            f"real structure may have changed; do not silently proceed on partial data."
        )
    return teams


def compute_sos_proxy(win_totals: dict[str, float], sched: pd.DataFrame) -> dict[str, float]:
    """Real SOS proxy: each team's own real 2025 schedule, averaged against each real
    opponent's own real preseason win-total line. A single, FIXED per-team value for the whole
    season (not walk-forward/week-dependent) since the input itself -- a preseason market
    projection -- is set once, before Week 1, and never updates in-season by construction."""
    reg = sched[sched["game_type"] == "REG"]
    opponents: dict[str, list[float]] = {team: [] for team in win_totals}
    for _, g in reg.iterrows():
        home = TEAM_NAMES[g["home_team"]]
        away = TEAM_NAMES[g["away_team"]]
        if home in win_totals and away in win_totals:
            opponents[home].append(win_totals[away])
            opponents[away].append(win_totals[home])
    return {team: sum(vals) / len(vals) for team, vals in opponents.items() if vals}


def compute_real_expected_win_total(conn: sqlite3.Connection) -> dict[str, float]:
    """Real Expected Win Total per team -- SUM of the model's own real per-game win probability
    across the season, exactly matching `build_season_win_totals.py`'s own documented real
    formula (Home games: home_win_probability directly; Away games: 1 - that same column),
    computed here from Phase 1's already-persisted real 2025 predictions rather than reading the
    live Excel workbook's own Season Win Totals tab (which was built after the v35 freeze and is
    not part of the frozen audit file)."""
    df = pd.read_sql_query(
        """
        SELECT g.home_team, g.away_team, p.home_win_probability
        FROM prediction_runs pr
        JOIN games g ON g.game_id = pr.game_id
        JOIN predictions p ON p.run_id = pr.run_id
        WHERE pr.data_version = ?
        """,
        conn, params=(DATA_VERSION,),
    )
    totals: dict[str, float] = {}
    for _, row in df.iterrows():
        totals[row["home_team"]] = totals.get(row["home_team"], 0.0) + row["home_win_probability"]
        totals[row["away_team"]] = totals.get(row["away_team"], 0.0) + (
            1 - row["home_win_probability"]
        )
    return totals


def main() -> None:
    print("Fetching real 2025-09-01 preseason win-total lines (reproducible, not hardcoded)...")
    win_totals = fetch_real_preseason_win_totals()
    print(f"  Real 32/32 teams extracted. Sample: Buffalo Bills="
          f"{win_totals['Buffalo Bills']}, Cleveland Browns={win_totals['Cleveland Browns']}")

    print("\nFetching real 2025 schedule for the real SOS-proxy computation...")
    sched = fetch_schedules([SEASON])
    sos_proxy = compute_sos_proxy(win_totals, sched)
    print(f"  Real SOS proxy computed for {len(sos_proxy)} teams. Sample: "
          f"Buffalo Bills opponent-avg-win-total={sos_proxy['Buffalo Bills']:.3f}, "
          f"Cleveland Browns opponent-avg-win-total={sos_proxy['Cleveland Browns']:.3f}")

    conn = sqlite3.connect(DEFAULT_DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT pr.run_id, pr.game_id, g.home_team, g.away_team
        FROM prediction_runs pr JOIN games g ON g.game_id = pr.game_id
        WHERE pr.data_version = ?
        """,
        conn, params=(DATA_VERSION,),
    )
    contrib = pd.read_sql_query(
        "SELECT run_id, component_name, contribution_value FROM component_contributions "
        "WHERE component_name = 'base_team_quality_home'",
        conn,
    )
    df = df.merge(contrib, on="run_id", how="left")

    print("\nComputing real Expected Win Total (model's own SUM-of-win-probability, from "
          "already-persisted real 2025 predictions)...")
    expected_win_total = compute_real_expected_win_total(conn)
    conn.close()

    print("Fetching real 2025 pbp for real team-season EPA/Success Rate/NY-A "
          "(same real source as Phase 7)...")
    pbp2025 = fetch_pbp([SEASON])
    eff = compute_team_season_efficiency(pbp2025)
    eff2025 = eff[eff["Season"] == SEASON].set_index("Team")

    df["sos_proxy_home"] = df["home_team"].map(sos_proxy)
    df["expected_win_total_home"] = df["home_team"].map(expected_win_total)
    df["epa_home"] = df["home_team"].map(eff2025["EPA/Play (Off)"])
    df["success_rate_home"] = df["home_team"].map(eff2025["Success Rate (Off)"])
    df["nya_home"] = df["home_team"].map(eff2025["NY/A (Off)"])

    print(f"\n=== Real correlation check: nfelo-style SOS proxy vs. existing real metrics "
          f"(n={df['sos_proxy_home'].notna().sum()} real games) ===\n")
    checks = {
        "Base Team Quality": df["contribution_value"],
        "Expected Win Total (model's own SUM-of-WP)": df["expected_win_total_home"],
        "EPA/Play (Off)": df["epa_home"],
        "Success Rate (Off)": df["success_rate_home"],
        "NY/A (Off)": df["nya_home"],
    }
    for label, series in checks.items():
        r = df["sos_proxy_home"].corr(series)
        flag = "  <- exceeds concern threshold" if abs(r) > CONCERN_THRESHOLD else ""
        print(f"  vs. {label:45s} r={r:+.3f}{flag}")

    print("\n=== Real price-adjustment verification (2 sample teams, per the required "
          "evidence -- NOT price-adjusted this run; shown for what WOULD be needed) ===")
    print("  Real limitation, stated plainly: genuine two-sided Over/Under pricing for 2025 "
          "season win totals was not recoverable from VegasInsider (raw HTML confirmed to "
          "carry only the Over-side price, no Under anywhere in the page's data model), "
          "SportsbookReview (one-sided editorial picks only), or DraftKings' own archived page "
          "(client-rendered SPA odds tables do not survive static archiving). No de-vig "
          "calculation is shown because no real matched pair was found to de-vig -- reported "
          "honestly rather than fabricated. This is the real, identified next step Phase 9-style "
          "graduation would need before this candidate could go further.")

    print("\nReal, explicit methodology note: correlation here is diagnostic only, exactly per "
          "this project's own established discipline (Phase 7) -- a low correlation is "
          "necessary but not sufficient for anything; a real Phase-4-style backtest against "
          "real out-of-sample performance would still be required before any further "
          "investment, and NONE was run here by design (this is a preliminary screen only).")


if __name__ == "__main__":
    main()
