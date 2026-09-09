"""
Real re-run of Phase 4 (SOS research) against Phase 1's corrected 2025 reconstruction
(HFA raw-estimator fix, PROGRESS.md 2026-09-09). Does NOT modify `phase4_run.py`. Pure
re-point at the corrected data_version; no real DB writes in the original script (confirmed
before writing this wrapper).

Usage:
    uv run python prediction_audit/phase4_run_rerun_hfa_fix.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import prediction_audit.phase4_run as p4  # noqa: E402

p4.DATA_VERSION = "phase1_full_season_reconstruction_2025_hfa_raw_fix"

if __name__ == "__main__":
    print(f"Real re-run, corrected HFA estimator: data_version={p4.DATA_VERSION!r}")
    p4.main()
