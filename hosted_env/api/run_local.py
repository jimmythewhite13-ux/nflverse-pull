"""
Real, local-dev-only launcher: loads the repo's real, gitignored .env (same file/pattern as
ODDS_API_KEY) so `DATABASE_URL` is available to main.py, then starts uvicorn. This file is
committed (it contains no secret itself, only the loading logic); .env stays gitignored as
always. Render's real deployment sets DATABASE_URL directly as a Web Service environment
variable and does not use this file at all.

Usage:
    uv run python hosted_env/api/run_local.py
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import uvicorn

_REPO_ROOT = Path(__file__).resolve().parent.parent.parent
_ENV_PATH = _REPO_ROOT / ".env"

# Real fix: running this file directly (python .../run_local.py) puts hosted_env/api/ on
# sys.path[0], not the repo root, so the "hosted_env.api.main" import string below would
# otherwise fail to resolve. Insert the real repo root explicitly.
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))


def _load_env() -> None:
    if not _ENV_PATH.exists():
        return
    for line in _ENV_PATH.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


if __name__ == "__main__":
    _load_env()
    uvicorn.run("hosted_env.api.main:app", host="127.0.0.1", port=8420)
