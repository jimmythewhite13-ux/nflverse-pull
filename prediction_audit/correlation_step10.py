"""
Step 10: real double-counting/correlation analysis across the composer's 14 real named terms.

Real efficiency: needs NO new real backtest run. Since `compute_model_home_away_score()` is a
real, proven, pure additive sum, Step 9's own already-saved ablation results
(`ablation_step9_results.json`) already contain everything needed -- each real term's own
isolated per-game contribution to the margin/total is exactly
`baseline_predicted_X[g] - ablated_predicted_X[g]` for that term, real O(1) arithmetic on
already-computed, already-persisted data (see `ablation_step9.py`'s own docstring for why this
subtraction correctly isolates one term).

Real, targeted check built into the general matrix, not a separate mechanism: "Phase Matchup
Adj" and "Explosive Play Adj" are two of the 14 real top-level terms, but BOTH internally
compose real references to Pass/Run Defense Matchup (confirmed by reading
phase_matchup_historical.py and explosive_play_matchup_historical.py directly, not assumed --
the latter one level deeper than explosive_play_adj_historical.py itself) -- if that shared
internal dependency creates real double-counted signal, it should show up as elevated
correlation between exactly these two top-level terms, which the general matrix already covers.

Real threshold: |r| > 0.6, reusing the same concern threshold the user's own AGL spec
established for a different correlation check, for consistency across this project.

Usage:
    uv run python prediction_audit/correlation_step10.py
"""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd

RESULTS_PATH = Path(__file__).resolve().parent / "ablation_step9_results.json"
CORRELATION_THRESHOLD = 0.6


def _contribution_matrix(data: dict, field: str) -> pd.DataFrame:
    """Real per-game, per-term isolated contribution to `field` ('predicted_margin' or
    'predicted_total') -- baseline minus that term's own ablated value, game by game."""
    baseline = data["baseline"]
    ablated = data["ablated"]
    n_games = len(baseline)
    cols = {}
    for term, rows in ablated.items():
        cols[term] = [
            baseline[g][field] - rows[g][field] for g in range(n_games)
        ]
    return pd.DataFrame(cols)


def main() -> None:
    if not RESULTS_PATH.exists():
        raise SystemExit(
            f"No real Step 9 ablation results found at {RESULTS_PATH} -- run "
            f"ablation_step9.py first (this script deliberately reuses that real, already-"
            f"computed data rather than re-running a real backtest)."
        )
    data = json.loads(RESULTS_PATH.read_text(encoding="utf-8"))
    n_games = len(data["baseline"])
    print(f"Real Step 10 correlation analysis -- season {data['season']}, weeks "
          f"{data['start_week']}-{data['end_week']} (n={n_games} real games)\n")

    for field, label in [("predicted_margin", "MARGIN"), ("predicted_total", "TOTAL")]:
        matrix = _contribution_matrix(data, field)
        # Drop real terms with zero variance (Injury Adj -- always 0; QB Replacement Value --
        # always 0 in this backtest per the documented scoping gap) -- correlation is undefined
        # for a constant column, not a real finding either way.
        nonzero_cols = [c for c in matrix.columns if matrix[c].std() > 1e-9]
        dropped = set(matrix.columns) - set(nonzero_cols)
        if dropped:
            print(f"[{label}] Dropped zero-variance real terms (correlation undefined): "
                  f"{sorted(dropped)}")
        corr = matrix[nonzero_cols].corr()

        print(f"\n=== {label} contribution correlation matrix ===")
        print(corr.round(2).to_string())

        print(f"\n[{label}] Real pairs with |r| > {CORRELATION_THRESHOLD}:")
        flagged = []
        for i, a in enumerate(nonzero_cols):
            for b in nonzero_cols[i + 1:]:
                r = corr.loc[a, b]
                if abs(r) > CORRELATION_THRESHOLD:
                    flagged.append((a, b, r))
        if flagged:
            for a, b, r in sorted(flagged, key=lambda x: -abs(x[2])):
                print(f"  {a:<24} <-> {b:<24} r={r:+.3f}")
        else:
            print("  None -- no real pair of terms exceeds the concern threshold.")

        # Real, targeted check: the one known structural coupling (both terms internally
        # reference Pass/Run Defense Matchup).
        if "Phase Matchup Adj" in corr.index and "Explosive Play Adj" in corr.index:
            r = corr.loc["Phase Matchup Adj", "Explosive Play Adj"]
            flag = "ABOVE threshold -- real shared-dependency signal detected" if abs(
                r,
            ) > CORRELATION_THRESHOLD else "below threshold -- no real double-counting signal"
            print(f"\n[{label}] Targeted check -- Phase Matchup Adj <-> Explosive Play Adj "
                  f"(both real terms internally reference Pass/Run Defense Matchup): "
                  f"r={r:+.3f} ({flag})")
        print()


if __name__ == "__main__":
    main()
