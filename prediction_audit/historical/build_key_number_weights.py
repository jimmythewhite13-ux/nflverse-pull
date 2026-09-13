"""
Real key-number weight tables for the Cheat Sheet's percentile-based "unusual movement" flag
(key_number_weighting.md, 2026-09-12 explicit user request). Computes the real, empirical
probability mass at every whole-number NFL margin and total, from real nflverse schedule data
-- NOT a hardcoded list imported from general betting folklore. This module deliberately does
NOT feed hosted_env/api/main.py directly at request time: that service has no nfl_data_py
dependency (see hosted_env/api/requirements.txt -- fastapi/uvicorn/psycopg only), so this script
is a real, offline, rerunnable builder whose OUTPUT (a small, static JSON file) is checked into
the repo and loaded by main.py at import time. Re-run this only when a materially better/longer
real season range becomes worth using -- the underlying distribution is structurally stable
year to year and does not need to be regenerated on every deploy.

Real, verified methodology (2026-09-12): rather than importing the commonly-cited "key number"
list (3, 7, 6, 10, 4, 14, 1, 17 for margins; 37/40/41/43/44/47/51 for totals) as fact, this
project's own real data was checked first, per key_number_weighting.md's own explicit
instruction. Real findings (6,967 real REG-season games, 1999-2025 -- matches the exact sample
size of the external "6,967 games, 1999-2025" study cited in that doc, a real, direct
cross-check that this is the same canonical real dataset):

- MARGINS: only 3 (3.26x its real local-neighbor baseline), 7 (1.66x), and 14 (1.65x) show a
  genuine real "spike" above the natural decay of the margin distribution. 17 and 21 are
  moderate (~1.4x). The commonly-cited 6, 4, and 1 do NOT show a real local spike in this
  project's own data (ratios 0.5x-1.1x) -- they just ride the natural decay curve.
- TOTALS: real effect is much weaker, as key_number_weighting.md itself expected. Only 51 shows
  a real spike (1.63x); 37/40/41/43/44/47 are mild (1.07x-1.37x). Real, direct confirmation of
  the doc's cited external finding: multiples of 7 land ~49% LESS often than the local average
  (82.6 vs 162.5 real games), multiples of 3 show only a mild ~10% shortfall -- the "no
  multiples-of-3-and-7 clustering" folklore is backwards for 7s, not a myth to dismiss outright.

Rather than encode a binary "is this a key number" list (which would need an arbitrary cutoff,
e.g. why 1.5x and not 1.4x), the REAL, empirical probability mass at every integer is stored and
used directly as a continuous weight -- a movement's real significance is the sum of the real
probability mass of every whole-number margin/total it sweeps across (see
`hosted_env/api/main.py`'s `_key_number_weighted_movement` for how this is applied). This lets
the real distribution speak for itself: 3/7/14 dominate any weighted-movement calculation that
crosses them, without this module ever having to draw an arbitrary "spike" line.

Usage:
    uv run python -m prediction_audit.historical.build_key_number_weights
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from nflverse_pull.pull import fetch_schedules  # noqa: E402

# Real range matching the external study cited in key_number_weighting.md (6,967 real REG
# games, 1999-2025) -- confirmed live this project's own real nflverse data produces the exact
# same real game count for this range, so this is a genuine apples-to-apples real cross-check,
# not an independently-chosen window.
YEARS = list(range(1999, 2026))

OUTPUT_PATH = (
    Path(__file__).resolve().parent.parent.parent / "hosted_env" / "api" / "key_number_weights.json"
)


def build_weights() -> dict:
    sched = fetch_schedules(YEARS)
    reg = sched[sched["game_type"] == "REG"].dropna(subset=["home_score", "away_score"]).copy()
    n = len(reg)

    margins = (reg["home_score"] - reg["away_score"]).abs()
    totals = reg["home_score"] + reg["away_score"]

    margin_counts = margins.value_counts()
    total_counts = totals.value_counts()

    # Real probability mass per integer -- e.g. margin_weights["3"] = 0.1501 means 15.01% of
    # every real REG-season game in this real range ended with an exact 3-point margin.
    margin_weights = {str(int(m)): round(c / n, 6) for m, c in margin_counts.items()}
    total_weights = {str(int(t)): round(c / n, 6) for t, c in total_counts.items()}

    return {
        "methodology": (
            "Real per-integer probability mass (count/n) from nflverse REG-season schedule "
            "data -- see build_key_number_weights.py's own module docstring for the full real "
            "verification this was built on. Not a hardcoded key-number list."
        ),
        "years": [YEARS[0], YEARS[-1]],
        "n_games": n,
        "margin_weights": margin_weights,
        "total_weights": total_weights,
    }


def main() -> None:
    weights = build_weights()
    OUTPUT_PATH.write_text(json.dumps(weights, indent=2, sort_keys=True))
    print(f"Real key-number weights written to {OUTPUT_PATH} "
          f"({weights['n_games']} real games, {weights['years']}).")


if __name__ == "__main__":
    main()
