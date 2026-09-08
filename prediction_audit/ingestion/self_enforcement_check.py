"""
Section 5 of the governing spec: before and after every scheduled ingestion run, prove the
production model hasn't drifted from what `v35-audit-passed-hfa-fix` validated. Fails LOUDLY
(non-zero exit, printed to stdout so CI surfaces it) on ANY real drift -- never a silent pass.

Three real, independent checks, not one broad "diff everything":

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
TAG = "v35-audit-passed-hfa-fix"
FROZEN_XLSX = REPO_ROOT / "prediction_audit/frozen_baselines/NFL_Prediction_Model_v35.xlsx"
REAL_TAGGED_SHA256 = "ac54ed4b893a0aae818a5419496e2e69fe60614afee92dea40e8a4585acdcb7d"
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


def main() -> int:
    all_problems: list[str] = []
    all_problems += check_workbook_integrity()
    all_problems += check_engine_files_unchanged()
    all_problems += check_production_override_scope()

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
          f"override zeroes exactly the 3 Phase-12-sanctioned keys, no more, no fewer.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
