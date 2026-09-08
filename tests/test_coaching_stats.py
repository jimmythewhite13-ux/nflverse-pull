import pandas as pd
import pytest

from nflverse_pull.coaching_stats import (
    compute_coach_season_stats,
    compute_current_coach_by_team,
    compute_game_coach_map,
)


def _sched_row(game_id, season, home_team, away_team, home_coach, away_coach):
    return {
        "game_id": game_id, "season": season, "game_type": "REG",
        "home_team": home_team, "away_team": away_team,
        "home_coach": home_coach, "away_coach": away_coach,
    }


def _fake_schedule():
    # BUF hosts MIA under Coach A (BUF) / Coach B (MIA), one 2025 game -- simple case.
    # CAR's own 2023 season is split: Coach C ran CAR's game 1, Coach D ran CAR's game 2
    # (a real in-season interim change, mirroring the real CAR/LAC/LV 2023 cases).
    return pd.DataFrame([
        _sched_row("2025_01_MIA_BUF", 2025, "BUF", "MIA", "Coach A", "Coach B"),
        _sched_row("2023_01_CAR_ATL", 2023, "ATL", "CAR", "Coach X", "Coach C"),
        _sched_row("2023_05_CAR_NO", 2023, "NO", "CAR", "Coach Y", "Coach D"),
    ])


def test_game_coach_map_real_abbreviations_not_full_names():
    out = compute_game_coach_map(_fake_schedule())
    assert len(out) == 6  # 2 teams/game x 3 games
    row = out[(out["game_id"] == "2025_01_MIA_BUF") & (out["team_abbr"] == "BUF")].iloc[0]
    assert row["coach"] == "Coach A"
    assert row["Team"] == "Buffalo Bills"  # full name still carried, for downstream lookups


def test_game_coach_map_raises_on_unmapped_team():
    bad = pd.DataFrame([_sched_row("g1", 2025, "ZZZ", "MIA", "Coach A", "Coach B")])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_game_coach_map(bad)


def _pbp_row(game_id, posteam, defteam, **kwargs):
    row = {
        "game_id": game_id, "posteam": posteam, "defteam": defteam,
        "play_type": "run", "down": None, "ydstogo": None, "qtr": 1, "game_half": "Half1",
        "epa": 0.0, "penalty": 0, "penalty_team": None,
    }
    row.update(kwargs)
    return row


def _fake_pbp_mid_season_change():
    rows = []
    # CAR game 1 (Coach C in charge): 2 real 4th-and-1 decisions, both go-for-it.
    for _ in range(2):
        rows.append(_pbp_row(
            "2023_01_CAR_ATL", "CAR", "ATL", play_type="pass", down=4, ydstogo=1, epa=0.3,
        ))
    # CAR game 2 (Coach D in charge): 1 real 4th-and-1 decision, a punt (did not go).
    rows.append(_pbp_row(
        "2023_05_CAR_NO", "CAR", "NO", play_type="punt", down=4, ydstogo=1, epa=-0.2,
    ))
    return pd.DataFrame(rows)


def test_coach_season_stats_attributes_midseason_change_at_game_precision():
    gcm = compute_game_coach_map(_fake_schedule())
    stats = compute_coach_season_stats(_fake_pbp_mid_season_change(), gcm)
    c = stats[stats["Coach"] == "Coach C"].iloc[0]
    d = stats[stats["Coach"] == "Coach D"].iloc[0]
    # Coach C's game: both real 4th-and-1 decisions were go-for-it -> Go Rate 1.0.
    assert c["4th Down Go Rate (Short)"] == pytest.approx(1.0)
    assert c["4th-and-Short Attempts"] == 2
    # Coach D's game: the one real 4th-and-1 decision was a punt -> Go Rate 0.0.
    assert d["4th Down Go Rate (Short)"] == pytest.approx(0.0)
    assert d["4th-and-Short Attempts"] == 1
    # Coach D's real game is NOT attributed to Coach C, and vice versa -- the whole point
    # of joining on game_id rather than a season-majority approximation.
    assert c["Team"] == "Carolina Panthers"
    assert d["Team"] == "Carolina Panthers"


def _fake_full_metric_pbp():
    # BUF (Coach A) vs MIA (Coach B), 2025, one game -- exercises every metric at once,
    # including BOTH sides of the ball for BUF (offensive AND defensive Q1 snaps), since
    # 1Q Net EPA needs both to be non-null.
    rows = []
    # BUF's own Q1 offense: 2 plays, epa 0.4 and 0.2 -> mean 0.3.
    rows.append(_pbp_row("2025_01_MIA_BUF", "BUF", "MIA", play_type="pass", qtr=1, epa=0.4))
    rows.append(_pbp_row("2025_01_MIA_BUF", "BUF", "MIA", play_type="run", qtr=1, epa=0.2))
    # MIA's own Q1 offense (BUF on defense, defteam=BUF): 1 play, epa 0.1 -> BUF's own real
    # Q1 defensive EPA allowed = 0.1. BUF's 1Q Net EPA = 0.3 (own offense) - 0.1 (own
    # defense allowed) = 0.2.
    rows.append(_pbp_row("2025_01_MIA_BUF", "MIA", "BUF", play_type="pass", qtr=1, epa=0.1))
    # BUF's own 2nd-half offense: 1 play, epa 0.6; BUF's own 1st-half offense is the 2 Q1
    # plays above (mean 0.3) -> 2H Delta = 0.6 - 0.3 = 0.3.
    rows.append(_pbp_row(
        "2025_01_MIA_BUF", "BUF", "MIA", play_type="pass", qtr=3, game_half="Half2", epa=0.6,
    ))
    # 1 real accepted penalty ON BUF (BUF is posteam here, penalty_team=BUF) -- play_type
    # "punt" so it counts toward Total Plays and the penalty numerator (neither filters by
    # play_type) WITHOUT also entering any of the run/pass-only EPA averages above (its own
    # epa=0.0 default would otherwise silently pull those means off their expected values).
    rows.append(_pbp_row(
        "2025_01_MIA_BUF", "BUF", "MIA", play_type="punt", penalty=1, penalty_team="BUF",
    ))
    return pd.DataFrame(rows)


def test_coach_season_stats_1q_epa_2h_delta_and_penalty_rate():
    gcm = compute_game_coach_map(_fake_schedule())
    stats = compute_coach_season_stats(_fake_full_metric_pbp(), gcm)
    a = stats[stats["Coach"] == "Coach A"].iloc[0]  # BUF's coach

    # 1Q Net EPA = 0.3 (BUF's own Q1 offense) - 0.1 (BUF's own Q1 defense allowed) = 0.2.
    assert a["1Q Net EPA/Play"] == pytest.approx(0.2)

    # 2H Delta = 0.6 (2H offense) - 0.3 (1H offense) = 0.3.
    assert a["2H EPA Delta"] == pytest.approx(0.3)

    # BUF's Total Plays = 4 real offensive plays (posteam=BUF) + 1 real defensive play
    # (defteam=BUF) = 5. Penalty Rate = 1 real penalty on BUF / 5 = 0.2.
    assert a["Total Plays"] == 5
    assert a["Penalty Rate"] == pytest.approx(1 / 5)


def test_current_coach_by_team():
    out = compute_current_coach_by_team(_fake_schedule(), 2025)
    row = out[out["Team"] == "Buffalo Bills"].iloc[0]
    assert row["Coach"] == "Coach A"
    assert set(out["Team"]) == {"Buffalo Bills", "Miami Dolphins"}
