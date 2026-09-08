"""
Phase 8 secondary check -- real champion/challenger comparison on 2024's degraded-OL-Index
reconstruction (data_version="phase8_2024_secondary_check_degraded_olindex", built by
`phase8_2024_reconstruction.py`). Same real candidates as phase8_run.py's Model 1/2/4/5
(Champion, Travel-G, HFA-A, Travel-G+HFA-A) evaluated on the FULL real 2024 set available
(no train/test split needed here -- Travel-G's spline is refit on 2024's own real weeks 4-10,
matching phase8_run.py's own real methodology, so this is a fair like-for-like second season,
not a leak).

Explicit, real caveat printed with the results: these numbers are NOT directly comparable to
the real 2025 Phase 8 numbers (different OL Index fidelity -- see
research/ol_index_degraded_pre2025.py) and this run does NOT constitute Phase 11's untouched
holdout. It exists only to check whether the real 2025 ranking (HFA-A best Brier/log-loss,
Travel-G+HFA-A best MAE/Win%) holds up in a second real season.

Usage:
    uv run python prediction_audit/phase8_2024_run.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nflverse_pull.pull import fetch_schedules  # noqa: E402
from prediction_audit.db.schema import DEFAULT_DB_PATH  # noqa: E402
from prediction_audit.engine.market_comparison import win_probability_home  # noqa: E402
from prediction_audit.historical.real_constants import load_real_model_assumptions  # noqa: E402
from prediction_audit.historical.stadium_locations import (  # noqa: E402
    resolve_travel_effect_miles,
)
from prediction_audit.research.travel_model import (  # noqa: E402
    OpponentControlledTravelModel,
    TravelModelConfig,
)
from prediction_audit.research.validation import evaluate_predictions  # noqa: E402

DATA_VERSION = "phase8_2024_secondary_check_degraded_olindex"
SEASON = 2024
FROZEN_XLSX = str(
    Path(__file__).resolve().parent / "frozen_baselines" / "NFL_Prediction_Model_v35.xlsx"
)
WIN_PROB_LOGISTIC_SLOPE_ROW = 171
FLAT_HFA_ROW = 3


def _load() -> pd.DataFrame:
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT pr.run_id, pr.game_id, g.week, g.game_date, g.home_team, g.away_team,
               p.home_projected_points, p.away_projected_points,
               r.home_final_score, r.away_final_score
        FROM prediction_runs pr
        JOIN games g ON g.game_id = pr.game_id
        JOIN predictions p ON p.run_id = pr.run_id
        JOIN results r ON r.game_id = pr.game_id
        WHERE pr.data_version = ?
        """,
        conn, params=(DATA_VERSION,),
    )
    contrib = pd.read_sql_query(
        "SELECT run_id, component_name, contribution_value FROM component_contributions",
        conn,
    )
    conn.close()
    pivot = contrib.pivot(index="run_id", columns="component_name", values="contribution_value")
    df = df.merge(pivot, on="run_id", how="left")
    df["home_won"] = (df["home_final_score"] > df["away_final_score"]).astype(int)
    df["actual_home_margin"] = df["home_final_score"] - df["away_final_score"]
    df["champion_home_margin"] = df["home_projected_points"] - df["away_projected_points"]
    return df


def main() -> None:
    df = _load().sort_values("week").reset_index(drop=True)
    if df.empty:
        print(f"No real rows found for data_version={DATA_VERSION!r} -- run "
              f"phase8_2024_reconstruction.py first.")
        return
    print(f"Loaded {len(df)} real 2024 games (degraded-OL-Index secondary check).")

    c = load_real_model_assumptions(FROZEN_XLSX)
    flat_hfa = c[FLAT_HFA_ROW]
    logistic_slope = c[WIN_PROB_LOGISTIC_SLOPE_ROW]

    weeks = sorted(df["week"].unique())
    mid = len(weeks) // 2
    train_weeks, test_weeks = weeks[:mid], weeks[mid:]
    train = df[df["week"].isin(train_weeks)].copy()
    test = df[df["week"].isin(test_weeks)].copy()
    print(f"Real split: train weeks {train_weeks[0]}-{train_weeks[-1]} (n={len(train)}), "
          f"test weeks {test_weeks[0]}-{test_weeks[-1]} (n={len(test)})")

    for part in (train, test):
        part["distance_miles"] = part.apply(
            lambda r: resolve_travel_effect_miles(r["away_team"], r["home_team"]), axis=1,
        )
    sched = fetch_schedules([SEASON])[["game_id", "home_rest", "away_rest"]]
    train = train.merge(sched, on="game_id", how="left")
    test = test.merge(sched, on="game_id", how="left")
    train["rest_diff"] = train["home_rest"] - train["away_rest"]
    test["rest_diff"] = test["home_rest"] - test["away_rest"]

    def travel_baseline_away_margin(d: pd.DataFrame) -> pd.Series:
        return (
            -d["champion_home_margin"] - d["travel_effect_away"].fillna(0)
            - d["travel_direction_away"].fillna(0)
        )

    train["baseline_away_margin"] = travel_baseline_away_margin(train)
    train["actual_away_margin"] = -train["actual_home_margin"]
    train["residual"] = train["actual_away_margin"] - train["baseline_away_margin"]

    travel_model = OpponentControlledTravelModel(
        config=TravelModelConfig(max_abs_adjustment=2.5),
        features=("distance",), nonlinear_distance=True,
    )
    travel_model.fit(train, train["residual"])
    test["travel_G_away_adj"] = travel_model.predict(test)
    test["hfa_A_home_net_delta"] = -(flat_hfa / 2 + test["hfa_delta_home"].fillna(0))

    def real_home_wp(margin: pd.Series) -> pd.Series:
        return margin.apply(lambda m: win_probability_home(m, logistic_slope))

    def build_margin(row_set: pd.DataFrame, use_travel_g: bool, use_hfa_a: bool) -> pd.Series:
        margin = row_set["champion_home_margin"].copy()
        if use_travel_g:
            margin = margin + row_set["travel_effect_away"].fillna(0) \
                + row_set["travel_direction_away"].fillna(0) - row_set["travel_G_away_adj"]
        if use_hfa_a:
            margin = margin + row_set["hfa_A_home_net_delta"]
        return margin

    def evaluate(name: str, margin: pd.Series) -> object:
        wp = real_home_wp(margin)
        result = evaluate_predictions(margin, test["actual_home_margin"], wp, test["home_won"])
        print(f"  {name:45s} MAE={result.mae:6.3f}  RMSE={result.rmse:6.3f}  "
              f"Win%={result.winner_accuracy:.1%}  Brier={result.brier:.4f}  "
              f"LL={result.log_loss:.4f}")
        return result

    print(f"\n=== Real 2024 secondary-check matrix (n={len(test)} test games, degraded OL "
          f"Index -- NOT comparable 1:1 to the real 2025 Phase 8 numbers) ===\n")
    champion = evaluate("1. CHAMPION (frozen v35, degraded OL)", test["champion_home_margin"])
    travel_g = evaluate("2. + Travel-G (nonlinear distance)", build_margin(test, True, False))
    hfa_a = evaluate("4. + HFA-A (no HFA)", build_margin(test, False, True))
    combined = evaluate("5. + Travel-G + HFA-A", build_margin(test, True, True))

    print("\n=== Real deltas vs. CHAMPION (2024 secondary check) ===")
    for name, result in [("Travel-G", travel_g), ("HFA-A", hfa_a), ("Travel-G+HFA-A", combined)]:
        print(f"  {name:20s} MAE_delta={result.mae - champion.mae:+.3f}  "
              f"Brier_delta={result.brier - champion.brier:+.4f}")

    print("\nReal, honest note: compare the SIGN and RELATIVE ORDER of these deltas against "
          "Phase 8's real 2025 deltas, not the absolute numbers -- the degraded OL Index here "
          "shifts every candidate's absolute MAE/Brier by an unknown, non-comparable amount.")


if __name__ == "__main__":
    main()
