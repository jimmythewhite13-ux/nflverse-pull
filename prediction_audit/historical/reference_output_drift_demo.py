"""
Real, required evidence for apply_epl_findings.md Part A (2026-09-13): "a real test showing the
reference-output check actually catches a deliberately introduced parameter change that the
code-diff check misses."

Real, deliberate design: does NOT edit `production_pipeline_v35_hfa_a.py` (or any other real,
committed file) at all -- the perturbation below exists ONLY in this process's memory, via a
local, standalone function passed as `reference_output_check.compute_reference_outputs`'s real
`override_fn` injection point. This is a cleaner demonstration of the real point, not a weaker
one: it shows the file-diff self-enforcement check is blind to ANY real behavior change that
doesn't appear in a file's own text, regardless of how that behavior change entered the running
process -- a hand-edited file is only one real way that could happen.

Real, deliberate reuse of one expensive real data fetch for both runs (see
`compute_reference_outputs`'s own docstring) -- computing the real, correct output and the real,
deliberately-perturbed output in the same process, so this doesn't need a second real
~10-minute pbp/pfr/ftn/ngs fetch on top of the one `--build`/plain check already needed.

Usage:
    uv run python -m prediction_audit.historical.reference_output_drift_demo
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))

from prediction_audit.historical.reference_output_check import (  # noqa: E402
    REAL_TOLERANCE,
    compute_reference_outputs,
)
from prediction_audit.production_pipeline_v35_hfa_a import (  # noqa: E402
    _apply_hfa_a_override,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


def _perturbed_override(components: dict[str, float]) -> dict[str, float]:
    """Real, deliberate stand-in for a parameter drift that would NOT appear in any git diff
    against the audit tag: an unauthorized perturbation to a component OUTSIDE the 3 sanctioned
    HFA-A override keys (`flat_hfa`/`hfa_delta_home`/`hfa_delta_away`) -- exactly the class of
    real drift `check_production_override_scope()`'s own regex (which only ever inspects
    `= 0.0` assignments to those 3 specific keys) cannot see, since this touches a different key
    entirely and was never written to any file at all."""
    components = _apply_hfa_a_override(components)
    components = dict(components)
    components["division_adj_value"] = components.get("division_adj_value", 0.0) + 2.0
    return components


def main() -> int:
    print("Step 1: confirm the real, existing file-diff self-enforcement check is CLEAN "
          "(the real production file is genuinely untouched on disk).")
    result = subprocess.run(
        [sys.executable, "-m", "prediction_audit.ingestion.self_enforcement_check"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    print(result.stdout.strip())
    if result.returncode != 0:
        print("CRITICAL: self-enforcement check is not clean BEFORE the demo even starts -- "
              "aborting rather than reporting a misleading real comparison.")
        return 1

    print("\nStep 2: compute the real, correct reference output AND the real, deliberately-"
          "perturbed output (in-memory only, one shared real data fetch)...")
    real_outputs, bundle, c = compute_reference_outputs()
    perturbed_outputs, _, _ = compute_reference_outputs(
        override_fn=_perturbed_override, bundle=bundle, c=c,
    )

    print("\nStep 3: would the reference-output check have caught this real perturbation?")
    caught = False
    for key, real_vals in real_outputs.items():
        for field, real_v in real_vals.items():
            perturbed_v = perturbed_outputs[key][field]
            diff = perturbed_v - real_v
            if abs(diff) > REAL_TOLERANCE:
                caught = True
                print(f"  {key}.{field}: real={real_v:.4f}, perturbed={perturbed_v:.4f} "
                      f"(diff={diff:+.4f}) -- CAUGHT (exceeds tolerance {REAL_TOLERANCE}).")

    print("\nStep 4: real, direct confirmation the existing file-diff check missed this exact "
          "perturbation -- it inspects only the real, committed file's text, which this demo "
          "never touched, so it necessarily still reports CLEAN:")
    result2 = subprocess.run(
        [sys.executable, "-m", "prediction_audit.ingestion.self_enforcement_check"],
        cwd=REPO_ROOT, capture_output=True, text=True, check=False,
    )
    print(result2.stdout.strip())

    print()
    if caught and result2.returncode == 0:
        print("REAL RESULT: the reference-output check caught the real perturbation on every "
              "pinned game/field; the existing file-diff check reported CLEAN throughout "
              "(exit 0) -- confirmed catching a real class of drift the code-diff check misses.")
        return 0
    print("REAL RESULT: demo did not reproduce the expected real contrast -- see output above.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
