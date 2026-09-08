import pandas as pd
import pytest

from nflverse_pull.season_schedule import compute_roof_fallback, compute_season_schedule


def _sched_row(season, week, away, home, roof, rest_a=7, rest_h=7, div=0):
    return {
        "season": season, "week": week, "game_type": "REG", "gameday": f"2026-09-{10+week}",
        "away_team": away, "home_team": home, "roof": roof, "stadium": f"{home} Stadium",
        "div_game": div, "away_rest": rest_a, "home_rest": rest_h,
    }


def test_roof_fallback_uses_real_historical_mode():
    hist = pd.DataFrame([
        _sched_row(2023, 1, "MIA", "BUF", "outdoors"),
        _sched_row(2024, 1, "NYJ", "BUF", "outdoors"),
        _sched_row(2025, 1, "NE", "BUF", None),  # null rows excluded from the mode
        _sched_row(2023, 5, "BUF", "ARI", "dome"),
        _sched_row(2024, 5, "BUF", "ARI", "dome"),
    ])
    out = compute_roof_fallback(hist)
    assert out["BUF"] == "outdoors"
    assert out["ARI"] == "dome"


def test_season_schedule_fills_null_roof_with_fallback():
    cur = pd.DataFrame([
        _sched_row(2026, 1, "MIA", "BUF", None),  # null -- should use fallback
        _sched_row(2026, 1, "NE", "ARI", "outdoors"),  # real value present -- keep as-is
    ])
    out = compute_season_schedule(cur, 2026, {"BUF": "outdoors", "ARI": "closed"})
    buf_row = out[out["Home Team"] == "Buffalo Bills"].iloc[0]
    ari_row = out[out["Home Team"] == "Arizona Cardinals"].iloc[0]
    assert buf_row["Dome"] == False  # noqa: E712 -- fallback "outdoors" -> not a dome
    # ARI's real "outdoors" value is kept (not overwritten by the "closed" fallback, which
    # only applies to a NULL roof) -- "outdoors" is correctly not a dome either.
    assert ari_row["Dome"] == False  # noqa: E712


def test_season_schedule_real_row_count_and_no_nulls():
    cur = pd.DataFrame([
        _sched_row(2026, 1, "MIA", "BUF", "outdoors"),
        _sched_row(2026, 1, "NE", "ARI", "dome", rest_a=4, rest_h=10, div=1),
        _sched_row(2025, 1, "SF", "LA", "dome"),  # different season -- must be excluded
    ])
    out = compute_season_schedule(cur, 2026, {})
    assert len(out) == 2
    assert out.isna().sum().sum() == 0
    ari_row = out[out["Home Team"] == "Arizona Cardinals"].iloc[0]
    assert ari_row["Divisional"] == True  # noqa: E712
    assert ari_row["Away Rest"] == 4
    assert ari_row["Home Rest"] == 10


def test_season_schedule_raises_on_unmapped_team():
    cur = pd.DataFrame([_sched_row(2026, 1, "ZZZ", "BUF", "outdoors")])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_season_schedule(cur, 2026, {})


def test_season_schedule_raises_on_missing_columns():
    bad = pd.DataFrame([{"season": 2026, "week": 1}])
    with pytest.raises(ValueError, match="missing expected columns"):
        compute_season_schedule(bad, 2026, {})
