"""
Phase 7 -- double-counting/correlation analysis, real run. No new backtest needed (per the
phase document's own explicit statement) -- reuses Phases 2/4/6's own already-computed real
data plus one additional real data source (team-season EPA/Success Rate/NY-A, via
`compute_team_season_efficiency()`) for the specific SOS correlation checks Phase 4 didn't
originally cover.

Real, honest scope for AGL: BLOCKED, confirmed again in Phase 5 -- no real variant/data exists
to correlate against QB Replacement Value or Availability Index. Documented as N/A, not
fabricated.

Usage:
    uv run python prediction_audit/phase7_run.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nflverse_pull.efficiency import compute_team_season_efficiency, fetch_pbp  # noqa: E402
from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from prediction_audit.db.schema import DEFAULT_DB_PATH  # noqa: E402
from prediction_audit.historical.stadium_locations import (  # noqa: E402
    TEAM_UTC_OFFSET,
    resolve_travel_effect_miles,
)
from prediction_audit.research.sos_model import (  # noqa: E402
    IterativeOpponentAdjustedStrength,
    SOSConfig,
    opponent_adjusted_offense,
    raw_opponent_strength,
    raw_opponent_win_pct,
)

DATA_VERSION = "phase1_full_season_reconstruction_2025"
SEASON = 2025
CONCERN_THRESHOLD = 0.6


def _load_full() -> pd.DataFrame:
    """Real, full 224-game Phase 1 dataset (not the train/test split -- Phase 7 wants the full
    real cross-term view, and correlation itself carries no leakage risk since nothing is
    fit here)."""
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT pr.run_id, pr.game_id, g.week, g.home_team, g.away_team
        FROM prediction_runs pr JOIN games g ON g.game_id = pr.game_id
        WHERE pr.data_version = ?
        """,
        conn, params=(DATA_VERSION,),
    )
    components = [
        "base_team_quality_home", "base_team_quality_away",
        "hfa_delta_home", "hfa_delta_away",
        "phase_matchup_home", "phase_matchup_away",
        "explosive_play_home", "explosive_play_away",
        "travel_effect_away", "travel_direction_away",
    ]
    contrib = pd.read_sql_query(
        f"SELECT run_id, component_name, contribution_value FROM component_contributions "
        f"WHERE component_name IN ({','.join('?' * len(components))})",
        conn, params=components,
    )
    conn.close()
    pivot = contrib.pivot(index="run_id", columns="component_name", values="contribution_value")
    return df.merge(pivot, on="run_id", how="left")


def _team_games_through_week(sched: pd.DataFrame, through_week: int) -> pd.DataFrame:
    played = sched[
        (sched["week"] < through_week) & sched["home_score"].notna() & sched["away_score"].notna()
    ]
    rows = []
    for _, g in played.iterrows():
        rows.append({"team": TEAM_NAMES[g["home_team"]], "opponent": TEAM_NAMES[g["away_team"]],
                     "points_for": g["home_score"], "points_against": g["away_score"]})
        rows.append({"team": TEAM_NAMES[g["away_team"]], "opponent": TEAM_NAMES[g["home_team"]],
                     "points_for": g["away_score"], "points_against": g["home_score"]})
    return pd.DataFrame(rows)


def main() -> None:
    df = _load_full()
    print(f"Loaded {len(df)} real games, data_version={DATA_VERSION!r}.")

    # ---- Travel vs Rest, Travel vs Time Zone -----------------------------------------------
    print("\n=== Real correlation: Travel vs. Rest, Travel vs. Time Zone ===")
    sched2025 = fetch_schedules([SEASON])
    sched2025 = sched2025[sched2025["game_type"] == "REG"][
        ["game_id", "home_rest", "away_rest"]
    ]
    tdf = df.merge(sched2025, on="game_id", how="left")
    tdf["distance_miles"] = tdf.apply(
        lambda r: resolve_travel_effect_miles(r["away_team"], r["home_team"]), axis=1,
    )
    tdf["rest_diff"] = tdf["home_rest"] - tdf["away_rest"]
    tdf["tz_diff"] = tdf.apply(
        lambda r: TEAM_UTC_OFFSET[r["home_team"]] - TEAM_UTC_OFFSET[r["away_team"]], axis=1,
    )
    r_travel_rest = tdf["distance_miles"].corr(tdf["rest_diff"])
    r_travel_tz = tdf["distance_miles"].corr(tdf["tz_diff"])
    print(f"  Travel distance vs. rest differential: r={r_travel_rest:+.3f}"
          f"{'  <- exceeds concern threshold' if abs(r_travel_rest) > CONCERN_THRESHOLD else ''}")
    print(f"  Travel distance vs. time-zone differential: r={r_travel_tz:+.3f}"
          f"{'  <- exceeds concern threshold' if abs(r_travel_tz) > CONCERN_THRESHOLD else ''}")

    # ---- HFA vs Team Quality (corrected, non-double-counted) -------------------------------
    print("\n=== Real correlation: HFA (corrected) vs. Base Team Quality ===")
    r_hfa_tq = df["hfa_delta_home"].corr(df["base_team_quality_home"])
    print(f"  hfa_delta_home vs. base_team_quality_home: r={r_hfa_tq:+.3f}"
          f"{'  <- exceeds concern threshold' if abs(r_hfa_tq) > CONCERN_THRESHOLD else ''}")

    # ---- Matchup vs Explosive Play (recheck on the larger, real 224-game 2025 set) --------
    print("\n=== Real correlation: Phase Matchup vs. Explosive Play (recheck, n=224) ===")
    r_matchup_explosive_home = df["phase_matchup_home"].corr(df["explosive_play_home"])
    r_matchup_explosive_away = df["phase_matchup_away"].corr(df["explosive_play_away"])
    home_flag = "  <- exceeds concern threshold" if abs(r_matchup_explosive_home) > \
        CONCERN_THRESHOLD else ""
    away_flag = "  <- exceeds concern threshold" if abs(r_matchup_explosive_away) > \
        CONCERN_THRESHOLD else ""
    print(f"  Home side: r={r_matchup_explosive_home:+.3f} (original audit found +0.49)"
          f"{home_flag}")
    print(f"  Away side: r={r_matchup_explosive_away:+.3f}{away_flag}")

    # ---- AGL vs QB Replacement Value, AGL vs Availability Index -- BLOCKED ----------------
    print("\n=== AGL vs. QB Replacement Value, AGL vs. Availability Index ===")
    print("  N/A -- AGL is BLOCKED (Phase 5, reconfirmed): no real Approximate Value data "
          "source exists to build any AGL variant to correlate against. Documented for "
          "whenever real data becomes available, not fabricated now.")

    # ---- SOS vs Base Team Quality, EPA, Success Rate, NY/A (full cross-term view) ---------
    print("\n=== Real correlation: SOS variants vs. Base Team Quality, EPA, Success Rate, "
          "NY/A ===")
    print("Fetching real 2025 pbp for team-season EPA/Success Rate/NY-A...")
    pbp2025 = fetch_pbp([SEASON])
    eff = compute_team_season_efficiency(pbp2025)
    eff2025 = eff[eff["Season"] == SEASON].set_index("Team")

    sched_full = fetch_schedules([SEASON])
    sched_full = sched_full[sched_full["game_type"] == "REG"]

    variants_by_week: dict[int, dict[str, pd.Series]] = {}
    for week in df["week"].unique():
        games = _team_games_through_week(sched_full, week)
        if games.empty:
            variants_by_week[week] = {}
            continue
        games["win"] = games["points_for"] > games["points_against"]
        win_pct = games.groupby("team")["win"].mean()
        avg_margin = games.groupby("team").apply(
            lambda g: (g["points_for"] - g["points_against"]).mean(), include_groups=False,
        )
        avg_points_allowed = games.groupby("team")["points_against"].mean()
        league_avg_pa = avg_points_allowed.mean()
        variants = {
            "A": raw_opponent_win_pct(games, win_pct),
            "B": raw_opponent_strength(games, avg_margin),
            "D": opponent_adjusted_offense(games, league_avg_pa, avg_points_allowed),
            "F": IterativeOpponentAdjustedStrength(SOSConfig()).fit(games).get_strength(),
            "G": IterativeOpponentAdjustedStrength(
                SOSConfig(recency_half_life_games=4),
            ).fit(games).get_strength(),
            "H": IterativeOpponentAdjustedStrength(SOSConfig(shrinkage=0.3)).fit(games)
                .get_strength(),
        }
        variants_by_week[week] = variants

    # Real home_team here is already a real full name (Phase 1 stored it that way) -- no
    # abbreviation lookup needed, matching the same fix already made in phase4_run.py.
    sos_home = {label: [] for label in ["A", "B", "D", "F", "G", "H"]}
    for _, row in df.iterrows():
        variants = variants_by_week.get(row["week"], {})
        for label in sos_home:
            strength = variants.get(label)
            sos_home[label].append(
                strength.get(row["home_team"], np.nan) if strength is not None else np.nan,
            )

    # Real home_team is already a real full name (see note above) -- maps directly into
    # eff2025's own real Team-indexed columns, no TEAM_NAMES abbreviation lookup needed.
    real_metrics = {
        "Base Team Quality": df["base_team_quality_home"],
        "EPA/Play (Off)": df["home_team"].map(eff2025["EPA/Play (Off)"]),
        "Success Rate (Off)": df["home_team"].map(eff2025["Success Rate (Off)"]),
        "NY/A (Off)": df["home_team"].map(eff2025["NY/A (Off)"]),
    }
    labels_desc = {
        "A": "Raw opponent win%", "B": "Raw opponent strength",
        "D": "Opponent-adjusted offense", "F": "Iterative opponent-adjusted",
        "G": "Recency-weighted", "H": "Shrinkage",
    }
    for label, desc in labels_desc.items():
        s = pd.Series(sos_home[label], index=df.index)
        print(f"\n  SOS variant {label} ({desc}):")
        for metric_name, metric_series in real_metrics.items():
            r = s.corr(metric_series)
            flag = "  <- exceeds concern threshold" if abs(r) > CONCERN_THRESHOLD else ""
            print(f"    vs. {metric_name:22s} r={r:+.3f}{flag}")

    print("\nReal, explicit methodology note: correlation above is diagnostic only -- a high "
          "correlation is combined with each term's own real incremental contribution "
          "(Phases 2-6) before any REJECTED status is finalized, in Phase 9.")


if __name__ == "__main__":
    main()
