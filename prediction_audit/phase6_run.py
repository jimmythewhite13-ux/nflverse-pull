"""
Phase 6 -- HFA research, real run against Phase 1's persisted 2025 reconstruction.

Critical framing (the phase document's own explicit point, and the reason this phase exists at
all): the original v35 audit's "removing HFA improved accuracy" finding was measured on the
DOUBLE-COUNTED, ~60%-inflated HFA term -- this is the real, first legitimate test of the
correctly-computed term's own contribution.

Real, honest deviation from the phase document (same real constraint as Phases 2/3): only
season-2025 data has a real, complete reconstruction, so the split is real, within-season, not
cross-season.

Usage:
    uv run python prediction_audit/phase6_run.py
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
from prediction_audit.engine.core_formula_simple_terms import (  # noqa: E402
    hfa_delta_home,
)
from prediction_audit.engine.market_comparison import win_probability_home  # noqa: E402
from prediction_audit.engine.team_specific_hfa import TeamSpecificHFAConstants  # noqa: E402
from prediction_audit.historical.real_constants import load_real_model_assumptions  # noqa: E402
from prediction_audit.historical.team_hfa import (  # noqa: E402
    resolve_team_specific_hfa_for_game,
)
from prediction_audit.research.validation import (  # noqa: E402
    challenger_delta,
    evaluate_predictions,
    leakage_check,
)

DATA_VERSION = "phase1_full_season_reconstruction_2025"
SEASON = 2025
FROZEN_XLSX = str(
    Path(__file__).resolve().parent / "frozen_baselines" / "NFL_Prediction_Model_v35.xlsx"
)
WIN_PROB_LOGISTIC_SLOPE_ROW = 171
FLAT_HFA_ROW = 3

# Real, established default -- the same real TeamSpecificHFAConstants every historical
# resolver this session already uses (decay_factor=0.5, regression_weight=0.4,
# last_year_emphasis=0.3), i.e. variant C (existing, corrected).
EXISTING_CONSTANTS = TeamSpecificHFAConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
)
# Variant E: real, heavier weight on the most recent season (last_year_emphasis raised from
# 0.3 to 0.6) than the existing constant already applies.
RECENCY_CONSTANTS = TeamSpecificHFAConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.6,
)
SHRINKAGE_FACTOR = 0.3  # real, additional pull toward the flat/league-average HFA


def _load() -> pd.DataFrame:
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT pr.run_id, pr.game_id, g.week, g.game_date, g.home_team, g.away_team,
               p.away_projected_points, p.home_projected_points,
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
        "SELECT run_id, component_name, contribution_value FROM component_contributions "
        "WHERE component_name IN ('hfa_delta_home', 'hfa_delta_away')",
        conn,
    )
    conn.close()
    pivot = contrib.pivot(index="run_id", columns="component_name", values="contribution_value")
    df = df.merge(pivot, on="run_id", how="left")
    df["home_won"] = (df["home_final_score"] > df["away_final_score"]).astype(int)
    return df


def main() -> None:
    df = _load().sort_values("week").reset_index(drop=True)
    print(f"Loaded {len(df)} real games, data_version={DATA_VERSION!r}.")

    c = load_real_model_assumptions(FROZEN_XLSX)
    flat_hfa = c[FLAT_HFA_ROW]
    logistic_slope = c[WIN_PROB_LOGISTIC_SLOPE_ROW]

    weeks = sorted(df["week"].unique())
    mid = len(weeks) // 2
    train_weeks, test_weeks = weeks[:mid], weeks[mid:]
    test = df[df["week"].isin(test_weeks)].copy()
    train = df[df["week"].isin(train_weeks)]
    print(f"\nReal split: train weeks {train_weeks[0]}-{train_weeks[-1]} (n={len(train)}), "
          f"test weeks {test_weeks[0]}-{test_weeks[-1]} (n={len(test)})")
    ok = leakage_check(train, test, "game_date")
    print(f"Real leakage_check(): {ok}")
    if not ok:
        print("STOP -- real leakage detected.")
        return

    print("\nFetching real 3-prior-season schedule data for the real HFA resolver...")
    sched_3yr = fetch_schedules([SEASON - 3, SEASON - 2, SEASON - 1])
    print("fetched.")

    # Real "baseline_home_margin": champion's own home margin with its own already-applied
    # real hfa_delta_home/away subtracted back out.
    test["baseline_home_margin"] = (
        test["home_projected_points"] - test["away_projected_points"]
        - test["hfa_delta_home"].fillna(0) - test["hfa_delta_away"].fillna(0)
    )
    actual_home_margin = test["home_final_score"] - test["away_final_score"]

    def evaluate_variant(name: str, home_hfa_net: pd.Series) -> None:
        """`home_hfa_net`: the real, TOTAL home-side HFA contribution for this variant
        (flat_hfa/2 + hfa_delta_home, i.e. what a real, single-counted formula would add) --
        subtracts the champion's own flat_hfa/2 baseline component since
        `baseline_home_margin` already includes it."""
        home_margin = test["baseline_home_margin"] + (home_hfa_net - flat_hfa / 2)
        home_win_probability = home_margin.apply(
            lambda m: win_probability_home(m, logistic_slope),
        )
        result = evaluate_predictions(
            home_margin, actual_home_margin, home_win_probability, test["home_won"],
        )
        print(f"  {name:45s} n={result.n:>4}  MAE={result.mae:6.3f}  RMSE={result.rmse:6.3f}  "
              f"winner_acc={result.winner_accuracy:.1%}  Brier={result.brier:.4f}  "
              f"logloss={result.log_loss:.4f}")
        return result

    print("\n=== Real variant results (all 6) ===")
    champion_net = flat_hfa / 2 + test["hfa_delta_home"].fillna(0)
    champion_result = evaluate_variant("CHAMPION (C. Existing Team-Specific HFA, corrected)",
                                        champion_net)
    a_result = evaluate_variant("A. No HFA", pd.Series(0.0, index=test.index))
    b_result = evaluate_variant("B. Flat HFA (pre-fix constant, 1.5)",
                                 pd.Series(flat_hfa / 2, index=test.index))

    def resolve_variant_net(constants: TeamSpecificHFAConstants,
                             shrinkage: float) -> pd.Series:
        nets = []
        for _, row in test.iterrows():
            hfa_result = resolve_team_specific_hfa_for_game(
                sched_3yr, SEASON, row["home_team"], constants,
            )
            delta_home = hfa_delta_home(hfa_result.regressed_hfa, flat_hfa)
            net = flat_hfa / 2 + delta_home
            if shrinkage > 0:
                net = net * (1 - shrinkage) + (flat_hfa / 2) * shrinkage
            nets.append(net)
        return pd.Series(nets, index=test.index)

    d_result = evaluate_variant(
        "D. Shrunk Team-Specific HFA",
        resolve_variant_net(EXISTING_CONSTANTS, shrinkage=SHRINKAGE_FACTOR),
    )
    e_result = evaluate_variant(
        "E. Recency-weighted HFA",
        resolve_variant_net(RECENCY_CONSTANTS, shrinkage=0.0),
    )
    f_result = evaluate_variant(
        "F. Shrinkage + recency combined",
        resolve_variant_net(RECENCY_CONSTANTS, shrinkage=SHRINKAGE_FACTOR),
    )

    print("\n=== Real challenger deltas vs. CHAMPION (C) ===")
    for label, result in [("A", a_result), ("B", b_result), ("D", d_result),
                           ("E", e_result), ("F", f_result)]:
        delta = challenger_delta(champion_result, result)
        verdict = "IMPROVED" if delta.improved else "not improved"
        print(f"  {label}: MAE_delta={delta.mae_delta:+.3f}  "
              f"Brier_delta={delta.brier_delta:+.4f}  -> {verdict}")

    print("\nReal, explicit B vs. C comparison (the actual first legitimate test of the "
          "question the original, double-counted audit finding never answered):")
    bc_delta = challenger_delta(b_result, champion_result)
    bc_verdict = "C IMPROVES on flat" if bc_delta.improved else "C does not clearly improve"
    print(f"  Flat (B) -> Corrected Team-Specific (C): MAE_delta={bc_delta.mae_delta:+.3f}  "
          f"Brier_delta={bc_delta.brier_delta:+.4f}  -> {bc_verdict}")


if __name__ == "__main__":
    main()
