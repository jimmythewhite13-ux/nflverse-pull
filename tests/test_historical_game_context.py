"""
Tests for prediction_audit/historical/game_context.py -- pure logic, no network. Uses a real
column shape (a hand-built pandas Series matching nflverse's own real schedule row fields)
rather than a full schedule fetch, since these functions consume one real game row directly.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.core_formula_simple_terms import (  # noqa: E402
    RestEffectConstants,
    WeatherAdjConstants,
)
from prediction_audit.historical.game_context import (  # noqa: E402
    resolve_division_adj_for_game,
    resolve_rest_effect_for_game,
    resolve_weather_adj_for_game,
)

REST_CONSTANTS = RestEffectConstants(
    low_threshold=4, high_threshold=10, low_val=-1.5, mid_val=0, high_val=1,
)
WEATHER_CONSTANTS = WeatherAdjConstants(
    wind_threshold=15, wind_adj=-3, cold_threshold=32, cold_adj=-2,
    precip_adj=-2, snow_adj=-1.5, humidity_threshold=70, humidity_adj=-0.5,
)


def _row(**kwargs) -> pd.Series:
    base = {"home_rest": 7, "away_rest": 7, "div_game": 0, "roof": "outdoors",
            "temp": 60.0, "wind": 5.0}
    base.update(kwargs)
    return pd.Series(base)


def test_rest_effect_short_week_home_vs_normal_away():
    game = _row(home_rest=4, away_rest=7)
    assert resolve_rest_effect_for_game(game, REST_CONSTANTS) == pytest.approx(-1.5)


def test_rest_effect_both_normal_is_zero():
    game = _row(home_rest=7, away_rest=7)
    assert resolve_rest_effect_for_game(game, REST_CONSTANTS) == pytest.approx(0.0)


def test_division_adj_real_div_game_flag_true():
    game = _row(div_game=1)
    assert resolve_division_adj_for_game(game, -1.0) == pytest.approx(-1.0)


def test_division_adj_real_div_game_flag_false():
    game = _row(div_game=0)
    assert resolve_division_adj_for_game(game, -1.0) == pytest.approx(0.0)


def test_weather_adj_dome_is_always_zero_regardless_of_temp_wind():
    game = _row(roof="dome", temp=None, wind=None)
    assert resolve_weather_adj_for_game(game, WEATHER_CONSTANTS) == pytest.approx(0.0)


def test_weather_adj_closed_roof_is_always_zero():
    game = _row(roof="closed", temp=None, wind=None)
    assert resolve_weather_adj_for_game(game, WEATHER_CONSTANTS) == pytest.approx(0.0)


def test_weather_adj_real_high_wind_outdoor_game():
    game = _row(roof="outdoors", temp=60.0, wind=20.0)
    assert resolve_weather_adj_for_game(game, WEATHER_CONSTANTS) == pytest.approx(-3.0)


def test_weather_adj_real_cold_outdoor_game():
    game = _row(roof="outdoors", temp=20.0, wind=5.0)
    assert resolve_weather_adj_for_game(game, WEATHER_CONSTANTS) == pytest.approx(-2.0)


def test_weather_adj_real_cold_and_windy_stacks():
    game = _row(roof="outdoors", temp=20.0, wind=20.0)
    assert resolve_weather_adj_for_game(game, WEATHER_CONSTANTS) == pytest.approx(-5.0)


def test_weather_adj_mild_outdoor_game_is_zero():
    game = _row(roof="outdoors", temp=60.0, wind=5.0)
    assert resolve_weather_adj_for_game(game, WEATHER_CONSTANTS) == pytest.approx(0.0)


def test_weather_adj_returns_none_not_fabricated_zero_when_real_data_missing():
    # A real outdoor game where nflverse's own temp/wind happen to be null -- must not be
    # silently treated as "0 impact" (a real, if smaller, historical data gap).
    game = _row(roof="outdoors", temp=None, wind=None)
    assert resolve_weather_adj_for_game(game, WEATHER_CONSTANTS) is None


def test_weather_adj_open_roof_uses_real_temp_wind_when_present():
    game = _row(roof="open", temp=20.0, wind=5.0)
    assert resolve_weather_adj_for_game(game, WEATHER_CONSTANTS) == pytest.approx(-2.0)
