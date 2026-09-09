"""
Real re-run of Phase 1's full 2025 reconstruction, after the real HFA raw-estimator fix
(PROGRESS.md's "Real bug found and fixed", 2026-09-09). Does NOT modify
`phase1_reconstruction_2025.py` itself -- that script's own real output remains an honest,
historical record of what the FIRST Phase 1 run actually did (now known to have used the
buggy, unhalved HFA estimator). This wrapper reuses that script's exact same real logic
unchanged, only overriding its `MODEL_VERSION`/`DATA_VERSION` module globals before calling
`main()`, so the corrected re-run persists under its own distinct, clearly-labeled tag --
never overwriting or deleting the original real data.

Usage:
    uv run python prediction_audit/phase1_reconstruction_2025_rerun_hfa_fix.py
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import sqlite3  # noqa: E402

import prediction_audit.phase1_reconstruction_2025 as p1  # noqa: E402
from prediction_audit.db.schema import DEFAULT_DB_PATH  # noqa: E402

p1.MODEL_VERSION = "v35.0-hfa-raw-estimator-fix"
p1.DATA_VERSION = "phase1_full_season_reconstruction_2025_hfa_raw_fix"


def _fix_model_description() -> None:
    """`main()`'s own real `insert_model()` call inserts a hardcoded description/hash string
    written for the ORIGINAL run -- correct it in place afterward (INSERT OR IGNORE already
    created the real row under our new model_version key) rather than editing that function
    body, which stays an honest record of the original script's real behavior."""
    conn = sqlite3.connect(DEFAULT_DB_PATH)
    conn.execute(
        "UPDATE models SET description = ?, workbook_sha256 = ? WHERE model_version = ?",
        (
            "Real re-run after the HFA raw-estimator factor-of-2 fix (PROGRESS.md's \"Real "
            "bug found and fixed\", 2026-09-09), tagged v35-audit-passed-hfa-raw-estimator-"
            "fix -- otherwise identical real Python walk-forward historical reconstruction "
            "(Step 6) as the original Phase 1 full-season run.",
            "372e54548a2c5e978aa464c557230c8a8c3091b8fffcdea310563bfc341e4c23",
            p1.MODEL_VERSION,
        ),
    )
    conn.commit()
    conn.close()


if __name__ == "__main__":
    print(f"Real re-run, corrected HFA estimator: model_version={p1.MODEL_VERSION!r}, "
          f"data_version={p1.DATA_VERSION!r}")
    p1.main()
    _fix_model_description()
    print("Real model description/hash corrected post-insert.")
