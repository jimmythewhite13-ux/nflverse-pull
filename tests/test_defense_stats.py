import pandas as pd
import pytest

from nflverse_pull.defense_stats import (
    compute_player_season_front7_stats,
    compute_player_season_secondary_stats,
    compute_team_season_front7_stats,
    compute_team_season_secondary_stats,
)


def _play(defteam, season, pass_attempt=0, sack=0, qb_hit=0, tfl=0, interception=0,
          sack_player=None, half1=None, half2=None,
          qb_hit1=None, qb_hit2=None, tfl1=None, tfl2=None,
          int_player=None, pbu1=None, pbu2=None):
    return {
        "season_type": "REG", "defteam": defteam, "season": season,
        "pass_attempt": pass_attempt, "sack": sack, "qb_hit": qb_hit,
        "tackled_for_loss": tfl, "interception": interception,
        "sack_player_id": sack_player,
        "half_sack_1_player_id": half1, "half_sack_2_player_id": half2,
        "qb_hit_1_player_id": qb_hit1, "qb_hit_2_player_id": qb_hit2,
        "tackle_for_loss_1_player_id": tfl1, "tackle_for_loss_2_player_id": tfl2,
        "interception_player_id": int_player,
        "pass_defense_1_player_id": pbu1, "pass_defense_2_player_id": pbu2,
    }


def _fake_pbp():
    """
    SF defense, 2025, faces 10 pass plays and 5 run plays (15 total defensive plays):
      - 2 of the pass plays are sacks (both credited fully to P1)
      - 1 of the pass plays has a QB hit (credited to P1 and P2, both get credit)
      - 2 of the run plays are TFLs (1 credited to P2, 1 credited to P3)

    Sack Rate = 2 sacks / 10 pass plays faced = 0.2
    QB Hit Rate = 1 qb_hit play / 10 pass plays faced = 0.1 (the play itself, not per-credit)
    TFL Rate = 2 TFL plays / 15 total defensive plays = 0.1333...

    Individual: P1 = 2.0 sacks, 0 TFL, 1 QB hit; P2 = 0 sacks, 1 TFL, 1 QB hit; P3 = 1 TFL.
    """
    rows = []
    rows.append(_play("SF", 2025, pass_attempt=1, sack=1, sack_player="P1"))
    rows.append(_play("SF", 2025, pass_attempt=1, sack=1, sack_player="P1"))
    rows.append(_play("SF", 2025, pass_attempt=1, qb_hit=1, qb_hit1="P1", qb_hit2="P2"))
    for _ in range(7):
        rows.append(_play("SF", 2025, pass_attempt=1))
    rows.append(_play("SF", 2025, tfl=1, tfl1="P2"))
    rows.append(_play("SF", 2025, tfl=1, tfl1="P3"))
    for _ in range(3):
        rows.append(_play("SF", 2025))
    return pd.DataFrame(rows)


def test_team_front7_stats_computes_expected_rates():
    out = compute_team_season_front7_stats(_fake_pbp())
    assert len(out) == 1
    row = out.iloc[0]
    assert row["Team"] == "San Francisco 49ers"
    assert row["Sack Rate"] == pytest.approx(0.2)
    assert row["QB Hit Rate"] == pytest.approx(0.1)
    assert row["TFL Rate"] == pytest.approx(2 / 15)


def test_team_front7_stats_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([_play("ZZZ", 2025, pass_attempt=1)])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_front7_stats(df)


def test_player_front7_stats_credits_full_and_half_sacks_correctly():
    """
    P1 gets 2 full sacks (2.0) plus a half-sack shared with P2 (0.5 each) -- total P1 = 2.5,
    P2 = 0.5. Matches the NFL's own official split-sack crediting convention.
    """
    rows = [
        _play("SF", 2025, pass_attempt=1, sack=1, sack_player="P1"),
        _play("SF", 2025, pass_attempt=1, sack=1, sack_player="P1"),
        _play("SF", 2025, pass_attempt=1, sack=1, half1="P1", half2="P2"),
    ]
    out = compute_player_season_front7_stats(pd.DataFrame(rows)).set_index("Player ID")
    assert out.loc["P1", "Sacks"] == pytest.approx(2.5)
    assert out.loc["P2", "Sacks"] == pytest.approx(0.5)
    assert out.loc["P1", "Team"] == "San Francisco 49ers"


def test_player_front7_stats_credits_both_players_on_a_shared_qb_hit_or_tfl():
    rows = [
        _play("MIA", 2025, pass_attempt=1, qb_hit=1, qb_hit1="P1", qb_hit2="P2"),
        _play("MIA", 2025, tfl=1, tfl1="P3", tfl2="P4"),
    ]
    out = compute_player_season_front7_stats(pd.DataFrame(rows)).set_index("Player ID")
    assert out.loc["P1", "QB Hits"] == 1.0
    assert out.loc["P2", "QB Hits"] == 1.0
    assert out.loc["P3", "TFL"] == 1.0
    assert out.loc["P4", "TFL"] == 1.0


def _fake_secondary_pbp():
    """
    SF defense, 2025, faces 10 pass plays:
      - 2 are interceptions (both credited to P1)
      - 3 are pass breakups (2 credited solely to P2, 1 shared between P2 and P3)

    INT Rate = 2 / 10 = 0.2
    PBU Rate = 3 plays / 10 = 0.3 (the play itself, not per-credit)
    Individual: P1 = 2 INT; P2 = 3 PBU (full credit on each, including the shared one);
    P3 = 1 PBU (also full credit on the shared play, not split like a half-sack).
    """
    rows = [
        _play("SF", 2025, pass_attempt=1, interception=1, int_player="P1"),
        _play("SF", 2025, pass_attempt=1, interception=1, int_player="P1"),
        _play("SF", 2025, pass_attempt=1, pbu1="P2"),
        _play("SF", 2025, pass_attempt=1, pbu1="P2"),
        _play("SF", 2025, pass_attempt=1, pbu1="P2", pbu2="P3"),
    ]
    rows += [_play("SF", 2025, pass_attempt=1) for _ in range(5)]
    return pd.DataFrame(rows)


def test_team_secondary_stats_computes_expected_rates():
    out = compute_team_season_secondary_stats(_fake_secondary_pbp())
    assert len(out) == 1
    row = out.iloc[0]
    assert row["Team"] == "San Francisco 49ers"
    assert row["INT Rate"] == pytest.approx(0.2)
    assert row["PBU Rate"] == pytest.approx(0.3)


def test_team_secondary_stats_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([_play("ZZZ", 2025, pass_attempt=1)])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_secondary_stats(df)


def test_player_secondary_stats_credits_int_and_shared_pbu_correctly():
    out = compute_player_season_secondary_stats(_fake_secondary_pbp()).set_index("Player ID")
    assert out.loc["P1", "INT"] == 2.0
    assert out.loc["P2", "PBU"] == 3.0  # full credit on all 3, including the shared play
    assert out.loc["P3", "PBU"] == 1.0  # full credit too -- PBU isn't split like a half-sack
    assert out.loc["P1", "Team"] == "San Francisco 49ers"
