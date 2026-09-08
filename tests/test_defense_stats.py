import pandas as pd
import pytest

from nflverse_pull.defense_stats import (
    MIN_QUALIFYING_DEFENSIVE_SNAPS,
    compute_player_season_defensive_rates,
    compute_player_season_defensive_snaps,
    compute_player_season_front7_stats,
    compute_player_season_secondary_stats,
    compute_player_season_tackle_stats,
    compute_team_season_front7_stats,
    compute_team_season_participation_context,
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


def _participation_pbp_row(
    defteam, season, pass_attempt, number_of_pass_rushers, defenders_in_box, play_type="pass",
):
    return {
        "season_type": "REG", "defteam": defteam, "season": season,
        "pass_attempt": pass_attempt, "number_of_pass_rushers": number_of_pass_rushers,
        "defenders_in_box": defenders_in_box, "play_type": play_type,
    }


def test_participation_context_computes_blitz_rate_and_avg_box_count():
    """
    SF defense, 2025: 4 pass plays faced (2 with 5+ rushers = blitzed, 2 not) + 1 run play
    (box count only, no pass rusher count on a run play).
    Blitz Rate = 2/4 = 0.5 (share of PASS plays with >= BLITZ_MIN_PASS_RUSHERS (5) rushers).
    Avg Box Count = mean across all 5 real SCRIMMAGE plays = (6+7+6+6+7)/5 = 6.4.
    """
    rows = [
        _participation_pbp_row("SF", 2025, 1, 5, 6, play_type="pass"),
        _participation_pbp_row("SF", 2025, 1, 6, 7, play_type="pass"),
        _participation_pbp_row("SF", 2025, 1, 4, 6, play_type="pass"),
        _participation_pbp_row("SF", 2025, 1, 3, 6, play_type="pass"),
        _participation_pbp_row("SF", 2025, 0, None, 7, play_type="run"),
    ]
    out = compute_team_season_participation_context(pd.DataFrame(rows)).set_index("Team")
    row = out.loc["San Francisco 49ers"]
    assert row["Blitz Rate"] == pytest.approx(0.5)
    assert row["Avg Box Count"] == pytest.approx((6 + 7 + 6 + 6 + 7) / 5)


def test_participation_context_excludes_special_teams_plays_from_avg_box_count():
    # Real bug caught while verifying this against a direct nflverse pull: defenders_in_box
    # is 0 (not null) on kickoffs/punts/etc. -- a real "0" would silently deflate every
    # team's Avg Box Count if those rows weren't excluded. A kickoff with defenders_in_box=0
    # must NOT pull the average down to include it.
    rows = [
        _participation_pbp_row("SF", 2025, 1, 5, 6, play_type="pass"),
        _participation_pbp_row("SF", 2025, 1, 5, 8, play_type="run"),
        _participation_pbp_row("SF", 2025, 0, None, 0, play_type="kickoff"),
        _participation_pbp_row("SF", 2025, 0, None, 0, play_type="punt"),
        _participation_pbp_row("SF", 2025, 0, None, 0, play_type="extra_point"),
    ]
    out = compute_team_season_participation_context(pd.DataFrame(rows)).set_index("Team")
    # Real scrimmage-play average only: (6+8)/2 = 7.0, NOT dragged down by the 0's.
    assert out.loc["San Francisco 49ers", "Avg Box Count"] == pytest.approx(7.0)


def test_participation_context_blitz_threshold_is_5_plus_not_4():
    # Exactly 4 pass rushers (the league-modal count, verified live) must NOT count as a
    # blitz -- only 5+ does, per BLITZ_MIN_PASS_RUSHERS's own documented definition.
    rows = [
        _participation_pbp_row("SF", 2025, 1, 4, 6),
        _participation_pbp_row("SF", 2025, 1, 5, 6),
    ]
    out = compute_team_season_participation_context(pd.DataFrame(rows)).set_index("Team")
    assert out.loc["San Francisco 49ers", "Blitz Rate"] == pytest.approx(0.5)


def test_participation_context_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([_participation_pbp_row("ZZZ", 2025, 1, 5, 6)])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_participation_context(df)


def _tackle_play(defteam, season, solo1=None, solo2=None, twa1=None,
                  assist1=None, assist2=None, assist3=None, assist4=None):
    return {
        "season_type": "REG", "defteam": defteam, "season": season,
        "solo_tackle_1_player_id": solo1, "solo_tackle_2_player_id": solo2,
        "tackle_with_assist_1_player_id": twa1,
        "assist_tackle_1_player_id": assist1, "assist_tackle_2_player_id": assist2,
        "assist_tackle_3_player_id": assist3, "assist_tackle_4_player_id": assist4,
    }


def test_tackle_stats_credits_solo_and_assist_at_full_weight():
    """
    SF defense, 2025:
      - P1 gets 2 solo tackles (solo_tackle_1_player_id).
      - P2 makes a tackle WITH an assist -- credited via tackle_with_assist_1_player_id
        (real quirk: solo_tackle_1_player_id is null on this play), P3 gets the assist.
    P1 = 2 tackles, P2 = 1 tackle, P3 = 1 tackle (assist counts full weight, not split).
    """
    rows = [
        _tackle_play("SF", 2025, solo1="P1"),
        _tackle_play("SF", 2025, solo1="P1"),
        _tackle_play("SF", 2025, twa1="P2", assist1="P3"),
    ]
    out = compute_player_season_tackle_stats(pd.DataFrame(rows)).set_index("Player ID")
    assert out.loc["P1", "Tackles"] == 2.0
    assert out.loc["P2", "Tackles"] == 1.0
    assert out.loc["P3", "Tackles"] == 1.0
    assert out.loc["P1", "Team"] == "San Francisco 49ers"


def test_tackle_stats_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([_tackle_play("ZZZ", 2025, solo1="P1")])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_player_season_tackle_stats(df)


def _snap_row(pfr_player_id, season, defense_snaps, game_type="REG"):
    return {"pfr_player_id": pfr_player_id, "season": season,
            "defense_snaps": defense_snaps, "game_type": game_type}


def _id_row(pfr_id, gsis_id):
    return {"pfr_id": pfr_id, "gsis_id": gsis_id}


def test_defensive_snaps_sums_real_season_total_and_joins_gsis_id():
    snaps = pd.DataFrame([
        _snap_row("SmitJo01", 2025, 40),
        _snap_row("SmitJo01", 2025, 35),
        _snap_row("SmitJo01", 2025, 0),  # a real game with 0 defensive snaps -- excluded
        _snap_row("JoneMi01", 2025, 20, game_type="POST"),  # postseason -- excluded
    ])
    ids = pd.DataFrame([_id_row("SmitJo01", "00-1111111"), _id_row("JoneMi01", "00-2222222")])

    out = compute_player_season_defensive_snaps(snaps, ids).set_index("Player ID")
    assert out.loc["00-1111111", "Defensive Snaps"] == 75
    assert "00-2222222" not in out.index  # only a postseason row -- no real REG total


def test_defensive_snaps_drops_unmatched_players():
    snaps = pd.DataFrame([_snap_row("GhosPl01", 2025, 100)])
    ids = pd.DataFrame([_id_row("SmitJo01", "00-1111111")])  # no match for GhosPl01

    out = compute_player_season_defensive_snaps(snaps, ids)
    assert len(out) == 0


def test_defensive_rates_converts_to_per_snap_and_excludes_below_threshold():
    assert MIN_QUALIFYING_DEFENSIVE_SNAPS == 200
    raw = pd.DataFrame([
        {"Player ID": "P1", "Season": 2025, "Team": "Buffalo Bills", "Sacks": 8.0},
        {"Player ID": "P2", "Season": 2025, "Team": "Buffalo Bills", "Sacks": 1.0},
    ])
    snaps = pd.DataFrame([
        {"Player ID": "P1", "Season": 2025, "Defensive Snaps": 400},  # qualifies
        {"Player ID": "P2", "Season": 2025, "Defensive Snaps": 50},  # below threshold
    ])
    rosters = pd.DataFrame([
        {"player_id": "P1", "season": 2025, "entry_year": 2020},
    ])

    out = compute_player_season_defensive_rates(raw, ["Sacks"], snaps, rosters)
    assert len(out) == 1  # P2 excluded, not zero-filled
    assert out.iloc[0]["Player ID"] == "P1"
    assert out.iloc[0]["Sacks Rate"] == pytest.approx(8.0 / 400)
    assert out.iloc[0]["Is Rookie Season"] == False  # noqa: E712 (numpy bool from merge)


def test_defensive_rates_drops_player_season_with_no_real_snap_match():
    raw = pd.DataFrame([
        {"Player ID": "P1", "Season": 2025, "Team": "Buffalo Bills", "Sacks": 8.0},
    ])
    snaps = pd.DataFrame(columns=["Player ID", "Season", "Defensive Snaps"])
    rosters = pd.DataFrame(columns=["player_id", "season", "entry_year"])

    out = compute_player_season_defensive_rates(raw, ["Sacks"], snaps, rosters)
    assert len(out) == 0
