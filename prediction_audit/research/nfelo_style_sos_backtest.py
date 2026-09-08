"""
Real Phase-4-style backtest for the nfelo-style, market-derived SOS proxy (see
`nfelo_style_sos_check.py` for the real correlation screen this follows up on -- low
correlation there was necessary, not sufficient; this is the real out-of-sample test that
was explicitly NOT run in that first pass).

Same real methodology as `phase4_run.py`'s 8 variants, for direct apples-to-apples
comparability: the candidate's own real team-strength signal REPLACES Base Team Quality
entirely (`home_margin = strength_home - strength_away + flat_hfa`), evaluated on the exact
same real out-of-sample test weeks (11-18, n=123) used throughout Phases 2-10 -- not summed
with the champion's own Base Team Quality as a bolt-on adjustment.

Real, structural note this candidate shares with none of Phase 4's 8 variants: the proxy is a
single, FIXED per-team value for the whole season (a real preseason market projection, not
walk-forward-incremental team-performance data), so there is no "games so far" recomputation
per target week -- the same real value applies to every one of a team's games, train or test,
by construction (a preseason line, set once, before Week 1).

Usage:
    uv run python prediction_audit/research/nfelo_style_sos_backtest.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from nflverse_pull.pull import fetch_schedules  # noqa: E402
from prediction_audit.db.schema import DEFAULT_DB_PATH  # noqa: E402
from prediction_audit.engine.market_comparison import win_probability_home  # noqa: E402
from prediction_audit.historical.real_constants import load_real_model_assumptions  # noqa: E402
from prediction_audit.research.nfelo_style_sos_check import (  # noqa: E402
    compute_sos_proxy,
    fetch_real_preseason_win_totals,
)
from prediction_audit.research.validation import (  # noqa: E402
    challenger_delta,
    evaluate_predictions,
    leakage_check,
)

DATA_VERSION = "phase1_full_season_reconstruction_2025"
SEASON = 2025
FROZEN_XLSX = str(
    Path(__file__).resolve().parent.parent / "frozen_baselines" / "NFL_Prediction_Model_v35.xlsx"
)
WIN_PROB_LOGISTIC_SLOPE_ROW = 171
FLAT_HFA_ROW = 3


def _load_champion() -> pd.DataFrame:
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT pr.run_id, pr.game_id, g.week, g.game_date, g.home_team, g.away_team,
               r.home_final_score, r.away_final_score
        FROM prediction_runs pr
        JOIN games g ON g.game_id = pr.game_id
        JOIN results r ON r.game_id = pr.game_id
        WHERE pr.data_version = ?
        """,
        conn, params=(DATA_VERSION,),
    )
    contrib = pd.read_sql_query(
        "SELECT run_id, component_name, contribution_value FROM component_contributions "
        "WHERE component_name IN ('base_team_quality_home', 'base_team_quality_away')",
        conn,
    )
    conn.close()
    pivot = contrib.pivot(index="run_id", columns="component_name", values="contribution_value")
    df = df.merge(pivot, on="run_id", how="left")
    df["home_won"] = (df["home_final_score"] > df["away_final_score"]).astype(int)
    return df


def main() -> None:
    df = _load_champion().sort_values("week").reset_index(drop=True)
    print(f"Loaded {len(df)} real games, data_version={DATA_VERSION!r}.")

    c = load_real_model_assumptions(FROZEN_XLSX)
    flat_hfa = c[FLAT_HFA_ROW]
    logistic_slope = c[WIN_PROB_LOGISTIC_SLOPE_ROW]

    weeks = sorted(df["week"].unique())
    mid = len(weeks) // 2
    train_weeks, test_weeks = weeks[:mid], weeks[mid:]
    train = df[df["week"].isin(train_weeks)]
    test = df[df["week"].isin(test_weeks)].copy()
    print(f"\nReal split: train weeks {train_weeks[0]}-{train_weeks[-1]} (n={len(train)}), "
          f"test weeks {test_weeks[0]}-{test_weeks[-1]} (n={len(test)})  "
          f"-- same real test set used throughout Phases 2-10.")
    ok = leakage_check(train, test, "game_date")
    print(f"Real leakage_check(): {ok}")
    if not ok:
        print("STOP -- real leakage detected.")
        return

    print("\nFetching real 2025-09-01 preseason win-total lines (reproducible)...")
    win_totals = fetch_real_preseason_win_totals()
    sched = fetch_schedules([SEASON])
    sos_proxy = compute_sos_proxy(win_totals, sched)
    print(f"  Real SOS proxy resolved for {len(sos_proxy)} teams (fixed per-team, whole season).")

    actual_home_margin = test["home_final_score"] - test["away_final_score"]

    def evaluate(name: str, home_margin: pd.Series) -> object:
        home_win_probability = home_margin.apply(
            lambda m: win_probability_home(m, logistic_slope),
        )
        result = evaluate_predictions(
            home_margin, actual_home_margin, home_win_probability, test["home_won"],
        )
        print(f"  {name:50s} n={result.n:>4}  MAE={result.mae:6.3f}  RMSE={result.rmse:6.3f}  "
              f"winner_acc={result.winner_accuracy:.1%}  Brier={result.brier:.4f}  "
              f"logloss={result.log_loss:.4f}")
        return result

    print("\n=== Real backtest: nfelo-style SOS proxy vs. CHAMPION (Base Team Quality), "
          "same real test set as Phase 4's 8 variants ===\n")

    champion_margin = test["base_team_quality_home"] - test["base_team_quality_away"] + flat_hfa
    champion_result = evaluate("CHAMPION (real Base Team Quality)", champion_margin)

    test["sos_proxy_home"] = test["home_team"].map(sos_proxy)
    test["sos_proxy_away"] = test["away_team"].map(sos_proxy)
    valid = test["sos_proxy_home"].notna() & test["sos_proxy_away"].notna()
    print(f"\nReal rows with a resolvable SOS proxy on both sides: {valid.sum()}/{len(test)}")

    proxy_margin = test["sos_proxy_home"] - test["sos_proxy_away"] + flat_hfa
    proxy_result = evaluate(
        "nfelo-style SOS proxy (REPLACES Base Team Quality)", proxy_margin,
    )

    delta = challenger_delta(champion_result, proxy_result)
    verdict = "IMPROVED" if delta.improved else "not improved"
    print("\n=== Real delta vs. CHAMPION ===")
    print(f"  MAE_delta={delta.mae_delta:+.3f}  Brier_delta={delta.brier_delta:+.4f}  "
          f"-> {verdict}")

    print("\nReal, honest methodology note: per Phase 4's own established convention, this "
          "candidate's real team-strength signal REPLACES Base Team Quality entirely -- it is "
          "not summed as a bolt-on adjustment. A real improvement here means the market's own "
          "preseason opinion, alone, competes with (or beats) this project's real, "
          "3-year-decay/blend Base Team Quality pipeline -- a real, informative result either "
          "way, not a claim that combining the two would help (that would be a separate, "
          "further real test).")


if __name__ == "__main__":
    main()
