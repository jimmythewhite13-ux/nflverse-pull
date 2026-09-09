"""
Real re-run of Phase 2 (Travel research) against Phase 1's corrected 2025 reconstruction
(HFA raw-estimator fix, PROGRESS.md 2026-09-09). Does NOT modify `phase2_run.py` -- that
script's own real output remains an honest record of the original run (against the pre-fix
data). Pure re-point at the corrected data_version; `phase2_run.py` makes no real DB writes,
so no model-description fixup is needed here (confirmed before writing this wrapper).

Usage:
    uv run python prediction_audit/phase2_run_rerun_hfa_fix.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import prediction_audit.phase2_run as p2  # noqa: E402

p2.DATA_VERSION = "phase1_full_season_reconstruction_2025_hfa_raw_fix"

if __name__ == "__main__":
    print(f"Real re-run, corrected HFA estimator: data_version={p2.DATA_VERSION!r}")
    p2.main()
