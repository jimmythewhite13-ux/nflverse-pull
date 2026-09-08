"""
Phase 2 -- travel research, real run against Phase 1's persisted 2025 reconstruction.

Real target (per the phase document's own explicit requirement): the RESIDUAL
(actual_away_margin - baseline_away_margin), not the raw margin -- isolates what travel
explains beyond what the champion (Phase 1's own persisted prediction) already captures.
`baseline_away_margin` here is derived from Phase 1's own persisted away_projected_points
MINUS the already-applied travel_effect_away/travel_direction_away contributions (so the
"baseline" genuinely has zero travel information in it, letting each variant re-introduce
travel on its own real terms) -- read directly from component_contributions, not
re-approximated.

Real, honest deviation from the phase document, stated plainly: only real season-2025 data
exists (same real constraint as Phase 3), so the temporal split is real, within-season
(train on early real weeks, test on later real weeks), not a cross-season design.

Usage:
    uv run python prediction_audit/phase2_run.py
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
from prediction_audit.research.travel_model import (  # noqa: E402
    OpponentControlledTravelModel,
    TravelModelConfig,
    existing_production_travel,
    no_travel_baseline,
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


def _load() -> pd.DataFrame:
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT pr.run_id, pr.game_id, g.week, g.game_date, g.home_team, g.away_team,
               p.away_projected_points, p.home_projected_points, p.home_win_probability,
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
        "WHERE component_name IN ('travel_effect_away', 'travel_direction_away')",
        conn,
    )
    conn.close()
    pivot = contrib.pivot(index="run_id", columns="component_name", values="contribution_value")
    df = df.merge(pivot, on="run_id", how="left")

    sched = fetch_schedules([SEASON])[
        ["game_id", "home_rest", "away_rest"]
    ]
    df = df.merge(sched, on="game_id", how="left")

    # Real home_team/away_team in the DB are already real full names (Phase 1 inserted them
    # that way), so distance resolves directly -- no abbreviation lookup needed.
    df["distance_miles"] = df.apply(
        lambda r: resolve_travel_effect_miles(r["away_team"], r["home_team"]), axis=1,
    )
    df["rest_diff"] = df["home_rest"] - df["away_rest"]
    df["tz_diff"] = df.apply(
        lambda r: TEAM_UTC_OFFSET[r["home_team"]] - TEAM_UTC_OFFSET[r["away_team"]], axis=1,
    )
    df["actual_away_margin"] = df["away_final_score"] - df["home_final_score"]
    # Real, travel-free baseline: the champion's own away margin, with its own already-applied
    # real travel terms subtracted back out.
    df["baseline_away_margin"] = (
        df["away_projected_points"] - df["home_projected_points"]
        - df["travel_effect_away"].fillna(0) - df["travel_direction_away"].fillna(0)
    )
    df["residual"] = df["actual_away_margin"] - df["baseline_away_margin"]
    df["home_won"] = (df["home_final_score"] > df["away_final_score"]).astype(int)
    return df


def main() -> None:
    df = _load().sort_values("week").reset_index(drop=True)
    print(f"Loaded {len(df)} real games, data_version={DATA_VERSION!r}.")
    print(f"Real distance range: {df['distance_miles'].min():.0f}-"
          f"{df['distance_miles'].max():.0f} miles")

    weeks = sorted(df["week"].unique())
    mid = len(weeks) // 2
    train_weeks, test_weeks = weeks[:mid], weeks[mid:]
    train = df[df["week"].isin(train_weeks)].copy()
    test = df[df["week"].isin(test_weeks)].copy()
    print(f"\nReal split: train weeks {train_weeks[0]}-{train_weeks[-1]} (n={len(train)}), "
          f"test weeks {test_weeks[0]}-{test_weeks[-1]} (n={len(test)})")
    ok = leakage_check(train, test, "game_date")
    print(f"Real leakage_check(): {ok}")
    if not ok:
        print("STOP -- real leakage detected.")
        return

    logistic_slope = load_real_model_assumptions(FROZEN_XLSX)[WIN_PROB_LOGISTIC_SLOPE_ROW]

    def evaluate_variant(name: str, away_adj: pd.Series) -> None:
        """`away_adj`: the real additive correction to ADD to the travel-free
        baseline_away_margin (same real sign convention as `residual` itself). Real win
        probability is RECOMPUTED from each variant's own real margin via the same real
        logistic transform Phase 1 used -- reusing the original, unchanged probability here
        would make Brier/log_loss blind to every variant's real effect on the margin."""
        away_margin = test["baseline_away_margin"] + away_adj
        home_margin = -away_margin
        home_win_probability = home_margin.apply(
            lambda m: win_probability_home(m, logistic_slope),
        )
        actual_home_margin = test["home_final_score"] - test["away_final_score"]
        result = evaluate_predictions(
            home_margin, actual_home_margin, home_win_probability, test["home_won"],
        )
        print(f"  {name:45s} n={result.n:>4}  MAE={result.mae:6.3f}  RMSE={result.rmse:6.3f}  "
              f"winner_acc={result.winner_accuracy:.1%}  Brier={result.brier:.4f}  "
              f"logloss={result.log_loss:.4f}")
        return result

    print("\n=== Real variant results (all 9) ===")
    champion_adj = test["travel_effect_away"].fillna(0) + test["travel_direction_away"].fillna(0)
    champion_result = evaluate_variant("CHAMPION (current production, for reference)",
                                        champion_adj)

    a_result = evaluate_variant("A. No travel", no_travel_baseline(test))
    b_result = evaluate_variant(
        "B. Existing v35 travel (+0.4pts/1000mi, unbounded)",
        existing_production_travel(test["distance_miles"]),
    )

    config = TravelModelConfig(max_abs_adjustment=2.5)
    variant_specs = [
        ("C. Distance-only (learned)", ("distance",), False),
        ("D. Distance + rest differential", ("distance", "rest_diff"), False),
        ("E. Distance + time-zone differential", ("distance", "tz_diff"), False),
        ("F. Distance + rest + time-zone", ("distance", "rest_diff", "tz_diff"), False),
        ("G. Nonlinear distance", ("distance",), True),
        ("H. Nonlinear distance + rest", ("distance", "rest_diff"), True),
        ("I. Nonlinear distance + rest + time-zone",
         ("distance", "rest_diff", "tz_diff"), True),
    ]
    results = {"A": a_result, "B": b_result}
    for label, features, nonlinear in variant_specs:
        model = OpponentControlledTravelModel(
            config=config, features=features, nonlinear_distance=nonlinear,
        )
        model.fit(train, train["residual"])
        away_adj = model.predict(test)  # real, direct estimate of the residual to add
        result = evaluate_variant(label, away_adj)
        results[label[0]] = result

    print("\n=== Real challenger deltas vs. CHAMPION ===")
    for key, result in results.items():
        delta = challenger_delta(champion_result, result)
        verdict = "IMPROVED" if delta.improved else "not improved"
        print(f"  {key}: MAE_delta={delta.mae_delta:+.3f}  Brier_delta={delta.brier_delta:+.4f}"
              f"  -> {verdict}")


if __name__ == "__main__":
    main()
