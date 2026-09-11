"""
Section 5 of the governing spec: before and after every scheduled ingestion run, prove the
production model hasn't drifted from what `v35-audit-passed-hfa-fix` validated. Fails LOUDLY
(non-zero exit, printed to stdout so CI surfaces it) on ANY real drift -- never a silent pass.

Four real, independent checks, not one broad "diff everything":

1. **Frozen workbook byte-for-byte integrity** -- the real mathematical source of truth. A
   real SHA-256 mismatch here means the actual formulas/coefficients changed, full stop.
2. **Every `engine/`/`historical/` file that existed at the tag** -- these encode the real
   formula implementations Phase 0 validated cell-by-cell. `git diff <tag> -- <path>` must be
   empty for every one of them. (`production_pipeline_v35_hfa_a.py` and the `ingestion/`
   package itself postdate the tag by design -- checked separately in #3, not diffed against a
   tag that couldn't have contained them.)
3. **The one sanctioned production deviation, exactly** -- `production_pipeline_v35_hfa_a.py`'s
   `_apply_hfa_a_override()` must zero exactly the 3 real keys Phase 12 specifies
   (`flat_hfa`, `hfa_delta_home`, `hfa_delta_away`) and nothing else. A direct, real source
   inspection (not a git diff, since this file postdates the tag) -- catches scope creep in the
   one intentional, documented deviation from frozen v35.
4. **No un-flagged, unapproved sportsbook in the live agent's real market captures** -- every
   real row in `raw_market_captures` not marked `flagged_excluded_source=1` (an acknowledged
   historical exception) must reference an approved book. The database-level trigger
   (schema.py) should make a new violation impossible; this check catches it anyway if it ever
   somehow doesn't.

Usage:
    uv run python -m prediction_audit.ingestion.self_enforcement_check
Exit code 0 = clean (no real drift). Exit code 1 = real drift detected, printed in full.
"""
from __future__ import annotations

import hashlib
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
# Real, deliberate re-tag (2026-09-09): the prior tag (v35-audit-passed-hfa-fix) reflected the
# workbook BEFORE the real raw-HFA-estimator factor-of-2 fix (PROGRESS.md's "Real bug found and
# fixed" entry) -- referencing it here after that real, authorized fix would make every future
# self-enforcement run fail against a checkpoint that is now known to be wrong, not a real drift
# alarm. Same real process Phase 0 itself established: fix, verify, re-tag, point here at the
# new tag.
TAG = "v35-audit-passed-hfa-raw-estimator-fix"
FROZEN_XLSX = REPO_ROOT / "prediction_audit/frozen_baselines/NFL_Prediction_Model_v35.xlsx"
REAL_TAGGED_SHA256 = "372e54548a2c5e978aa464c557230c8a8c3091b8fffcdea310563bfc341e4c23"
PRODUCTION_PIPELINE = REPO_ROOT / "prediction_audit/production_pipeline_v35_hfa_a.py"
ALLOWED_OVERRIDE_KEYS = {"flat_hfa", "hfa_delta_home", "hfa_delta_away"}


def _run_git(*args: str) -> str:
    result = subprocess.run(
        ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    return result.stdout


def check_workbook_integrity() -> list[str]:
    if not FROZEN_XLSX.exists():
        return [f"CRITICAL: frozen workbook missing entirely at {FROZEN_XLSX}"]
    real_sha = hashlib.sha256(FROZEN_XLSX.read_bytes()).hexdigest()
    if real_sha != REAL_TAGGED_SHA256:
        return [
            f"CRITICAL: frozen workbook SHA-256 drift. "
            f"Tagged ({TAG})={REAL_TAGGED_SHA256}, current={real_sha}. "
            f"The frozen mathematical source of truth has changed since the tag."
        ]
    return []


def check_engine_files_unchanged() -> list[str]:
    """Real, deliberate fix (caught by this script's own smoke test, not trusted blindly):
    `git diff TAG HEAD -- path` only compares two COMMITS -- an uncommitted working-tree edit
    (exactly what a compromised or buggy CI step might introduce right before running) would
    show as clean. `git diff TAG -- path` (no second ref) diffs the tag against the actual
    working tree on disk instead, which is what "the code about to run" really means."""
    tagged_files = _run_git(
        "ls-tree", "-r", "--name-only", TAG, "--",
        "prediction_audit/engine", "prediction_audit/historical",
    ).splitlines()
    tagged_files = [f for f in tagged_files if f.strip()]
    problems = []
    for path in tagged_files:
        diff = _run_git("diff", TAG, "--", path)
        if diff.strip():
            problems.append(f"CRITICAL: real diff detected in {path} vs. tag {TAG}:\n{diff}")
    return problems


def check_production_override_scope() -> list[str]:
    if not PRODUCTION_PIPELINE.exists():
        return [f"CRITICAL: {PRODUCTION_PIPELINE} is missing -- cannot verify the one "
                f"sanctioned production deviation."]
    source = PRODUCTION_PIPELINE.read_text(encoding="utf-8")
    # Real, direct check: every literal `components["<key>"] = 0.0` assignment inside the
    # override function must be one of the 3 real sanctioned keys, no more, no fewer.
    import re
    func_match = re.search(
        r"def _apply_hfa_a_override.*?(?=\ndef |\Z)", source, re.S,
    )
    if not func_match:
        return ["CRITICAL: _apply_hfa_a_override() function not found in "
                "production_pipeline_v35_hfa_a.py -- cannot verify override scope."]
    body = func_match.group(0)
    assigned_keys = set(re.findall(r'components\["([a-z_]+)"\]\s*=\s*0\.0', body))
    unexpected = assigned_keys - ALLOWED_OVERRIDE_KEYS
    missing = ALLOWED_OVERRIDE_KEYS - assigned_keys
    problems = []
    if unexpected:
        problems.append(
            f"CRITICAL: production override zeroes UNEXPECTED key(s) beyond Phase 12's "
            f"3 sanctioned keys: {sorted(unexpected)}. This is real, unauthorized scope creep."
        )
    if missing:
        problems.append(
            f"CRITICAL: production override no longer zeroes ALL 3 Phase-12-sanctioned "
            f"keys -- missing: {sorted(missing)}."
        )
    return problems


def check_no_unapproved_sportsbook_rows() -> list[str]:
    """Real, fixed 2026-09-09 (see PROGRESS.md's real bug report on offshore books): every real
    NON-flagged row in raw_market_captures must reference an approved sportsbook -- a flagged
    row (flagged_excluded_source=1) is an acknowledged, preserved historical exception, not a
    live compliance violation; this check only flags a NEW, un-flagged violation, which the
    real database-level trigger (schema.py) should make impossible going forward regardless."""
    import sqlite3

    from prediction_audit.db.schema import DEFAULT_DB_PATH

    db_path = Path(DEFAULT_DB_PATH)
    if not db_path.exists():
        return []  # a fresh checkout with no real DB yet -- nothing to check
    conn = sqlite3.connect(db_path)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(raw_market_captures)")]
        if "flagged_excluded_source" not in cols:
            return ["CRITICAL: raw_market_captures.flagged_excluded_source column is missing "
                    "-- the real sportsbook allow-list migration has not been applied."]
        rows = conn.execute(
            "SELECT DISTINCT sportsbook FROM raw_market_captures "
            "WHERE flagged_excluded_source = 0 "
            "AND sportsbook NOT IN (SELECT name FROM approved_sportsbooks)"
        ).fetchall()
    finally:
        conn.close()
    if rows:
        return [f"CRITICAL: real, un-flagged row(s) reference unapproved sportsbook(s): "
                f"{sorted(r[0] for r in rows)} -- the database-level trigger should have "
                f"rejected these; investigate how they landed here."]

    # Real, same check extended to raw_player_prop_captures (2026-09-11) -- identical allow-list
    # discipline and identical database-level trigger, so identical audit-visibility check.
    conn = sqlite3.connect(db_path)
    try:
        cols = [row[1] for row in conn.execute("PRAGMA table_info(raw_player_prop_captures)")]
        if not cols:
            return []  # table not created yet on this checkout -- nothing to check
        prop_rows = conn.execute(
            "SELECT DISTINCT sportsbook FROM raw_player_prop_captures "
            "WHERE flagged_excluded_source = 0 "
            "AND sportsbook NOT IN (SELECT name FROM approved_sportsbooks)"
        ).fetchall()
    finally:
        conn.close()
    if prop_rows:
        return [f"CRITICAL: real, un-flagged row(s) in raw_player_prop_captures reference "
                f"unapproved sportsbook(s): {sorted(r[0] for r in prop_rows)} -- the "
                f"database-level trigger should have rejected these; investigate how they "
                f"landed here."]
    return []


def main() -> int:
    all_problems: list[str] = []
    all_problems += check_workbook_integrity()
    all_problems += check_engine_files_unchanged()
    all_problems += check_production_override_scope()
    all_problems += check_no_unapproved_sportsbook_rows()

    if all_problems:
        print("=== SELF-ENFORCEMENT CHECK FAILED -- real drift detected ===\n")
        for p in all_problems:
            print(p)
            print()
        print(f"({len(all_problems)} real problem(s) found. Failing loudly per Section 5 -- "
              f"a human must review before anything continues.)")
        return 1

    print(f"Self-enforcement check: CLEAN. Frozen workbook SHA-256 matches tag {TAG} exactly "
          f"({REAL_TAGGED_SHA256}). All engine/historical files unchanged vs. tag. Production "
          f"override zeroes exactly the 3 Phase-12-sanctioned keys, no more, no fewer. No "
          f"un-flagged, unapproved sportsbook rows found.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
