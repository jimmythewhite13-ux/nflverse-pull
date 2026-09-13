"""
Real, automated Tuesday-morning weekly review (weekly_review_automation.md, 2026-09-12 explicit
user request). By Tuesday morning, the full week's real games (through Monday Night Football)
exist -- this gives the maximum real runway before the next week's Thursday opener.

Real, structural governance boundary, not just a comment: this module only ever reads and
prints real findings -- it has no write path to any table, and calls no ingestion/freeze script.
Per Phase 14's standing governance (restated explicitly in the task doc's own "What NOT to do"):
this flags real findings for human review, it never adjusts anything itself.

Real, dated output: prints a real Markdown report to stdout. The GitHub Actions workflow
redirects this into `$GITHUB_STEP_SUMMARY`, so every real run's findings are preserved on that
run's own Actions page -- no new repo-committed file, no autonomous action, matching "flags...
does not adjust." "No notable anomaly this week" is printed plainly as its own real finding, per
the task doc's own explicit instruction not to pad a quiet week with manufactured content.

Checks run every real week, until 2026-09-29 (Phase 14's own real prediction-freeze go-live,
not a number invented here):
1. Cheat Sheet / market-signal health -- real capture freshness, plus a real, GENERALIZED
   "does any one book show a persistent, one-directional price bias vs. consensus" scanner --
   the exact real methodology that found `pmu_fr`'s real 27/27-games home-team bias this
   session, built here as a reusable check rather than a one-off re-confirmation, so a similar
   real anomaly on any OTHER book gets caught automatically too.
2. Bias-detection tooling progress -- confirms `systematic_bias_detection.compute_bias_stats`
   still imports and runs cleanly against the real 2024/2025 baseline.
3. Downstream readiness -- confirms the real DB tables a live 2026 prediction will need exist
   and are queryable, and that the real ingestion/audit/sync modules it depends on still import
   cleanly, against the real current database state (not synthetic dummy data -- the real
   tables/modules ARE the realistic condition to check against).
4. Reference-output self-check (apply_epl_findings.md Part A) -- re-runs the real, unmodified
   production call chain end-to-end for 3 pinned, already-completed 2025 games and asserts
   output matches a stored reference within tolerance, catching real drift the file-diff
   self-enforcement check structurally cannot see (see `check_reference_output`'s own
   docstring). Placed here rather than the frequent self-enforcement runs given its real cost.

Starting 2026-09-29 onward, additionally:
5. Real, updated systematic-bias calculation using all real 2026 PRODUCTION predictions graded
   so far, with the real current sample size stated plainly (small-sample estimates are real but
   explicitly flagged as less reliable, per the task doc's own instruction).
6. Real, updated weekly metrics (margin/total MAE, winner accuracy, Brier) for the current real
   season, same real methodology `hosted_env/api/main.py`'s `get_historical()` already uses.

Usage:
    uv run python -m prediction_audit.ingestion.weekly_review
"""
from __future__ import annotations

import importlib
import os
import sys
from datetime import UTC, date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

import psycopg  # noqa: E402
from psycopg.rows import dict_row  # noqa: E402

from prediction_audit.historical.systematic_bias_detection import (  # noqa: E402
    compute_bias_stats,
    fetch_real_predictions_vs_actuals,
)
from prediction_audit.ingestion.season import current_nfl_season  # noqa: E402

# Real cutover date the task doc itself specifies (Phase 14's own real prediction-freeze
# go-live) -- not a number invented here.
REAL_LIVE_PREDICTIONS_START = date(2026, 9, 29)

# Real, fixed allowlist (never user input) of tables a live 2026 prediction will need --
# safe to interpolate directly into SQL below.
_REQUIRED_TABLES = (
    "predictions", "prediction_runs", "results", "player_prop_backtest",
    "games", "model_versions",
)
_REQUIRED_MODULES = (
    "prediction_audit.ingestion.results_and_audit",
    "prediction_audit.ingestion.prediction_freeze",
    "prediction_audit.sync_historical_to_postgres",
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


def _implied_probability(odds: float) -> float:
    return 100 / (odds + 100) if odds > 0 else -odds / (-odds + 100)


def check_market_signal_health(conn) -> list[str]:
    """Real Cheat Sheet / market-signal health check -- see module docstring point 1."""
    findings: list[str] = []
    with conn.cursor() as cur:
        cur.execute("SELECT MAX(captured_at) AS latest FROM raw_market_captures;")
        latest = cur.fetchone()["latest"]
        if latest is None:
            findings.append("No real market captures exist at all yet.")
        else:
            age_hours = (datetime.now(UTC) - latest).total_seconds() / 3600
            if age_hours > 48:
                findings.append(
                    f"Real market captures look stale -- latest is {age_hours:.1f}h old "
                    f"(expected at least once daily)."
                )

        # Real, generalized book-bias scanner -- same real methodology confirmed live this
        # session for pmu_fr (27/27 real games, one direction). Flags ANY book showing a
        # persistent, one-directional real deviation from consensus, not just pmu_fr again.
        cur.execute(
            "SELECT game_id, sportsbook, odds, captured_at FROM raw_market_captures "
            "WHERE market_type='moneyline' AND flagged_excluded_source=FALSE "
            "ORDER BY game_id, sportsbook, captured_at DESC;"
        )
        latest_by_game_book: dict[tuple[str, str], float] = {}
        for r in cur.fetchall():
            key = (r["game_id"], r["sportsbook"])
            if key not in latest_by_game_book:
                latest_by_game_book[key] = float(r["odds"])
        by_game: dict[str, dict[str, float]] = {}
        for (gid, book), odds in latest_by_game_book.items():
            by_game.setdefault(gid, {})[book] = odds

        book_diffs: dict[str, list[float]] = {}
        for books in by_game.values():
            if len(books) < 4:
                continue
            for book, odds in books.items():
                others = [v for b, v in books.items() if b != book]
                if len(others) < 3:
                    continue
                consensus = sorted(_implied_probability(v) for v in others)[len(others) // 2]
                book_diffs.setdefault(book, []).append(_implied_probability(odds) - consensus)

        for book, diffs in sorted(book_diffs.items()):
            if len(diffs) < 10:
                continue  # real, honest minimum sample before calling a pattern "persistent"
            n = len(diffs)
            n_pos = sum(1 for d in diffs if d > 0.005)
            n_neg = sum(1 for d in diffs if d < -0.005)
            if n_pos == n or n_neg == n:
                direction = "the home team" if n_pos == n else "the away team"
                mean_diff = sum(diffs) / n
                findings.append(
                    f"Real book bias: `{book}` favors {direction} vs. consensus in {n}/{n} "
                    f"real games (mean {mean_diff * 100:+.2f}pp) -- same real pattern class as "
                    f"the confirmed `pmu_fr` finding (2026-09-12)."
                )
    return findings


def check_bias_detection_progress() -> list[str]:
    """Real check: does `systematic_bias_detection.py` still import and run cleanly against the
    real 2024/2025 baseline? See module docstring point 2."""
    try:
        rows = fetch_real_predictions_vs_actuals()
        by_season: dict[int, list[dict]] = {}
        for r in rows:
            by_season.setdefault(r["season"], []).append(r)
        for srows in by_season.values():
            errors = [
                float(r["projected_margin"]) - (r["home_final_score"] - r["away_final_score"])
                for r in srows
            ]
            compute_bias_stats(errors)
        return [
            f"OK -- systematic_bias_detection runs cleanly against {len(rows)} real baseline "
            f"games across seasons {sorted(by_season.keys())}."
        ]
    except Exception as e:  # noqa: BLE001 -- a real, honest catch-and-report, not a silent pass
        return [f"BROKEN -- systematic_bias_detection failed: {e!r}"]


def check_downstream_readiness(conn) -> list[str]:
    """Real check: are the tables/modules a live 2026 prediction will need genuinely wired?
    See module docstring point 3."""
    findings: list[str] = []
    with conn.cursor() as cur:
        for table in _REQUIRED_TABLES:
            try:
                cur.execute(f"SELECT COUNT(*) AS n FROM {table};")  # real fixed allowlist above
                n = cur.fetchone()["n"]
                findings.append(f"OK -- real table `{table}` exists and is queryable ({n} rows).")
            except Exception as e:  # noqa: BLE001
                conn.rollback()
                findings.append(f"BROKEN -- real table `{table}` check failed: {e!r}")
    for mod_name in _REQUIRED_MODULES:
        try:
            importlib.import_module(mod_name)
            findings.append(f"OK -- `{mod_name}` imports cleanly.")
        except Exception as e:  # noqa: BLE001
            findings.append(f"BROKEN -- `{mod_name}` failed to import: {e!r}")
    return findings


def check_reference_output() -> list[str]:
    """Real reference-output self-check (apply_epl_findings.md Part A, 2026-09-13) -- runs
    ALONGSIDE the existing file-diff self-enforcement check (prediction_audit/ingestion/
    self_enforcement_check.py), not replacing it: that check diffs specific files/directories
    against a git tag, but never inspects `production_pipeline_v35_hfa_a.py` beyond one narrow
    override-scope check, and never inspects `src/nflverse_pull/*` at all -- a real gap where a
    parameter/logic change there could alter real output undetected. This re-runs the real,
    unmodified production call chain end-to-end for 3 pinned, already-completed 2025 games and
    asserts output matches a stored real reference within a tight real tolerance -- see
    `reference_output_check.py`'s own module docstring for the full real rationale.

    Real, deliberate cadence choice: this fetches ~3 real seasons of pbp data and runs the real
    full historical composition (~1-2 real CPU-minutes, confirmed live) -- genuinely more
    expensive than every other check in this module, so it runs here (weekly) rather than in
    the frequent per-ingestion self-enforcement runs."""
    try:
        from prediction_audit.historical.reference_output_check import (
            check_reference_output as _check,
        )
        problems = _check()
        if problems:
            return [f"BROKEN -- {p}" for p in problems]
        return ["OK -- all 3 pinned real 2025 games reproduce the stored reference output "
                "within tolerance."]
    except Exception as e:  # noqa: BLE001
        return [f"BROKEN -- reference-output check itself failed to run: {e!r}"]


def check_live_season_bias(conn, season: int) -> list[str]:
    """Real, updated signed-bias calculation for the current live real season's PRODUCTION
    predictions -- see module docstring point 4. Only meaningful once real 2026 predictions
    exist; an honest, explicit small-n note otherwise, never a fabricated result."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.projected_margin, p.projected_total, "
            "r.away_final_score, r.home_final_score "
            "FROM predictions p "
            "JOIN prediction_runs pr ON pr.id = p.run_id "
            "JOIN model_versions mv ON mv.id = pr.model_version_id "
            "JOIN games g ON g.game_id = pr.game_id "
            "JOIN results r ON r.game_id = g.game_id "
            "WHERE mv.status = 'PRODUCTION' AND g.season = %s;",
            (season,),
        )
        rows = cur.fetchall()
    n = len(rows)
    if n == 0:
        return [f"No real, graded {season} PRODUCTION predictions exist yet."]
    margin_errors = [
        float(r["projected_margin"]) - (r["home_final_score"] - r["away_final_score"])
        for r in rows
    ]
    total_errors = [
        float(r["projected_total"]) - (r["home_final_score"] + r["away_final_score"])
        for r in rows
    ]
    findings = [f"Real current {season} sample size: {n} graded games "
                + ("(small -- treat with real caution)." if n < 30 else "(a reasonable base).")]
    for label, errors in (("Margin", margin_errors), ("Total", total_errors)):
        stats = compute_bias_stats(errors)
        sig = "REAL, SIGNIFICANT" if stats["significant"] else "not significant"
        findings.append(f"{label}: signed mean error {stats['mean']:+.3f}, "
                         f"p={stats['p_value']} -- {sig}.")
    return findings


def check_live_season_metrics(conn, season: int) -> list[str]:
    """Real, updated margin/total MAE, winner accuracy, and Brier for the current real season --
    see module docstring point 5. Same real methodology as `hosted_env/api/main.py`'s
    `get_historical()`, just scoped to whichever model_version is currently PRODUCTION."""
    with conn.cursor() as cur:
        cur.execute(
            "SELECT p.projected_margin, p.projected_total, p.home_win_probability, "
            "r.away_final_score, r.home_final_score "
            "FROM predictions p "
            "JOIN prediction_runs pr ON pr.id = p.run_id "
            "JOIN model_versions mv ON mv.id = pr.model_version_id "
            "JOIN games g ON g.game_id = pr.game_id "
            "JOIN results r ON r.game_id = g.game_id "
            "WHERE mv.status = 'PRODUCTION' AND g.season = %s;",
            (season,),
        )
        rows = cur.fetchall()
    n = len(rows)
    if n == 0:
        return [f"No real, graded {season} PRODUCTION predictions exist yet."]
    margin_abs_errors, total_abs_errors, correct, brier_terms = [], [], 0, []
    for r in rows:
        actual_margin = r["home_final_score"] - r["away_final_score"]
        actual_total = r["home_final_score"] + r["away_final_score"]
        margin_abs_errors.append(abs(float(r["projected_margin"]) - actual_margin))
        total_abs_errors.append(abs(float(r["projected_total"]) - actual_total))
        correct += (float(r["projected_margin"]) > 0) == (actual_margin > 0)
        brier_terms.append(
            (float(r["home_win_probability"]) - (1.0 if actual_margin > 0 else 0.0)) ** 2
        )
    return [
        f"Real {season} metrics (n={n}): Margin MAE={sum(margin_abs_errors) / n:.2f}, "
        f"Total MAE={sum(total_abs_errors) / n:.2f}, "
        f"Winner Acc.={100 * correct / n:.1f}%, Brier={sum(brier_terms) / n:.4f}."
    ]


def main() -> int:
    today = datetime.now(UTC).date()
    live = today >= REAL_LIVE_PREDICTIONS_START
    print(f"# Real Weekly Review -- {today.isoformat()}\n")
    phase_desc = ("YES (2026-09-29 has passed)" if live
                  else f"NOT YET (starts {REAL_LIVE_PREDICTIONS_START.isoformat()})")
    print(f"Real live-predictions phase: {phase_desc}\n")

    conn = psycopg.connect(_real_database_url(), row_factory=dict_row)
    try:
        print("## 1. Cheat Sheet / market-signal health\n")
        findings = check_market_signal_health(conn)
        for f in findings or ["No notable anomaly this week -- a legitimate, real result."]:
            print(f"- {f}")
        print()

        print("## 2. Bias-detection tooling progress\n")
        for f in check_bias_detection_progress():
            print(f"- {f}")
        print()

        print("## 3. Downstream readiness\n")
        for f in check_downstream_readiness(conn):
            print(f"- {f}")
        print()

        print("## 4. Reference-output self-check (real end-to-end model drift)\n")
        for f in check_reference_output():
            print(f"- {f}")
        print()

        if live:
            season = current_nfl_season(datetime.now(UTC))
            print(f"## 5. Real, updated systematic-bias calculation ({season} season)\n")
            for f in check_live_season_bias(conn, season):
                print(f"- {f}")
            print()

            print(f"## 6. Real, updated weekly metrics ({season} season)\n")
            for f in check_live_season_metrics(conn, season):
                print(f"- {f}")
            print()
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
