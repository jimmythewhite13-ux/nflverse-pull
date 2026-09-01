import pandas as pd
import pytest

from nflverse_pull.player_props import (
    compute_player_game_schedule,
    compute_player_season_catch_rate,
    compute_player_season_qb_yards_per_attempt,
    compute_player_season_target_share,
    compute_team_season_pass_rush_volume,
)


def _row(game_id, posteam, season, **kwargs):
    row = {
        "season_type": "REG", "game_id": game_id, "posteam": posteam, "season": season,
        "play_type": "pass", "pass_attempt": 0, "sack": 0, "passing_yards": 0,
        "passer_id": None, "receiver_player_id": None, "complete_pass": 0,
    }
    row.update(kwargs)
    return row


def _fake_pbp():
    # BUF, 2025, 2 real games. Game 1: 3 real pass attempts (2 to WR_A, 1 to WR_B, both
    # complete) + 1 real sack (not a real "attempt") + 2 real rush attempts. Game 2: 2 real
    # pass attempts (both to WR_A, 1 complete) + 3 real rush attempts.
    rows = [
        _row("g1", "BUF", 2025, pass_attempt=1, passer_id="QB1", receiver_player_id="WR_A",
             complete_pass=1, passing_yards=10),
        _row("g1", "BUF", 2025, pass_attempt=1, passer_id="QB1", receiver_player_id="WR_A",
             complete_pass=1, passing_yards=5),
        _row("g1", "BUF", 2025, pass_attempt=1, passer_id="QB1", receiver_player_id="WR_B",
             complete_pass=1, passing_yards=15),
        _row("g1", "BUF", 2025, sack=1, passer_id="QB1"),
        _row("g1", "BUF", 2025, play_type="run"),
        _row("g1", "BUF", 2025, play_type="run"),
        _row("g2", "BUF", 2025, pass_attempt=1, passer_id="QB1", receiver_player_id="WR_A",
             complete_pass=1, passing_yards=20),
        _row("g2", "BUF", 2025, pass_attempt=1, passer_id="QB1", receiver_player_id="WR_A",
             complete_pass=0, passing_yards=0),
        _row("g2", "BUF", 2025, play_type="run"),
        _row("g2", "BUF", 2025, play_type="run"),
        _row("g2", "BUF", 2025, play_type="run"),
    ]
    return pd.DataFrame(rows)


def test_team_season_pass_rush_volume():
    out = compute_team_season_pass_rush_volume(_fake_pbp())
    buf = out[out["Team"] == "Buffalo Bills"].iloc[0]
    # 5 real pass attempts (sack excluded) + 5 real rush attempts, over 2 real games.
    assert buf["Pass Attempts/Game"] == pytest.approx(2.5)
    assert buf["Rush Attempts/Game"] == pytest.approx(2.5)


def test_qb_yards_per_attempt_excludes_sacks():
    out = compute_player_season_qb_yards_per_attempt(_fake_pbp())
    qb = out[out["Player ID"] == "QB1"].iloc[0]
    # 5 real attempts (sack excluded), 10+5+15+20+0 = 50 real yards -> 50/5 = 10.0.
    assert qb["Y/A"] == pytest.approx(10.0)


def test_target_share():
    out = compute_player_season_target_share(_fake_pbp())
    wr_a = out[out["Player ID"] == "WR_A"].iloc[0]
    wr_b = out[out["Player ID"] == "WR_B"].iloc[0]
    # WR_A: 4 real targets / 5 real team pass attempts = 0.8. WR_B: 1/5 = 0.2.
    assert wr_a["Target Share"] == pytest.approx(0.8)
    assert wr_b["Target Share"] == pytest.approx(0.2)


def test_catch_rate():
    out = compute_player_season_catch_rate(_fake_pbp())
    wr_a = out[out["Player ID"] == "WR_A"].iloc[0]
    wr_b = out[out["Player ID"] == "WR_B"].iloc[0]
    # WR_A: 3 real completions / 4 real targets = 0.75. WR_B: 1/1 = 1.0.
    assert wr_a["Catch Rate"] == pytest.approx(0.75)
    assert wr_b["Catch Rate"] == pytest.approx(1.0)


def test_raises_on_unmapped_team():
    bad = pd.DataFrame([_row("g1", "ZZZ", 2025, play_type="run")])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_pass_rush_volume(bad)


def _fake_schedule():
    # 2 real games: BUF hosts MIA in Week 1 (BUF Home), BUF at NYJ in Week 2 (BUF Away).
    return pd.DataFrame([
        {"Week": 1, "Date": "2026-09-06", "Away Team": "Miami Dolphins",
         "Home Team": "Buffalo Bills", "Stadium": "Highmark Stadium", "Dome": False,
         "Divisional": True, "Home Rest": 7, "Away Rest": 7, "Away Travel": 1000.0},
        {"Week": 2, "Date": "2026-09-13", "Away Team": "Buffalo Bills",
         "Home Team": "New York Jets", "Stadium": "MetLife Stadium", "Dome": False,
         "Divisional": True, "Home Rest": 7, "Away Rest": 7, "Away Travel": 300.0},
    ])


def _fake_population():
    return pd.DataFrame([
        {"Team": "Buffalo Bills", "Role": "Starter", "Player Name": "QB1",
         "Player ID": "QB1", "Position": "QB"},
    ])


def test_player_game_schedule_real_week_opponent_home_away():
    out = compute_player_game_schedule(_fake_population(), _fake_schedule())
    assert len(out) == 2

    wk1 = out[out["Week"] == 1].iloc[0]
    assert wk1["Opponent"] == "Miami Dolphins"
    assert wk1["Home/Away"] == "Home"
    assert wk1["Game Key"] == "1|Miami Dolphins|Buffalo Bills"

    wk2 = out[out["Week"] == 2].iloc[0]
    assert wk2["Opponent"] == "New York Jets"
    assert wk2["Home/Away"] == "Away"
    assert wk2["Game Key"] == "2|Buffalo Bills|New York Jets"
