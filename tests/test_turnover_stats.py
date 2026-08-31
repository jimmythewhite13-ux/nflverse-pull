import pandas as pd
import pytest

from nflverse_pull.turnover_stats import (
    REDZONE_OUTPUT_COLUMNS,
    TURNOVER_OUTPUT_COLUMNS,
    compute_team_season_redzone_components,
    compute_team_season_turnover_components,
)


def _base_row(posteam, defteam, season, play_type, **kwargs):
    row = {
        "season_type": "REG", "posteam": posteam, "defteam": defteam, "season": season,
        "play_type": play_type, "pass_attempt": 0, "sack": 0, "interception": 0,
        "fumble": 0, "fumble_forced": 0, "fumble_lost": 0, "fumbled_1_team": None,
        "fumble_recovery_1_team": None,
    }
    row.update(kwargs)
    return row


def _fake_turnover_pbp():
    """
    BUF offense vs MIA defense, 2025:
      - 10 real pass attempts (excl. sacks), 2 of which are real INTs thrown by BUF
        (intercepted BY MIA). INT Rate Thrown (BUF) = 2/10 = 0.2. Also feeds MIA's real
        takeaway count (2) via defteam.
      - 20 real scrimmage plays for BUF offense (10 pass attempts above + 10 more real
        plays, used as the Fumble Lost Rate denominator), 20 for MIA defense (same games).
      - 1 real fumble: BUF fumbles its own snap (fumbled_1_team=BUF), forced by MIA
        (fumble_forced=1), recovered by MIA (fumble_recovery_1_team=MIA) -- a real ordinary
        turnover-fumble. Fumble Lost Rate (BUF) = 1/20 = 0.05. Fumble Forced Rate (MIA) =
        1/20 = 0.05.
      - 1 real fumble BUF recovers itself (fumbled_1_team=BUF, fumble_recovery_1_team=BUF,
        fumble_forced=0) -- an "ordinary" fumble but NOT lost (excluded from Fumble Lost
        Rate's numerator) and NOT a takeaway/giveaway event.
      Fumble Recovery Rate: BUF was involved in 2 real fumbles (both fumbled_1_team=BUF),
      recovered 1 of them -> 1/2 = 0.5. MIA was involved in the SAME 2 real fumbles (it's
      the defteam on both), recovered 1 of them (the lost one, not the BUF-recovers-itself
      one) -> 1/2 = 0.5.
      Actual Turnover Differential: BUF gave away 2 INTs + 1 fumble = 3 giveaways, 0
      takeaways -> -3. MIA gained 2 INTs + 1 fumble = 3 takeaways, 0 giveaways -> +3.
    """
    rows = []
    # 8 clean completions (not INTs)
    for _ in range(8):
        rows.append(_base_row("BUF", "MIA", 2025, "pass", pass_attempt=1))
    # 2 real INTs thrown by BUF, intercepted by MIA
    for _ in range(2):
        rows.append(_base_row("BUF", "MIA", 2025, "pass", pass_attempt=1, interception=1))
    # 10 more real scrimmage plays (runs) padding out the offensive/defensive play counts
    for _ in range(8):
        rows.append(_base_row("BUF", "MIA", 2025, "run"))
    # 1 real ordinary ordinary lost fumble: BUF fumbles, MIA forces + recovers
    rows.append(_base_row(
        "BUF", "MIA", 2025, "run", fumble=1, fumble_forced=1, fumble_lost=1,
        fumbled_1_team="BUF", fumble_recovery_1_team="MIA",
    ))
    # 1 real fumble BUF recovers itself (not forced, not lost)
    rows.append(_base_row(
        "BUF", "MIA", 2025, "run", fumble=1, fumble_forced=0, fumble_lost=0,
        fumbled_1_team="BUF", fumble_recovery_1_team="BUF",
    ))
    return pd.DataFrame(rows)


def test_turnover_components_computes_expected_rates():
    out = compute_team_season_turnover_components(_fake_turnover_pbp())

    assert list(out.columns) == TURNOVER_OUTPUT_COLUMNS

    buf = out[out["Team"] == "Buffalo Bills"].iloc[0]
    assert buf["INT Rate Thrown (Off)"] == pytest.approx(2 / 10)
    assert buf["Fumble Lost Rate (Off)"] == pytest.approx(1 / 20)
    assert buf["Fumble Recovery Rate"] == pytest.approx(0.5)
    assert buf["Actual Turnover Differential"] == pytest.approx(-3.0)

    mia = out[out["Team"] == "Miami Dolphins"].iloc[0]
    assert mia["Fumble Forced Rate (Def)"] == pytest.approx(1 / 20)
    # MIA is the defteam on BOTH real fumbles in this fixture (the lost one AND the one BUF
    # recovers itself) -- involved in 2, recovered 1 -> 0.5, not 1.0.
    assert mia["Fumble Recovery Rate"] == pytest.approx(0.5)
    assert mia["Actual Turnover Differential"] == pytest.approx(3.0)


def test_turnover_differential_is_real_zero_sum():
    out = compute_team_season_turnover_components(_fake_turnover_pbp())
    assert out["Actual Turnover Differential"].sum() == pytest.approx(0.0)


def test_turnover_components_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([_base_row("ZZZ", "MIA", 2025, "pass", pass_attempt=1)])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_turnover_components(df)


def _drive_row(game_id, posteam, drive, season, inside20, result, yardline_100=50,
                goal_to_go=0, epa=0.0):
    return {
        "season_type": "REG", "game_id": game_id, "posteam": posteam, "season": season,
        "play_type": "run", "drive": drive, "drive_inside20": inside20,
        "fixed_drive_result": result, "yardline_100": yardline_100,
        "goal_to_go": goal_to_go, "epa": epa,
    }


def _fake_redzone_pbp():
    """
    BUF, 2025, two DIFFERENT real games sharing the same drive NUMBER (drive=3) -- the real
    bug this module's own docstring documents catching: grouping by (posteam, season, drive)
    alone would wrongly merge these into one drive. Grouping by (game_id, posteam, drive)
    keeps them separate real drives:
      - Game 1, drive 3: reaches the red zone (inside20=1), ends in a real Touchdown, with
        one real goal-to-go play (yardline_100=3) also ending in that same Touchdown.
      - Game 2, drive 3: reaches the red zone (inside20=1), ends in a real Field goal (no
        goal-to-go play).
      - Game 1, drive 5: does NOT reach the red zone (inside20=0), ends in a Punt --
        excluded from both the red-zone and goal-to-go counts entirely.
    Red-Zone Drive Count = 2, Red-Zone TD% = 1/2 = 0.5. Goal-to-Go Drive Count = 1,
    Goal-to-Go TD% = 1/1 = 1.0. Red-Zone EPA = mean EPA of real PLAYS (not drives) with
    yardline_100<=20 -- only the yardline_100=3 (epa=1.5) and yardline_100=18 (epa=0.2)
    rows qualify; the yardline_100=25 row is a real play from the SAME red-zone-reaching
    drive but is itself outside the red zone, so it's correctly excluded -> (1.5+0.2)/2.
    """
    rows = [
        _drive_row("2025_01_BUF_X", "BUF", 3, 2025, 1, "Touchdown", yardline_100=25, epa=0.5),
        _drive_row("2025_01_BUF_X", "BUF", 3, 2025, 1, "Touchdown", yardline_100=3,
                   goal_to_go=1, epa=1.5),
        _drive_row("2025_02_BUF_Y", "BUF", 3, 2025, 1, "Field goal", yardline_100=18, epa=0.2),
        _drive_row("2025_01_BUF_X", "BUF", 5, 2025, 0, "Punt", yardline_100=60, epa=-0.3),
    ]
    return pd.DataFrame(rows)


def test_redzone_components_uses_game_id_not_just_drive_number():
    out = compute_team_season_redzone_components(_fake_redzone_pbp())
    assert list(out.columns) == REDZONE_OUTPUT_COLUMNS

    buf = out[out["Team"] == "Buffalo Bills"].iloc[0]
    assert buf["Red-Zone Drive Count"] == 2
    assert buf["Red-Zone TD%"] == pytest.approx(0.5)
    assert buf["Goal-to-Go Drive Count"] == 1
    assert buf["Goal-to-Go TD%"] == pytest.approx(1.0)
    assert buf["Red-Zone EPA"] == pytest.approx((1.5 + 0.2) / 2)


def test_redzone_components_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([_drive_row("g1", "ZZZ", 1, 2025, 1, "Touchdown")])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_redzone_components(df)
