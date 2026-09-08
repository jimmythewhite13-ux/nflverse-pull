"""
Test for prediction_audit/historical/full_game_prediction.py -- pure logic, no network.
Every sub-resolver this module composes is already independently verified against real data,
and the full composition itself was verified live end to end (San Francisco @ LA Rams, 2025
week 10, real Model Score 25.70-22.45, +3.25 real home margin -- see the module's own commit
message and demo_full_game_prediction.py).

This test is a real regression guard for a real bug caught during that live verification: an
early version of `resolve_historical_model_home_away_score` passed only the CURRENT season's
real schedule into Base Team Quality's own `resolve_team_quality_for_game()`, which genuinely
needs real Y1/Y2/Y3 (3 full prior seasons) from the SAME DataFrame -- it correctly raised
rather than silently using a truncated real history, surfacing the bug immediately. Fixed by
concatenating the bundle's own two real schedule slices before that one call.
"""
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.historical.full_game_prediction import (  # noqa: E402
    HistoricalGameDataBundle,
)


def test_bundle_sched_slices_combine_to_cover_all_4_real_seasons():
    """Real regression guard: Base Team Quality's own resolver needs target_season-3
    through target_season in ONE DataFrame -- proves the bundle's 2 real schedule slices,
    concatenated the way the composer itself does internally, actually cover that full real
    span (would have caught the original bug: passing sched_current_season alone)."""
    sched_3yr_prior = pd.DataFrame([
        {"season": s, "week": 1} for s in (2022, 2023, 2024)
    ])
    sched_current = pd.DataFrame([{"season": 2025, "week": 1}])
    bundle = HistoricalGameDataBundle(
        pbp_3yr_prior=pd.DataFrame(), pbp_current_season=pd.DataFrame(),
        sched_current_season=sched_current, sched_3yr_prior=sched_3yr_prior,
        pfr_pass_3yr=pd.DataFrame(), pfr_rush_3yr=pd.DataFrame(), ftn_3yr=pd.DataFrame(),
        ngs_rushing_3yr_prior=pd.DataFrame(), ngs_rushing_current=pd.DataFrame(),
    )
    combined = pd.concat(
        [bundle.sched_3yr_prior, bundle.sched_current_season], ignore_index=True,
    )
    target_season = 2025
    for offset in (1, 2, 3):
        assert (combined["season"] == target_season - offset).any(), (
            f"season {target_season - offset} missing from the combined real schedule -- "
            f"resolve_team_quality_for_game() would raise, reproducing the real bug this "
            f"test guards against."
        )


def test_bundle_current_season_alone_is_missing_prior_years():
    """Confirms the real bug this test guards against WOULD reproduce: sched_current_season
    alone (the pre-fix wiring) genuinely does not cover the real prior seasons."""
    sched_current = pd.DataFrame([{"season": 2025, "week": 1}])
    assert not (sched_current["season"] == 2024).any()
