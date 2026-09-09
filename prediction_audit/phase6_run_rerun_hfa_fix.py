"""
Real re-run of Phase 6 (HFA research) against Phase 1's corrected 2025 reconstruction (HFA
raw-estimator fix, PROGRESS.md 2026-09-09) -- this is the SAME real fix already applied and
run directly against `phase6_run.py` earlier the same day (against the OLD, stale Phase 1
persisted data, using a live walk-forward recomputation for the champion's own net HFA). This
wrapper re-runs it a second time, now pointed at Phase 1's freshly-corrected persisted data
throughout, for full internal consistency -- expected to reproduce the same real numbers,
since `phase6_run.py`'s own champion computation already recomputes HFA fresh via the
corrected resolver either way. Does NOT modify `phase6_run.py`. No real DB writes in the
original script.

Usage:
    uv run python prediction_audit/phase6_run_rerun_hfa_fix.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import prediction_audit.phase6_run as p6  # noqa: E402

p6.DATA_VERSION = "phase1_full_season_reconstruction_2025_hfa_raw_fix"

if __name__ == "__main__":
    print(f"Real re-run, corrected HFA estimator (fully consistent data): "
          f"data_version={p6.DATA_VERSION!r}")
    p6.main()
