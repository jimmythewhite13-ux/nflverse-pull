"""
Real reference-output self-check (apply_epl_findings.md Part A, 2026-09-13 explicit user
request) -- a real gap in the existing `self_enforcement_check.py`: that script diffs specific
FILES (`prediction_audit/engine`/`prediction_audit/historical` against a git tag) plus one
narrowly-scoped check of `_apply_hfa_a_override`'s exact key set. Two real classes of drift slip
through untouched: (1) any OTHER change to `production_pipeline_v35_hfa_a.py` itself (it
"postdates the tag by design," so it is never diffed at all, and the override-scope check only
ever looks at the one override function, nothing else in that file), and (2) any change to
`src/nflverse_pull/*` (EPA calculations, team-name mappings, anything the production pipeline
calls) -- neither existing check inspects that package at all. A real parameter tweak in either
place would alter real output without ever touching a file either existing check diffs.

Real, deliberate design: rather than diff files, this RE-RUNS the real, unmodified production
call chain (`resolve_historical_model_components` -> `_apply_hfa_a_override` ->
`compute_model_home_away_score`) end to end for a pinned, fixed real set of ALREADY-COMPLETED
2025 games, and asserts the real output still matches a stored real reference within a tight
real tolerance. This catches drift from ANY source in the real dependency chain, not just the
two directories the existing check happens to diff -- runs ALONGSIDE that check, not replacing
it (per the task doc's own explicit instruction; each catches a real, different failure mode).

Real, deliberate use of ALREADY-COMPLETED historical games, not a live re-fetch of in-progress
data: nflverse's pbp/schedule data for a finished season is stable (confirmed by this project's
own repeated real backtest re-runs producing identical results) -- a live re-fetch of these
specific, already-final games is already effectively a "frozen data snapshot" without needing to
separately save one to disk, so this isolates real CODE/PARAMETER drift (the real thing being
checked for) from real, separate upstream-data-revision risk (a different, much rarer concern,
and NOT what this task asks about).

Real, deliberate scope note on cadence: unlike the existing self-enforcement check (cheap,
file-only diffs, runs before/after every scheduled ingestion job), this one fetches ~3 real
seasons of pbp data and runs the real full historical composition -- genuinely more expensive
(~1-2 real CPU-minutes). Wired into the weekly review (a real, appropriate lower cadence for
this real cost), not into the frequent per-ingestion self-enforcement runs.

Usage:
    uv run python -m prediction_audit.historical.reference_output_check          # check
    uv run python -m prediction_audit.historical.reference_output_check --build  # (re)build
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from nflverse_pull.efficiency import fetch_pbp  # noqa: E402
from nflverse_pull.oline_stats import fetch_ftn, fetch_pfr_pass, fetch_pfr_rush  # noqa: E402
from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from nflverse_pull.rb_stats import fetch_ngs_rushing  # noqa: E402
from prediction_audit.backtest_step7_multiweek import (  # noqa: E402
    _resolve_season_level_stats,
    _resolve_week_level_stats,
)
from prediction_audit.engine.season_matchups import compute_model_home_away_score  # noqa: E402
from prediction_audit.historical.full_game_prediction import (  # noqa: E402
    HistoricalGameDataBundle,
    resolve_historical_model_components,
)
from prediction_audit.historical.real_constants import (  # noqa: E402
    build_real_constants,
    load_real_model_assumptions,
)
from prediction_audit.production_pipeline_v35_hfa_a import (  # noqa: E402
    _apply_hfa_a_override,
)

FROZEN_XLSX = str(
    Path(__file__).resolve().parent.parent / "frozen_baselines" / "NFL_Prediction_Model_v35.xlsx"
)
REFERENCE_PATH = (
    Path(__file__).resolve().parent.parent / "manifests" / "reference_output_pinned.json"
)
REAL_TOLERANCE = 1e-6  # real, tight -- fixed real code + fixed real completed-game data should
# reproduce EXACTLY; this only allows for benign floating-point summation-order noise.

# Real, fixed, specific historical games (season 2025, week 4 -- all real, already-completed,
# confirmed directly against this project's own live Historical tab) -- not "whichever game
# happens to be first," a genuinely pinned real list per the task doc's own explicit ask.
REFERENCE_GAMES: list[tuple[int, int, str, str]] = [
    (2025, 4, "KC", "BAL"),   # Ravens @ Chiefs
    (2025, 4, "NE", "CAR"),   # Panthers @ Patriots
    (2025, 4, "LV", "CHI"),   # Bears @ Raiders
]


def compute_reference_outputs(
    override_fn=_apply_hfa_a_override, bundle=None, c=None,
) -> tuple[dict[str, dict[str, float]], HistoricalGameDataBundle, dict[int, float]]:
    """Real, end-to-end computation via the EXACT SAME real production call chain
    `production_pipeline_v35_hfa_a.py`'s own `main()` uses -- not a separately re-derived
    approximation.

    `override_fn` (default: the real, unmodified `_apply_hfa_a_override`) and `bundle`/`c` are
    real, deliberate injection points -- NOT used by the normal build/check flow (which always
    uses the real defaults), but let `reference_output_drift_demo.py` reuse one real, expensive
    data fetch to compute both the real and a deliberately-perturbed output in the same process,
    for the required real evidence that this check catches drift the file-diff check misses,
    without needing a second real ~10-minute fetch or touching any real production file."""
    if bundle is None or c is None:
        seasons = sorted({season for season, _, _, _ in REFERENCE_GAMES})
        if len(seasons) != 1:
            raise ValueError("Real, deliberate constraint: all reference games must share one "
                              "season so season-level stats are resolved exactly once, cheaply.")
        season = seasons[0]

        pbp_3yr = fetch_pbp([season - 3, season - 2, season - 1])
        pbp_current = fetch_pbp([season])
        sched_current = fetch_schedules([season])
        sched_3yr = fetch_schedules([season - 3, season - 2, season - 1])
        pfr_pass = fetch_pfr_pass([season - 3, season - 2, season - 1])
        pfr_rush = fetch_pfr_rush([season - 3, season - 2, season - 1])
        ftn = fetch_ftn([season - 3, season - 2, season - 1])
        ngs_rushing_3yr = fetch_ngs_rushing([season - 3, season - 2, season - 1])
        ngs_rushing_current = fetch_ngs_rushing([season])

        bundle = HistoricalGameDataBundle(
            pbp_3yr_prior=pbp_3yr, pbp_current_season=pbp_current,
            sched_current_season=sched_current, sched_3yr_prior=sched_3yr,
            pfr_pass_3yr=pfr_pass, pfr_rush_3yr=pfr_rush, ftn_3yr=ftn,
            ngs_rushing_3yr_prior=ngs_rushing_3yr, ngs_rushing_current=ngs_rushing_current,
        )
        c = load_real_model_assumptions(FROZEN_XLSX)
    season = REFERENCE_GAMES[0][0]

    outputs: dict[str, dict[str, float]] = {}
    stats_by_week: dict[int, tuple] = {}
    for season_g, week, home_abbr, away_abbr in REFERENCE_GAMES:
        if week not in stats_by_week:
            stats_by_week[week] = _resolve_season_level_stats(bundle, season, c)
        ol_stats, prg_stats, pd_stats, rd_stats, qbe_stats, ep_stats = stats_by_week[week]
        qb_stats, rb_stats = _resolve_week_level_stats(bundle, season, week, c)
        constants = build_real_constants(
            FROZEN_XLSX, qb_stats, rb_stats, ol_stats, prg_stats, pd_stats, rd_stats,
            qbe_stats, ep_stats,
        )
        home_team, away_team = TEAM_NAMES[home_abbr], TEAM_NAMES[away_abbr]
        components = resolve_historical_model_components(
            bundle, constants, season, week, home_team, home_abbr, away_team, away_abbr,
        )
        components = override_fn(components)
        home_score, away_score = compute_model_home_away_score(**components)
        key = f"{season}_w{week}_{away_abbr}@{home_abbr}"
        outputs[key] = {"home_score": home_score, "away_score": away_score,
                         "margin": home_score - away_score, "total": home_score + away_score}
    return outputs, bundle, c


def build_reference() -> None:
    outputs, _bundle, _c = compute_reference_outputs()
    REFERENCE_PATH.write_text(json.dumps(outputs, indent=2, sort_keys=True))
    print(f"Real reference output written to {REFERENCE_PATH} for {len(outputs)} pinned games.")
    for key, vals in outputs.items():
        print(f"  {key}: {vals}")


def check_reference_output() -> list[str]:
    """Real check: does the SAME real production call chain still reproduce the stored real
    reference, within tolerance, for every pinned real game? Returns a list of real problems
    (empty = clean)."""
    if not REFERENCE_PATH.exists():
        return [f"CRITICAL: no real reference file at {REFERENCE_PATH} -- run with --build "
                f"once to create it before this check can run."]
    stored = json.loads(REFERENCE_PATH.read_text())
    current, _bundle, _c = compute_reference_outputs()
    problems = []
    for key, stored_vals in stored.items():
        if key not in current:
            problems.append(f"CRITICAL: reference game {key} no longer resolves at all.")
            continue
        for field, stored_v in stored_vals.items():
            current_v = current[key][field]
            if abs(current_v - stored_v) > REAL_TOLERANCE:
                problems.append(
                    f"CRITICAL: real output drift on {key}.{field}: reference={stored_v}, "
                    f"current={current_v} (diff={current_v - stored_v:+.6f}, "
                    f"tolerance={REAL_TOLERANCE})."
                )
    return problems


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--build", action="store_true",
                         help="(Re)build the real reference file from current code/data.")
    args = parser.parse_args()
    if args.build:
        build_reference()
        return 0
    problems = check_reference_output()
    if problems:
        print("=== REFERENCE-OUTPUT CHECK FAILED -- real output drift detected ===\n")
        for p in problems:
            print(p)
        return 1
    print(f"Reference-output check: CLEAN. All {len(REFERENCE_GAMES)} pinned real games "
          f"reproduce the stored reference within tolerance ({REAL_TOLERANCE}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
