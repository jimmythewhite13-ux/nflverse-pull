"""
Real re-run of the 2024 secondary-check champion/challenger matrix against Phase 8 2024's
corrected reconstruction (HFA raw-estimator fix, PROGRESS.md 2026-09-09/10) -- this is the
SAME real margin-symmetry fix already applied to `phase8_2024_run.py`'s own
`hfa_A_home_net_delta` formula (2026-09-08), now additionally re-pointed at the corrected
data_version so `champion_home_margin`/`hfa_delta_home` (both sourced from real, persisted
prediction/component data) reflect the THIRD, distinct HFA bug's fix too -- not just the
margin-symmetry one. Does NOT modify `phase8_2024_run.py`. No real DB writes in the original
script.

Usage:
    uv run python prediction_audit/phase8_2024_run_rerun_hfa_fix.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import prediction_audit.phase8_2024_run as p8r2024  # noqa: E402

p8r2024.DATA_VERSION = "phase8_2024_secondary_check_degraded_olindex_hfa_raw_fix"

if __name__ == "__main__":
    print(f"Real re-run, corrected HFA raw estimator: data_version={p8r2024.DATA_VERSION!r}")
    p8r2024.main()
