import pandas as pd
import pytest

from nflverse_pull.rookie_crosswalk import (
    TIER_LATE,
    TIER_MID,
    TIER_TOP,
    assign_historical_tier,
    assign_rookie_assumptions,
    compute_historical_tier_averages,
    rank_rookie_class,
)


def test_assign_historical_tier_boundaries():
    assert assign_historical_tier(1) == TIER_TOP
    assert assign_historical_tier(2) == TIER_MID
    assert assign_historical_tier(3) == TIER_MID
    assert assign_historical_tier(4) == TIER_LATE
    assert assign_historical_tier(7) == TIER_LATE
    assert assign_historical_tier(None) == TIER_LATE
    assert assign_historical_tier(float("nan")) == TIER_LATE


def test_compute_historical_tier_averages_hand_computed():
    """
    Two Round-1 (Tier 1) rookies with EPA 0.10 and 0.20 -> tier average 0.15.
    One Round-2 (Tier 2) rookie with EPA -0.05 -> tier average -0.05 (sample size 1).
    Zero Tier-3 rookies -> average is None (0 sample size), not zero/fabricated.
    """
    rookie_stats = pd.DataFrame([
        {"Player ID": "P1", "EPA/Play": 0.10},
        {"Player ID": "P2", "EPA/Play": 0.20},
        {"Player ID": "P3", "EPA/Play": -0.05},
    ])
    draft_info = pd.DataFrame([
        {"gsis_id": "P1", "draft_round": 1.0},
        {"gsis_id": "P2", "draft_round": 1.0},
        {"gsis_id": "P3", "draft_round": 2.0},
    ])

    out = compute_historical_tier_averages(
        rookie_stats, draft_info, ["EPA/Play"]
    ).set_index("Historical Tier")

    assert out.loc[TIER_TOP, "EPA/Play"] == pytest.approx(0.15)
    assert out.loc[TIER_TOP, "Sample Size"] == 2
    assert out.loc[TIER_MID, "EPA/Play"] == pytest.approx(-0.05)
    assert out.loc[TIER_MID, "Sample Size"] == 1
    assert out.loc[TIER_LATE, "Sample Size"] == 0
    # A None assigned into an otherwise-float column comes back as NaN (pandas dtype
    # coercion), not a literal None -- pd.isna() is the correct check either way.
    assert pd.isna(out.loc[TIER_LATE, "EPA/Play"])


def test_compute_historical_tier_averages_undrafted_player_falls_to_late_tier():
    rookie_stats = pd.DataFrame([{"Player ID": "P1", "EPA/Play": 0.5}])
    draft_info = pd.DataFrame([{"gsis_id": "P2", "draft_round": 1.0}])  # P1 has no draft row

    out = compute_historical_tier_averages(
        rookie_stats, draft_info, ["EPA/Play"]
    ).set_index("Historical Tier")
    assert out.loc[TIER_LATE, "Sample Size"] == 1
    assert out.loc[TIER_LATE, "EPA/Play"] == pytest.approx(0.5)


def test_rank_rookie_class_thirds_with_three_players():
    # ADP: lower is better. A=1.0 (best), B=2.0, C=3.0 (worst).
    market = pd.DataFrame([
        {"name": "A", "adp": 1.0}, {"name": "B", "adp": 2.0}, {"name": "C", "adp": 3.0},
    ])
    out = rank_rookie_class(market, rank_col="adp", ascending=True).set_index("Player Name")

    assert out.loc["A", "Position Rank"] == 1
    assert out.loc["A", "Percentile"] == pytest.approx(100.0)
    assert out.loc["A", "Assumption Tier"] == TIER_TOP
    assert out.loc["B", "Percentile"] == pytest.approx(200 / 3)
    assert out.loc["B", "Assumption Tier"] == TIER_MID
    assert out.loc["C", "Percentile"] == pytest.approx(100 / 3)
    assert out.loc["C", "Assumption Tier"] == TIER_LATE


def test_rank_rookie_class_empty_input_returns_empty_not_error():
    out = rank_rookie_class(pd.DataFrame(columns=["name", "adp"]), rank_col="adp", ascending=True)
    assert len(out) == 0


def test_assign_rookie_assumptions_uses_tier_average_when_available():
    ranking = pd.DataFrame([{"Player Name": "R.Star", "Assumption Tier": TIER_TOP}])
    tiers = pd.DataFrame([
        {"Historical Tier": TIER_TOP, "Sample Size": 5, "EPA/Play": 0.12},
        {"Historical Tier": TIER_MID, "Sample Size": 3, "EPA/Play": -0.02},
        {"Historical Tier": TIER_LATE, "Sample Size": 0, "EPA/Play": None},
    ])
    flat_baseline = {"EPA/Play": -0.10}

    out = assign_rookie_assumptions(
        ranking, tiers, ["EPA/Play"], flat_baseline, all_rookie_names=["R.Star"]
    ).set_index("Player Name")

    assert out.loc["R.Star", "EPA/Play"] == pytest.approx(0.12)
    assert out.loc["R.Star", "Source"] == "market-informed tier average"


def test_assign_rookie_assumptions_falls_back_to_flat_baseline_when_missing_from_market():
    ranking = pd.DataFrame([{"Player Name": "R.Star", "Assumption Tier": TIER_TOP}])
    tiers = pd.DataFrame([{"Historical Tier": TIER_TOP, "Sample Size": 5, "EPA/Play": 0.12}])
    flat_baseline = {"EPA/Play": -0.10}

    # R.Ghost never appears in the market ranking at all (no ADP/trade-value data found).
    out = assign_rookie_assumptions(
        ranking, tiers, ["EPA/Play"], flat_baseline, all_rookie_names=["R.Star", "R.Ghost"]
    ).set_index("Player Name")

    assert out.loc["R.Ghost", "EPA/Play"] == pytest.approx(-0.10)
    assert "flat Rookie Baseline" in out.loc["R.Ghost", "Source"]


def test_assign_rookie_assumptions_falls_back_when_tier_has_zero_sample():
    # R.Star ranks into Tier 3, but Tier 3 has no historical examples at all -- must not
    # silently produce a None/NaN assumption; falls back to the flat baseline instead.
    ranking = pd.DataFrame([{"Player Name": "R.Star", "Assumption Tier": TIER_LATE}])
    tiers = pd.DataFrame([{"Historical Tier": TIER_LATE, "Sample Size": 0, "EPA/Play": None}])
    flat_baseline = {"EPA/Play": -0.10}

    out = assign_rookie_assumptions(
        ranking, tiers, ["EPA/Play"], flat_baseline, all_rookie_names=["R.Star"]
    ).set_index("Player Name")

    assert out.loc["R.Star", "EPA/Play"] == pytest.approx(-0.10)
    assert "flat Rookie Baseline" in out.loc["R.Star", "Source"]
