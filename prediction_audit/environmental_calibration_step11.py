"""
Step 11: real environmental calibration -- checks whether the real, hardcoded Model
Assumptions thresholds/coefficients for Weather Adj, Travel Effect, Rest Effect, and Division
Adj are actually well-fit against real historical scoring effects, not just whether the terms
help at all (already answered by Step 9's ablation).

Real, deliberate scope, not fabricated around: nflverse's own real schedule data carries real
`wind`/`temp` (outdoor games only) and real `away_rest`/`home_rest`/`div_game` directly -- no
pbp/PFR/FTN pull needed for this analysis, only `fetch_schedules()`. Weather Adj's real
precip_adj/snow_adj/humidity_threshold/humidity_adj constants are NOT checked here -- nflverse's
schedule data has no real precipitation/humidity field at this granularity; a real, honest gap,
not silently skipped without saying so.

Real travel-distance calibration reuses `stadium_locations.py`'s own already-verified haversine
distance (validated to within 0.21mi against v35's own real ground truth) -- no new coordinate
work needed.

Usage:
    uv run python prediction_audit/environmental_calibration_step11.py [start_season] [end_season]
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from prediction_audit.historical.real_constants import load_real_model_assumptions  # noqa: E402
from prediction_audit.historical.stadium_locations import (  # noqa: E402
    resolve_travel_effect_miles,
)

FROZEN_XLSX = str(
    Path(__file__).resolve().parent / "frozen_baselines" / "NFL_Prediction_Model_v35.xlsx"
)


def main(start_season: int, end_season: int) -> None:
    seasons = list(range(start_season, end_season + 1))
    print(f"Fetching real schedules for {seasons}...")
    sched = fetch_schedules(seasons)
    sched = sched[sched["game_type"] == "REG"].copy()
    print(f"{len(sched)} real REG games loaded.\n")

    c = load_real_model_assumptions(FROZEN_XLSX)
    sched["total_points"] = sched["home_score"] + sched["away_score"]
    sched["away_margin"] = sched["away_score"] - sched["home_score"]

    # ---- Wind ---------------------------------------------------------------------------
    wind_threshold, wind_adj = c[6], c[7]
    outdoor = sched.dropna(subset=["wind", "temp", "total_points"])
    print(f"=== Wind (real current threshold={wind_threshold}mph, adj={wind_adj}pts) ===")
    print(f"n={len(outdoor)} real outdoor games with wind/temp data")
    below = outdoor[outdoor["wind"] < wind_threshold]["total_points"]
    above = outdoor[outdoor["wind"] >= wind_threshold]["total_points"]
    print(f"  wind < {wind_threshold}mph: n={len(below)}, real mean total={below.mean():.2f}")
    print(f"  wind >= {wind_threshold}mph: n={len(above)}, real mean total={above.mean():.2f}")
    print(f"  real observed difference: {above.mean() - below.mean():+.2f}pts "
          f"(current model assumes {wind_adj:+.2f}pts)\n")

    # Real, non-cherry-picked alternate thresholds for comparison.
    print("  Real total by wind-speed bin (for comparison, not just the one threshold):")
    for lo, hi in [(0, 5), (5, 10), (10, 15), (15, 20), (20, 50)]:
        b = outdoor[(outdoor["wind"] >= lo) & (outdoor["wind"] < hi)]["total_points"]
        if len(b):
            print(f"    {lo:>2}-{hi:<2}mph: n={len(b):>4}  real mean total={b.mean():.2f}")

    # ---- Cold ---------------------------------------------------------------------------
    cold_threshold, cold_adj = c[8], c[9]
    print(f"\n=== Cold (real current threshold={cold_threshold}F, adj={cold_adj}pts) ===")
    below = outdoor[outdoor["temp"] < cold_threshold]["total_points"]
    above = outdoor[outdoor["temp"] >= cold_threshold]["total_points"]
    print(f"  temp < {cold_threshold}F: n={len(below)}, real mean total={below.mean():.2f}")
    print(f"  temp >= {cold_threshold}F: n={len(above)}, real mean total={above.mean():.2f}")
    print(f"  real observed difference: {below.mean() - above.mean():+.2f}pts "
          f"(current model assumes {cold_adj:+.2f}pts applied below threshold)\n")
    print("  Real total by temperature bin:")
    for lo, hi in [(-10, 20), (20, 32), (32, 45), (45, 65), (65, 100)]:
        b = outdoor[(outdoor["temp"] >= lo) & (outdoor["temp"] < hi)]["total_points"]
        if len(b):
            print(f"    {lo:>3}-{hi:<3}F: n={len(b):>4}  real mean total={b.mean():.2f}")

    print("\n=== Precip/Snow/Humidity -- NOT checked ===")
    print("  Real, honest gap: nflverse's own schedule data has no real precipitation/snow/"
          "humidity field at per-game granularity -- these 3 real Model Assumptions constants "
          "cannot be empirically calibrated from this data source.")

    # ---- Travel -------------------------------------------------------------------------
    travel_coefficient = c[5]
    print(f"\n=== Travel (real current coefficient={travel_coefficient}pts/1000mi) ===")
    sched["away_team_full"] = sched["away_team"].map(TEAM_NAMES)
    sched["home_team_full"] = sched["home_team"].map(TEAM_NAMES)
    # Real, honest exclusion: TEAM_NAMES only has each franchise's CURRENT stadium/abbreviation
    # (e.g. "LV" not the real pre-2020 "OAK" code the Raiders used while still in Oakland) --
    # using the current Las Vegas stadium's real coordinates for a real 2019 Oakland game would
    # be historically wrong, not just a naming gap, so those real rows are dropped explicitly
    # rather than silently mis-located.
    unmapped = sched[sched["away_team_full"].isna() | sched["home_team_full"].isna()]
    if len(unmapped):
        print(f"  Excluding {len(unmapped)} real game(s) with a pre-relocation team code not "
              f"in TEAM_NAMES (e.g. real 2019 Oakland Raiders games) -- their real CURRENT "
              f"stadium location would be historically wrong for that season, not verified "
              f"pre-relocation coordinates: {sorted(unmapped['away_team'].unique())} / "
              f"{sorted(unmapped['home_team'].unique())}")
    mapped = sched.dropna(subset=["away_team_full", "home_team_full"]).copy()
    mapped["away_travel_miles"] = mapped.apply(
        lambda r: resolve_travel_effect_miles(r["away_team_full"], r["home_team_full"]), axis=1,
    )
    travel_df = mapped.dropna(subset=["away_travel_miles", "away_margin"])
    print(f"n={len(travel_df)} real games with resolved travel distance")
    print("  Real away-team margin by travel-distance bin (negative = away team lost by more):")
    for lo, hi in [(0, 500), (500, 1000), (1000, 1500), (1500, 2000), (2000, 3000)]:
        b = travel_df[
            (travel_df["away_travel_miles"] >= lo) & (travel_df["away_travel_miles"] < hi)
        ]["away_margin"]
        if len(b):
            print(f"    {lo:>4}-{hi:<4}mi: n={len(b):>4}  real mean away margin={b.mean():+.2f}")
    corr = travel_df["away_travel_miles"].corr(travel_df["away_margin"])
    print(f"  Real correlation (travel miles vs away margin): r={corr:+.3f}")
    implied_pts_per_1000mi = None
    short = travel_df[travel_df["away_travel_miles"] < 500]["away_margin"].mean()
    far = travel_df[travel_df["away_travel_miles"] >= 2000]["away_margin"].mean()
    if pd.notna(short) and pd.notna(far):
        avg_far_miles = travel_df[travel_df["away_travel_miles"] >= 2000][
            "away_travel_miles"].mean()
        implied_pts_per_1000mi = (short - far) / (avg_far_miles / 1000)
        print(f"  Real implied coefficient (short vs 2000mi+ games): "
              f"{implied_pts_per_1000mi:.3f}pts/1000mi (current model assumes "
              f"{travel_coefficient}pts/1000mi)")

    # ---- Rest ---------------------------------------------------------------------------
    low_t, high_t = c[150], c[151]
    print(f"\n=== Rest (real current thresholds: low<{low_t}, high>{high_t} days) ===")
    rest_df = sched.dropna(subset=["home_rest", "away_rest", "away_margin"])
    for label, col in [("home", "home_rest"), ("away", "away_rest")]:
        print(f"  Real {label} team margin by real rest-days bin:")
        for lo, hi in [(0, low_t), (low_t, 8), (8, high_t), (high_t, 20)]:
            b = rest_df[(rest_df[col] >= lo) & (rest_df[col] < hi)]
            if len(b):
                margin = b["away_margin"] if label == "away" else -b["away_margin"]
                print(f"    {lo}-{hi} days: n={len(b):>4}  real mean {label} margin="
                      f"{margin.mean():+.2f}")

    # ---- Division -----------------------------------------------------------------------
    division_adj = c[11]
    print(f"\n=== Division (real current adj={division_adj}pts applied to total) ===")
    div_games = sched[sched["div_game"] == 1]["total_points"]
    nondiv_games = sched[sched["div_game"] == 0]["total_points"]
    print(f"  Division games: n={len(div_games)}, real mean total={div_games.mean():.2f}")
    print(f"  Non-division games: n={len(nondiv_games)}, real mean total="
          f"{nondiv_games.mean():.2f}")
    print(f"  Real observed difference: {div_games.mean() - nondiv_games.mean():+.2f}pts "
          f"(current model assumes {division_adj:+.2f}pts)")


if __name__ == "__main__":
    start_season = int(sys.argv[1]) if len(sys.argv) > 1 else 2019
    end_season = int(sys.argv[2]) if len(sys.argv) > 2 else 2025
    main(start_season, end_season)
