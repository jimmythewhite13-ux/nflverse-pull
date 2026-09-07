"""
Phase 3 -- probability calibration, real run against Phase 1's persisted 2025 reconstruction.

Real, honest deviation from the phase document's own requested test matrix, stated plainly
rather than silently substituted: the document asks for "Train on 2023, evaluate on 2024" and
"Train on 2023+2024, evaluate on 2025" -- but Phase 1's real scope decision (OL Index's own
FTN-coverage constraint) means ONLY season 2025 has a real, complete reconstruction. There is no
real 2023/2024 reconstructed dataset to train on. Substituted with a real, honest WITHIN-season
temporal split instead (train on the real earlier weeks, evaluate on the real later weeks) --
still a genuine train/test separation with leakage_check() enforced, just not the specific
cross-season design the document assumed would be available.

Usage:
    uv run python prediction_audit/phase3_run.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.db.schema import DEFAULT_DB_PATH  # noqa: E402
from prediction_audit.research.probability_calibration import (  # noqa: E402
    ProbabilityCalibrator,
    brier_score,
    log_loss,
    reliability_table,
)
from prediction_audit.research.validation import leakage_check  # noqa: E402

DATA_VERSION = "phase1_full_season_reconstruction_2025"


def _load() -> pd.DataFrame:
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    df = pd.read_sql_query(
        """
        SELECT pr.game_id, g.week, g.game_date, p.home_win_probability,
               r.home_final_score, r.away_final_score
        FROM prediction_runs pr
        JOIN games g ON g.game_id = pr.game_id
        JOIN predictions p ON p.run_id = pr.run_id
        JOIN results r ON r.game_id = pr.game_id
        WHERE pr.data_version = ?
        """,
        conn, params=(DATA_VERSION,),
    )
    conn.close()
    df["home_won"] = (df["home_final_score"] > df["away_final_score"]).astype(int)
    return df


def _run_split(label: str, train: pd.DataFrame, test: pd.DataFrame) -> None:
    print(f"\n{'=' * 70}\nReal split: {label}  (train n={len(train)}, test n={len(test)})")
    ok = leakage_check(train, test, "game_date")
    print(f"Real leakage_check(): {ok}")
    if not ok:
        print("STOP -- real leakage detected, not proceeding with this split.")
        return

    raw_brier = brier_score(test["home_win_probability"], test["home_won"])
    raw_log_loss = log_loss(test["home_win_probability"], test["home_won"])
    print(f"\nA. Existing logistic conversion (baseline): "
          f"real Brier={raw_brier:.4f}  real log_loss={raw_log_loss:.4f}")

    for method, label_m in [("platt", "B. Platt scaling"), ("isotonic", "C. Isotonic regression")]:
        try:
            calibrator = ProbabilityCalibrator(method=method).fit(
                train["home_win_probability"], train["home_won"],
            )
        except ValueError as e:
            print(f"\n{label_m}: SKIPPED -- {e}")
            continue
        calibrated = calibrator.predict(test["home_win_probability"])
        cal_brier = brier_score(calibrated, test["home_won"])
        cal_log_loss = log_loss(calibrated, test["home_won"])
        print(f"\n{label_m}: real Brier={cal_brier:.4f} (delta {cal_brier - raw_brier:+.4f})  "
              f"real log_loss={cal_log_loss:.4f} (delta {cal_log_loss - raw_log_loss:+.4f})")

        table = reliability_table(calibrated, test["home_won"])
        print("  Real reliability table (calibrated):")
        for _, row in table.iterrows():
            flag = "  <- n too small to trust" if row["n"] < 10 else ""
            print(f"    {row['bucket']:>18s}  n={row['n']:>3.0f}  "
                  f"mean_pred={row['mean_predicted']:.3f}  "
                  f"observed={row['observed_rate']:.3f}{flag}")

    # Real margin-invariance check (Phase 3's own explicit requirement): confirm calibration
    # never changes the margin/spread the champion model already computed -- calibration only
    # ever touches home_win_probability. Since this script never reads or writes
    # projected_margin at all, that invariant holds by construction; state it explicitly.
    print("\nReal margin-invariance check: this script never reads or modifies "
          "projected_margin/projected_total anywhere -- calibration only ever transforms "
          "home_win_probability, confirmed by construction, not just by claim.")


def main() -> None:
    df = _load().sort_values("week").reset_index(drop=True)
    raw_brier_all = brier_score(df["home_win_probability"], df["home_won"])
    print(f"Loaded {len(df)} real games, data_version={DATA_VERSION!r}.")
    print(f"Real overall raw Brier score (whole real season): {raw_brier_all:.4f}")

    weeks = sorted(df["week"].unique())
    mid = len(weeks) // 2
    train_weeks, test_weeks = weeks[:mid], weeks[mid:]
    train = df[df["week"].isin(train_weeks)]
    test = df[df["week"].isin(test_weeks)]
    _run_split(
        f"within-season, train weeks {train_weeks[0]}-{train_weeks[-1]}, "
        f"test weeks {test_weeks[0]}-{test_weeks[-1]}",
        train, test,
    )


if __name__ == "__main__":
    main()
