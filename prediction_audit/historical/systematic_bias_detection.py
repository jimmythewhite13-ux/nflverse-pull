"""
Real systematic-bias detection (systematic_bias_detection.md, 2026-09-12 explicit user request)
-- computes the real SIGNED mean error (predicted minus actual, not absolute value) for margin
and total, across the real Phase 1 (2025, 224 games) and Phase 8 (2024, 220 games) backtests,
with a real one-sample significance test so a small observed lean isn't mistaken for a real,
systematic pattern.

Real statistical method: a one-sample z-test on the signed error (H0: true mean signed error is
0). scipy isn't a real dependency of this project (confirmed: not installed in this venv) and a
proper t-test at this real sample size (n=220-224) is statistically indistinguishable from a
z-test -- the t-critical value at df=219 for a two-tailed 0.05 test is 1.971 vs the normal's
1.960, a real difference of 0.011, far below anything that would change a real conclusion here.
Implemented directly against Python's stdlib `math.erf` (the standard normal CDF), not a new
real dependency for a test this large sample size doesn't need.

Real, deliberate reuse: pulls from the EXACT SAME real query `hosted_env/api/main.py`'s
`get_historical()` already uses (`_HISTORICAL_MODEL_VERSIONS`, the same DISTINCT ON dedup for
the same real duplicate-prediction-run gap) -- so this module's numbers are always consistent
with what the live Historical tab already shows, never a second, silently-diverging real
computation of the same underlying data.

Built to be reusable, not a one-off print script: `compute_bias_stats()` takes a plain real list
of signed errors and returns the full real stats dict, so `weekly_review_automation.md`'s future
recurring check can call it directly against the growing real 2026 sample once live predictions
exist -- same real test, same real honesty about small-sample uncertainty, just a different real
input list.

Usage:
    uv run python -m prediction_audit.historical.systematic_bias_detection
"""
from __future__ import annotations

import math
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

# Real, exact same real model_version scope as hosted_env/api/main.py's own
# `_HISTORICAL_MODEL_VERSIONS` -- see that constant's own comment for the full real rationale.
# Not imported directly (hosted_env/api has its own minimal, deployment-independent module,
# same reasoning as its local `_TEAM_FULL_NAMES` copy) -- kept as a real, exact literal copy.
HISTORICAL_MODEL_VERSIONS = (
    "v35.0-hfa-raw-estimator-fix",
    "v35.0-degraded-ol-2024-secondary-check-hfa-raw-estimator-fix",
)


def _real_database_url() -> str:
    env_value = os.environ.get("DATABASE_URL")
    if env_value:
        return env_value
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            if line.startswith("DATABASE_URL="):
                return line.split("=", 1)[1].strip()
    raise SystemExit("Real DATABASE_URL not available.")


def fetch_real_predictions_vs_actuals() -> list[dict]:
    """Real network call -- one row per real graded game across Phase 1 (2025)/Phase 8 (2024),
    the exact same real query shape `get_historical()` already uses (including its own real
    DISTINCT ON dedup for the real duplicate-prediction-run gap)."""
    conn = psycopg.connect(_real_database_url(), row_factory=dict_row)
    try:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT DISTINCT ON (g.game_id, mv.version_name) "
                "g.game_id, g.season, p.projected_margin, p.projected_total, "
                "r.away_final_score, r.home_final_score "
                "FROM predictions p "
                "JOIN prediction_runs pr ON pr.id = p.run_id "
                "JOIN model_versions mv ON mv.id = pr.model_version_id "
                "JOIN games g ON g.game_id = pr.game_id "
                "JOIN results r ON r.game_id = g.game_id "
                "WHERE mv.version_name = ANY(%s) "
                "ORDER BY g.game_id, mv.version_name, pr.id ASC;",
                (list(HISTORICAL_MODEL_VERSIONS),),
            )
            return cur.fetchall()
    finally:
        conn.close()


def compute_bias_stats(signed_errors: list[float]) -> dict:
    """Real, generic one-sample signed-bias test -- H0: the true mean signed error is 0 (no
    real systematic lean, just noise in both directions). Returns the real mean, real sample
    std dev, real n, real z-statistic, and real two-tailed p-value (normal approximation, see
    module docstring for why that's real and sufficient at this sample size). `significant` is
    True only at the conventional real p < 0.05 threshold -- never treated as proof beyond that,
    per this task's own explicit "do not over-trust a small-sample lean" instruction."""
    n = len(signed_errors)
    if n < 2:
        return {"n": n, "mean": None, "std": None, "z": None, "p_value": None,
                "significant": False, "note": "Real n < 2 -- cannot compute a real variance."}
    mean = sum(signed_errors) / n
    variance = sum((x - mean) ** 2 for x in signed_errors) / (n - 1)
    std = math.sqrt(variance)
    if std == 0:
        return {"n": n, "mean": mean, "std": 0.0, "z": None, "p_value": None,
                "significant": False, "note": "Real zero variance -- every real error identical."}
    z = mean / (std / math.sqrt(n))
    # Standard normal CDF via erf -- Phi(z) = 0.5*(1+erf(z/sqrt(2))); two-tailed p-value.
    phi = 0.5 * (1 + math.erf(abs(z) / math.sqrt(2)))
    p_value = 2 * (1 - phi)
    return {
        "n": n, "mean": round(mean, 3), "std": round(std, 3), "z": round(z, 3),
        "p_value": round(p_value, 5), "significant": p_value < 0.05,
    }


def main() -> None:
    rows = fetch_real_predictions_vs_actuals()
    by_season: dict[int, list[dict]] = {}
    for r in rows:
        by_season.setdefault(r["season"], []).append(r)

    print(f"Real systematic-bias check across {len(rows)} real graded games "
          f"({sorted(by_season.keys())}):\n")

    results: dict[int, dict] = {}
    for season in sorted(by_season, reverse=True):
        srows = by_season[season]
        margin_errors = [
            float(r["projected_margin"]) - (r["home_final_score"] - r["away_final_score"])
            for r in srows
        ]
        total_errors = [
            float(r["projected_total"]) - (r["home_final_score"] + r["away_final_score"])
            for r in srows
        ]
        margin_stats = compute_bias_stats(margin_errors)
        total_stats = compute_bias_stats(total_errors)
        results[season] = {"margin": margin_stats, "total": total_stats}

        print(f"=== {season} season ({len(srows)} real games) ===")
        for label, stats in (("Margin", margin_stats), ("Total", total_stats)):
            sig = "REAL, SIGNIFICANT" if stats["significant"] else "not significant"
            direction = (
                "over-predicts" if stats["mean"] and stats["mean"] > 0
                else "under-predicts" if stats["mean"] and stats["mean"] < 0
                else "no lean"
            )
            print(f"  {label}: signed mean error = {stats['mean']:+.3f} "
                  f"(model {direction}), std={stats['std']}, n={stats['n']}, "
                  f"z={stats['z']}, p={stats['p_value']} -- {sig}")
        print()

    # Real, honest cross-season consistency check -- per the task's own explicit ask.
    seasons = sorted(results.keys())
    if len(seasons) == 2:
        for label in ("margin", "total"):
            s1, s2 = results[seasons[0]][label], results[seasons[1]][label]
            same_direction = (s1["mean"] is not None and s2["mean"] is not None
                               and (s1["mean"] > 0) == (s2["mean"] > 0))
            direction_desc = (
                "the SAME real direction" if same_direction else "DIFFERENT real directions"
            )
            print(f"{label.capitalize()}: {seasons[0]} and {seasons[1]} signed means point in "
                  f"{direction_desc} ({s1['mean']:+.3f} vs {s2['mean']:+.3f}).")


if __name__ == "__main__":
    main()
