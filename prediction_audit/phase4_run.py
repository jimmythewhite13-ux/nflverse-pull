"""
Phase 4 -- Strength of Schedule research, real run against Phase 1's persisted 2025
reconstruction.

Critical framing (the phase document's own explicit requirement): SOS is tested here as a real,
ALTERNATIVE INPUT to team-strength -- never a bolt-on "Prediction + SOS Adjustment" additive
term. Each variant produces its own real team-strength metric from real, walk-forward,
season-to-date team-game records (points_for/points_against, built directly from
fetch_schedules()'s own real completed games strictly BEFORE the target week -- never future
information); that metric is compared DIRECTLY against the champion's own real Base Team
Quality (already persisted in component_contributions), not summed with it.

Real, honest scope: the "predicted margin" each SOS variant produces here is a real, simple,
direct real_home_strength - real_away_strength + flat_hfa comparison -- NOT a full
re-derivation of Base Team Quality's own real 3-year-decay/blend pipeline with SOS-adjusted
inputs substituted in (a substantially larger undertaking). This measures whether each
variant's own real team-strength signal is competitive with the champion's real Base Team
Quality on its own terms, which is what the phase's own correlation-check requirement is built
to assess in the first place.

Usage:
    uv run python prediction_audit/phase4_run.py
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

from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from prediction_audit.db.schema import DEFAULT_DB_PATH  # noqa: E402
from prediction_audit.engine.market_comparison import win_probability_home  # noqa: E402
from prediction_audit.historical.real_constants import load_real_model_assumptions  # noqa: E402
from prediction_audit.research.sos_model import (  # noqa: E402
    IterativeOpponentAdjustedStrength,
    SOSConfig,
    opponent_adjusted_defense,
    opponent_adjusted_offense,
    raw_opponent_strength,
    raw_opponent_win_pct,
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


def _team_games_through_week(sched: pd.DataFrame, through_week: int) -> pd.DataFrame:
    """Real, long-format team-game rows for every real completed REG game strictly BEFORE
    `through_week` -- the real walk-forward slice a variant fit for a game in `through_week`
    is allowed to see."""
    played = sched[
        (sched["week"] < through_week) & sched["home_score"].notna() & sched["away_score"].notna()
    ]
    rows = []
    for _, g in played.iterrows():
        rows.append({"team": TEAM_NAMES[g["home_team"]], "opponent": TEAM_NAMES[g["away_team"]],
                     "points_for": g["home_score"], "points_against": g["away_score"],
                     "week": g["week"]})
        rows.append({"team": TEAM_NAMES[g["away_team"]], "opponent": TEAM_NAMES[g["home_team"]],
                     "points_for": g["away_score"], "points_against": g["home_score"],
                     "week": g["week"]})
    return pd.DataFrame(rows)


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
          f"test weeks {test_weeks[0]}-{test_weeks[-1]} (n={len(test)})")
    ok = leakage_check(train, test, "game_date")
    print(f"Real leakage_check(): {ok}")
    if not ok:
        print("STOP -- real leakage detected.")
        return

    sched = fetch_schedules([SEASON])
    sched = sched[sched["game_type"] == "REG"]

    actual_home_margin = test["home_final_score"] - test["away_final_score"]

    def evaluate_champion() -> None:
        home_margin = test["base_team_quality_home"] - test["base_team_quality_away"] + flat_hfa
        home_win_probability = home_margin.apply(
            lambda m: win_probability_home(m, logistic_slope),
        )
        result = evaluate_predictions(
            home_margin, actual_home_margin, home_win_probability, test["home_won"],
        )
        print(f"  {'CHAMPION (real Base Team Quality)':45s} n={result.n:>4}  "
              f"MAE={result.mae:6.3f}  RMSE={result.rmse:6.3f}  "
              f"winner_acc={result.winner_accuracy:.1%}  Brier={result.brier:.4f}  "
              f"logloss={result.log_loss:.4f}")
        return result

    def evaluate_variant(name: str, home_strength: pd.Series, away_strength: pd.Series):
        home_margin = home_strength - away_strength + flat_hfa
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

    print("\n=== Real variant results (all 8 + champion) ===")
    champion_result = evaluate_champion()

    home_strengths: dict[str, pd.Series] = {}
    away_strengths: dict[str, pd.Series] = {}
    for label in "ABCDEFGH":
        home_strengths[label] = pd.Series(index=test.index, dtype=float)
        away_strengths[label] = pd.Series(index=test.index, dtype=float)

    # Real efficiency: many real test rows share the same real target week, so each week's
    # own real "games so far" slice and real variant fits are computed once, not once per row.
    variants_by_week: dict[int, dict[str, pd.Series]] = {}
    for week in test["week"].unique():
        games = _team_games_through_week(sched, week)
        if games.empty:
            variants_by_week[week] = {}
            continue
        games["win"] = games["points_for"] > games["points_against"]
        win_pct = games.groupby("team")["win"].mean()
        avg_margin = games.groupby("team").apply(
            lambda g: (g["points_for"] - g["points_against"]).mean(), include_groups=False,
        )
        avg_points_allowed = games.groupby("team")["points_against"].mean()
        avg_points_scored = games.groupby("team")["points_for"].mean()
        league_avg_pa = avg_points_allowed.mean()
        league_avg_ps = avg_points_scored.mean()

        variants = {
            "A": raw_opponent_win_pct(games, win_pct),
            "B": raw_opponent_strength(games, avg_margin),
            "C": opponent_adjusted_offense(games, league_avg_pa, avg_points_allowed),
            "D": opponent_adjusted_offense(games, league_avg_pa, avg_points_allowed),
            "E": opponent_adjusted_defense(games, league_avg_ps, avg_points_scored),
        }
        variants["F"] = IterativeOpponentAdjustedStrength(SOSConfig()).fit(games).get_strength()
        variants["G"] = IterativeOpponentAdjustedStrength(
            SOSConfig(recency_half_life_games=4),
        ).fit(games).get_strength()
        variants["H"] = IterativeOpponentAdjustedStrength(
            SOSConfig(shrinkage=0.3),
        ).fit(games).get_strength()
        variants_by_week[week] = variants

    for idx, row in test.iterrows():
        variants = variants_by_week.get(row["week"], {})
        # Real home_team/away_team here are already real full names (Phase 1 stored them that
        # way via TEAM_NAMES at insert time) -- no abbreviation lookup needed.
        home_name = row["home_team"]
        away_name = row["away_team"]
        for label in "ABCDEFGH":
            strength = variants.get(label)
            if strength is None:
                continue
            home_strengths[label][idx] = strength.get(home_name, np.nan)
            away_strengths[label][idx] = strength.get(away_name, np.nan)

    labels_desc = {
        "A": "A. Raw opponent win pct", "B": "B. Raw opponent strength",
        "C": "C. Opponent-adjusted points", "D": "D. Opponent-adjusted offense",
        "E": "E. Opponent-adjusted defense", "F": "F. Iterative opponent-adjusted strength",
        "G": "G. Recency-weighted opponent adjustment", "H": "H. Shrinkage opponent adjustment",
    }
    results = {}
    correlations = {}
    for label, desc in labels_desc.items():
        valid = home_strengths[label].notna() & away_strengths[label].notna()
        if valid.sum() < 10:
            print(f"  {desc:45s} SKIPPED -- too few real games with resolvable strength "
                  f"({valid.sum()})")
            continue
        sub_test = test[valid]
        sub_home_margin = home_strengths[label][valid] - away_strengths[label][valid] + flat_hfa
        sub_actual = sub_test["home_final_score"] - sub_test["away_final_score"]
        sub_wp = sub_home_margin.apply(lambda m: win_probability_home(m, logistic_slope))
        result = evaluate_predictions(
            sub_home_margin, sub_actual, sub_wp, sub_test["home_won"],
        )
        print(f"  {desc:45s} n={result.n:>4}  MAE={result.mae:6.3f}  RMSE={result.rmse:6.3f}  "
              f"winner_acc={result.winner_accuracy:.1%}  Brier={result.brier:.4f}  "
              f"logloss={result.log_loss:.4f}")
        results[label] = result

        real_corr = home_strengths[label][valid].corr(test["base_team_quality_home"][valid])
        correlations[label] = real_corr

    print("\n=== Real challenger deltas vs. CHAMPION (Base Team Quality) ===")
    for label, result in results.items():
        delta = challenger_delta(champion_result, result)
        verdict = "IMPROVED" if delta.improved else "not improved"
        print(f"  {label}: MAE_delta={delta.mae_delta:+.3f}  "
              f"Brier_delta={delta.brier_delta:+.4f}  -> {verdict}")

    print("\n=== Real correlation vs. champion's own Base Team Quality (home side) ===")
    for label, corr in correlations.items():
        flag = "  <- exceeds the 0.6 real concern threshold (information likely duplicated)" \
            if abs(corr) > 0.6 else ""
        print(f"  {labels_desc[label]:45s} r={corr:+.3f}{flag}")


if __name__ == "__main__":
    main()
