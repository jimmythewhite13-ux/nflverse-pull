"""
Real re-run of Phase 8's 2024 secondary-check reconstruction, after the real HFA raw-estimator
fix (PROGRESS.md's "Real bug found and fixed", 2026-09-09). Does NOT modify
`phase8_2024_reconstruction.py` itself -- that script's own real output remains an honest,
historical record of the FIRST 2024 secondary check (now known to have used the buggy, unhalved
HFA estimator, same as the original Phase 1 run). This wrapper reuses that script's exact same
real logic (including its own real, unrelated degraded-OL-Index monkeypatch) unchanged, only
overriding `MODEL_VERSION`/`DATA_VERSION` before calling `main()`.

Usage:
    uv run python prediction_audit/phase8_2024_reconstruction_rerun_hfa_fix.py
"""
from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import prediction_audit.phase8_2024_reconstruction as p8  # noqa: E402
from prediction_audit.db.schema import DEFAULT_DB_PATH  # noqa: E402

p8.MODEL_VERSION = "v35.0-degraded-ol-2024-secondary-check-hfa-raw-estimator-fix"
p8.DATA_VERSION = "phase8_2024_secondary_check_degraded_olindex_hfa_raw_fix"


def _fix_model_description() -> None:
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    conn.execute(
        "UPDATE models SET description = ?, workbook_sha256 = ? WHERE model_version = ?",
        (
            "Real re-run after the HFA raw-estimator factor-of-2 fix (PROGRESS.md's \"Real "
            "bug found and fixed\", 2026-09-09) -- otherwise identical real 2024 secondary "
            "check (degraded OL Index, unrelated to this fix) as the original run.",
            "372e54548a2c5e978aa464c557230c8a8c3091b8fffcdea310563bfc341e4c23",
            p8.MODEL_VERSION,
        ),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    print(f"Real re-run, corrected HFA estimator: model_version={p8.MODEL_VERSION!r}, "
          f"data_version={p8.DATA_VERSION!r}")
    p8.main()
    _fix_model_description()
    print("Real model description/hash corrected post-insert.")
