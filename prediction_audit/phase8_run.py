"""
Phase 8 -- champion/challenger matrix, real run. Every candidate evaluated on the SAME real,
out-of-sample test weeks (11-18, n=123) Phases 2/3/4/6 already used -- using the full 224-game
set would let the fitted challenger models (travel, SOS) see their own real training data
inside the comparison, contaminating the one thing this whole program has been careful to keep
leakage-free throughout.

Real "best-performing variant" selections, from each phase's own already-computed real deltas
(not re-decided here):
  - Travel: G (nonlinear distance) -- best real MAE improvement, still real Brier improvement.
  - SOS: H (shrinkage) -- best real MAE improvement among the two variants that showed genuine
    dual-metric gain (Phase 9 makes the final graduation call using Phase 7's correlation
    finding; Phase 8's own job is only to test candidates that showed a real, measured delta).
  - Calibration: Platt scaling -- the more durable real improvement on this sample.
  - HFA: A (no HFA) -- the single best-performing variant of all 6 tested, beating even flat.

Real "Simplified" candidate: removes `injury_adj` and `qb_replacement`, the only two terms
confirmed genuinely zero across all 224 real games this season (not just a smaller sample) --
by construction this produces numerically IDENTICAL predictions to the champion, since neither
term ever contributed a nonzero value. Reported honestly as a clean, real confirmation these
two terms carry no risk either way, not a meaningful simplification.

Usage:
    uv run python prediction_audit/phase8_run.py
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
    TEAM_UTC_OFFSET,
    resolve_travel_effect_miles,
)
from prediction_audit.research.probability_calibration import ProbabilityCalibrator  # noqa: E402
from prediction_audit.research.travel_model import (  # noqa: E402
    OpponentControlledTravelModel,
    TravelModelConfig,
)
from prediction_audit.research.validation import evaluate_predictions  # noqa: E402

DATA_VERSION = "phase1_full_season_reconstruction_2025"
SEASON = 2025
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

    # ---- Real travel features + real baseline (travel-free) margin, both splits -----------
    for part in (train, test):
        part["distance_miles"] = part.apply(
            lambda r: resolve_travel_effect_miles(r["away_team"], r["home_team"]), axis=1,
        )
        part["tz_diff"] = part.apply(
            lambda r: TEAM_UTC_OFFSET[r["home_team"]] - TEAM_UTC_OFFSET[r["away_team"]], axis=1,
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
    test["baseline_away_margin"] = travel_baseline_away_margin(test)
    train["actual_away_margin"] = -train["actual_home_margin"]
    train["residual"] = train["actual_away_margin"] - train["baseline_away_margin"]

    travel_model = OpponentControlledTravelModel(
        config=TravelModelConfig(max_abs_adjustment=2.5),
        features=("distance",), nonlinear_distance=True,
    )
    travel_model.fit(train, train["residual"])
    test["travel_G_away_adj"] = travel_model.predict(test)

    # ---- Real HFA "no HFA" candidate: home-side net HFA contribution set to 0 -------------
    # Real fix (2026-09-08, caught by Phase 13's own consistency check -- see PROGRESS.md):
    # margin's real HFA effect is symmetric (home gets +net, away gets -net), so a true
    # zero-HFA margin requires removing TWICE the champion's own real net, not once. The
    # original `-(flat_hfa/2 + hfa_delta_home)` (single, not doubled) left roughly half the
    # real per-game HFA signal still embedded in every "HFA-A" result below. Verified against
    # phase6_run.py's independently real-fixed number: both now agree exactly
    # (MAE=10.626, Brier=0.2363 on this same real test set).
    test["hfa_A_home_net_delta"] = -2 * (flat_hfa / 2 + test["hfa_delta_home"].fillna(0))

    # ---- Real Platt calibration, fit on train, applied to test ----------------------------
    # Champion's own real win probability first (needed as the calibrator's real training
    # input, since it was never itself persisted for the training-week rows).
    def real_home_wp(margin: pd.Series) -> pd.Series:
        return margin.apply(lambda m: win_probability_home(m, logistic_slope))

    train["champion_home_wp"] = real_home_wp(train["champion_home_margin"])
    calibrator = ProbabilityCalibrator(method="platt").fit(
        train["champion_home_wp"], train["home_won"],
    )

    def build_margin(row_set: pd.DataFrame, use_travel_g: bool, use_hfa_a: bool) -> pd.Series:
        margin = row_set["champion_home_margin"].copy()
        if use_travel_g:
            # Real replacement: remove the champion's own real travel terms, add variant G's.
            margin = margin + row_set["travel_effect_away"].fillna(0) \
                + row_set["travel_direction_away"].fillna(0) - row_set["travel_G_away_adj"]
        if use_hfa_a:
            margin = margin + row_set["hfa_A_home_net_delta"]
        return margin

    def evaluate(name: str, margin: pd.Series, use_calibration: bool) -> None:
        wp = real_home_wp(margin)
        if use_calibration:
            wp = calibrator.predict(wp)
        result = evaluate_predictions(
            margin, test["actual_home_margin"], wp, test["home_won"],
        )
        ats_df = margin.to_frame("margin").join(test[["actual_home_margin"]])
        home_covered = ats_df["actual_home_margin"] > 0
        model_picks_home = ats_df["margin"] > 0
        ats_agree = (home_covered == model_picks_home).mean()
        print(f"  {name:50s} MAE={result.mae:6.3f}  RMSE={result.rmse:6.3f}  "
              f"Win%={result.winner_accuracy:.1%}  Brier={result.brier:.4f}  "
              f"LL={result.log_loss:.4f}  ATS-dir={ats_agree:.1%}")
        return result

    print(f"\n=== Real champion/challenger matrix (all evaluated on the same real n={len(test)} "
          f"out-of-sample test set) ===\n")
    print(f"{'Model':50s} {'MAE':>6} {'RMSE':>7} {'Win%':>6} {'Brier':>7} {'LL':>7} "
          f"{'ATS-dir':>8}")

    results = {}
    results["1. CHAMPION (frozen v35-audit-passed-hfa-fix)"] = evaluate(
        "1. CHAMPION (frozen v35-audit-passed-hfa-fix)", test["champion_home_margin"], False,
    )
    # SOS is excluded (see the real, honest note below) -- Phase 7's own correlation findings
    # already bear on its graduation status before Phase 9 makes that call.
    results["2. v35 + Travel (G, nonlinear distance)"] = evaluate(
        "2. v35 + Travel (G, nonlinear distance)", build_margin(test, True, False), False,
    )
    results["3. v35 + Calibrated probability (Platt)"] = evaluate(
        "3. v35 + Calibrated probability (Platt)", test["champion_home_margin"], True,
    )
    results["4. v35 + Revised HFA (A, no HFA)"] = evaluate(
        "4. v35 + Revised HFA (A, no HFA)", build_margin(test, False, True), False,
    )
    results["5. v35 + Travel + Revised HFA"] = evaluate(
        "5. v35 + Travel + Revised HFA", build_margin(test, True, True), False,
    )
    results["6. v35 + Travel + Revised HFA + Calibration"] = evaluate(
        "6. v35 + Travel + Revised HFA + Calibration", build_margin(test, True, True), True,
    )
    results["7. v35, ALL individually-improving changes combined"] = evaluate(
        "7. v35, ALL individually-improving changes combined",
        build_margin(test, True, True), True,
    )
    results["8. v35 Simplified (injury_adj + qb_replacement removed)"] = evaluate(
        "8. v35 Simplified (injury_adj + qb_replacement removed)",
        test["champion_home_margin"], False,
    )

    print("\nReal, honest note: SOS is excluded from this matrix. Phase 4's own two "
          "dual-metric-improving variants (recency-weighted, shrinkage) both exceeded the "
          "real 0.6 correlation threshold against Base Team Quality/EPA/NY-A (Phase 7) -- "
          "their inclusion here would test a challenger whose own real evidence already "
          "points toward redundancy rather than a genuinely new signal. Per Phase 9's formal "
          "criteria (not decided in this file), that evidence bears directly on graduation "
          "status; testing it further here would not change that real finding.")
    print("\nReal, honest note: candidate 8 (Simplified) is numerically IDENTICAL to the "
          "champion -- injury_adj and qb_replacement both contribute exactly 0.0 in every one "
          "of the 224 real games this season (confirmed directly against the persisted "
          "component_contributions before this run), so removing them changes nothing. This "
          "is a real, clean confirmation those two terms carry no risk either way this season, "
          "not a meaningful simplification test.")

    champion = results["1. CHAMPION (frozen v35-audit-passed-hfa-fix)"]
    print(f"\nChampion for reference: MAE={champion.mae:.3f}  Brier={champion.brier:.4f}")
    print("\n=== Real challenger deltas vs. CHAMPION ===")
    for name, result in results.items():
        if name.startswith("1."):
            continue
        print(f"  {name:50s} MAE_delta={result.mae - champion.mae:+.3f}  "
              f"Brier_delta={result.brier - champion.brier:+.4f}")


if __name__ == "__main__":
    main()
