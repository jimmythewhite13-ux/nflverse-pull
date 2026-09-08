"""Real, standard NFL-season-year convention (the season is named by the calendar year it
starts in) -- so the GitHub Actions workflows never need a hardcoded season number that goes
stale every year. January/February are still the PRIOR season's playoffs.

Usage (as the workflows use it): `uv run python -m prediction_audit.ingestion.season` prints
the real current season year to stdout, nothing else.
"""
from __future__ import annotations

from datetime import UTC, datetime


def current_nfl_season(today: datetime | None = None) -> int:
    today = today or datetime.now(UTC)
    return today.year - 1 if today.month <= 2 else today.year


if __name__ == "__main__":
    print(current_nfl_season())
