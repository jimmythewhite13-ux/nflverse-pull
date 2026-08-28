import pandas as pd
import pytest

from nflverse_pull.qb_stats import (
    MIN_QUALIFYING_DROPBACKS,
    SEASON_STATS_COLUMNS,
    compute_qb_roles,
    compute_team_season_qb_stats,
)


def _filler_rows(n: int, passer_id: str, passer: str, season: int, posteam: str) -> list[dict]:
    """n identical simple completions: pass_attempt=1, epa=0.1, cpoe=5.0, 5 yards, no TD/INT."""
    return [
        {"season_type": "REG", "season": season, "posteam": posteam,
         "passer_id": passer_id, "passer": passer,
         "passer_player_id": passer_id, "passer_player_name": passer,
         "qb_dropback": 1, "pass_attempt": 1, "sack": 0, "qb_scramble": 0,
         "epa": 0.1, "cpoe": 5.0, "passing_yards": 5, "yards_gained": 5,
         "pass_touchdown": 0, "interception": 0}
        for _ in range(n)
    ]


def _fake_pbp():
    """
    QB1 "A.Star" (BUF, 2025), 100 dropbacks total, hand-computed below:
      - 96 filler completions: epa=0.1, cpoe=5.0, 5 yards each, no TD/INT
      - 1 scramble: epa=0.5 (qb_dropback but NOT pass_attempt -- passer_player_id/name are
        None here, matching the real nflverse quirk this module works around; passer_id/
        passer stay populated)
      - 1 sack: epa=-2.0, yards_gained=-7 (sack yardage, no passing_yards)
      - 1 TD pass: epa=3.0, cpoe=10.0, 20 yards, pass_touchdown=1
      - 1 INT pass: epa=-3.0, cpoe=-15.0, 0 yards, interception=1

    EPA/Play = mean of all 100: (96*0.1 + 0.5 - 2.0 + 3.0 - 3.0) / 100
             = (9.6 + 0.5 - 2.0 + 3.0 - 3.0) / 100 = 8.1 / 100 = 0.081
    CPOE = mean over the 98 attempts only (96 filler + TD + INT; scramble/sack excluded):
             (96*5.0 + 10.0 - 15.0) / 98 = (480 + 10 - 15) / 98 = 475 / 98
    ANY/A: attempts=98, sacks=1, denom=99
             att_yards = 96*5 + 20 + 0 = 500; sack_yards = -7
             numerator = (500 - 7) + 20*1 - 45*1 = 493 + 20 - 45 = 468
             ANY/A = 468 / 99

    QB2 "B.Mop" (BUF, 2025): 50 dropbacks only -- below MIN_QUALIFYING_DROPBACKS (100),
    must be excluded entirely (not zero-filled).
    """
    qb1_filler = _filler_rows(96, "00-1111111", "A.Star", 2025, "BUF")
    qb1_special = [
        {"season_type": "REG", "season": 2025, "posteam": "BUF",
         "passer_id": "00-1111111", "passer": "A.Star",
         "passer_player_id": None, "passer_player_name": None,  # scramble: null, per nflverse
         "qb_dropback": 1, "pass_attempt": 0, "sack": 0, "qb_scramble": 1,
         "epa": 0.5, "cpoe": None, "passing_yards": None, "yards_gained": 8,
         "pass_touchdown": 0, "interception": 0},
        {"season_type": "REG", "season": 2025, "posteam": "BUF",
         "passer_id": "00-1111111", "passer": "A.Star",
         "passer_player_id": "00-1111111", "passer_player_name": "A.Star",
         "qb_dropback": 1, "pass_attempt": 0, "sack": 1, "qb_scramble": 0,
         "epa": -2.0, "cpoe": None, "passing_yards": None, "yards_gained": -7,
         "pass_touchdown": 0, "interception": 0},
        {"season_type": "REG", "season": 2025, "posteam": "BUF",
         "passer_id": "00-1111111", "passer": "A.Star",
         "passer_player_id": "00-1111111", "passer_player_name": "A.Star",
         "qb_dropback": 1, "pass_attempt": 1, "sack": 0, "qb_scramble": 0,
         "epa": 3.0, "cpoe": 10.0, "passing_yards": 20, "yards_gained": 20,
         "pass_touchdown": 1, "interception": 0},
        {"season_type": "REG", "season": 2025, "posteam": "BUF",
         "passer_id": "00-1111111", "passer": "A.Star",
         "passer_player_id": "00-1111111", "passer_player_name": "A.Star",
         "qb_dropback": 1, "pass_attempt": 1, "sack": 0, "qb_scramble": 0,
         "epa": -3.0, "cpoe": -15.0, "passing_yards": 0, "yards_gained": 0,
         "pass_touchdown": 0, "interception": 1},
    ]
    qb2_mopup = _filler_rows(50, "00-2222222", "B.Mop", 2025, "BUF")

    return pd.DataFrame(qb1_filler + qb1_special + qb2_mopup)


def test_qb_stats_computes_expected_metrics_and_excludes_below_threshold():
    out = compute_team_season_qb_stats(_fake_pbp())

    assert list(out.columns) == SEASON_STATS_COLUMNS
    assert MIN_QUALIFYING_DROPBACKS == 100  # the fixture's docstring math assumes this

    # QB2 (50 dropbacks) must be excluded entirely -- only QB1 survives.
    assert len(out) == 1
    qb1 = out.iloc[0]

    assert qb1["Player Name"] == "A.Star"
    assert qb1["Player ID"] == "00-1111111"
    assert qb1["Team"] == "Buffalo Bills"
    assert qb1["Season"] == 2025
    assert qb1["Dropbacks"] == 100
    assert qb1["EPA/Play"] == pytest.approx(0.081)
    assert qb1["CPOE"] == pytest.approx(475 / 98)
    assert qb1["ANY/A"] == pytest.approx(468 / 99)


def test_qb_stats_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame(_filler_rows(100, "00-9999999", "Z.Zed", 2025, "ZZZ"))
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_qb_stats(df)


def test_qb_stats_flags_rookie_season_as_first_qualifying_season_not_first_appearance():
    # QB3 "C.Young": a below-threshold 2024 cup of coffee (60 dropbacks, excluded from the
    # output) followed by a qualifying 2025 -- 2025 must be flagged as the rookie season,
    # since the 2024 appearance never qualified and so doesn't count as "having a season."
    qb3_2024_belowthreshold = _filler_rows(60, "00-3333333", "C.Young", 2024, "MIA")
    qb3_2025_qualifying = _filler_rows(100, "00-3333333", "C.Young", 2025, "MIA")

    # QB4 "D.Vet": qualifies in both 2024 and 2025 -- 2024 (the earlier real season) is the
    # rookie season, 2025 is not.
    qb4_2024 = _filler_rows(105, "00-4444444", "D.Vet", 2024, "MIA")
    qb4_2025 = _filler_rows(100, "00-4444444", "D.Vet", 2025, "MIA")

    pbp = pd.DataFrame(
        qb3_2024_belowthreshold + qb3_2025_qualifying + qb4_2024 + qb4_2025
    )
    out = compute_team_season_qb_stats(pbp)

    qb3 = out[out["Player ID"] == "00-3333333"]
    assert list(qb3["Season"]) == [2025]  # 2024 excluded (below threshold), not zero-filled
    assert qb3.iloc[0]["Is Rookie Season"]

    qb4 = out[out["Player ID"] == "00-4444444"].sort_values("Season")
    assert list(qb4["Season"]) == [2024, 2025]
    assert qb4[qb4["Season"] == 2024].iloc[0]["Is Rookie Season"]
    assert not qb4[qb4["Season"] == 2025].iloc[0]["Is Rookie Season"]


def test_qb_roles_ranks_starter_and_backup_by_dropbacks():
    season_stats = pd.DataFrame([
        {"Team": "Buffalo Bills", "Season": 2025, "Player Name": "A.Star",
         "Player ID": "00-1111111", "Dropbacks": 550, "EPA/Play": 0.1, "CPOE": 3.0,
         "ANY/A": 6.5, "Is Rookie Season": False},
        {"Team": "Buffalo Bills", "Season": 2025, "Player Name": "B.Two",
         "Player ID": "00-2222222", "Dropbacks": 120, "EPA/Play": -0.1, "CPOE": -2.0,
         "ANY/A": 4.5, "Is Rookie Season": False},
        {"Team": "Buffalo Bills", "Season": 2025, "Player Name": "C.Three",
         "Player ID": "00-3333333", "Dropbacks": 105, "EPA/Play": -0.2, "CPOE": -3.0,
         "ANY/A": 4.0, "Is Rookie Season": True},
    ])

    roles = compute_qb_roles(season_stats)

    assert list(roles["Role"]) == ["Starter", "Backup", "Other"]
    assert list(roles["Player Name"]) == ["A.Star", "B.Two", "C.Three"]


def test_qb_roles_resolves_traded_qb_to_season_of_record_team():
    # A QB traded mid-season, qualifying with both teams -- roles must use the team with
    # more dropbacks as his season-of-record team, per the spec, not create two role rows.
    season_stats = pd.DataFrame([
        {"Team": "Miami Dolphins", "Season": 2025, "Player Name": "E.Traded",
         "Player ID": "00-5555555", "Dropbacks": 150, "EPA/Play": 0.0, "CPOE": 0.0,
         "ANY/A": 5.0, "Is Rookie Season": False},
        {"Team": "New York Jets", "Season": 2025, "Player Name": "E.Traded",
         "Player ID": "00-5555555", "Dropbacks": 400, "EPA/Play": 0.0, "CPOE": 0.0,
         "ANY/A": 5.0, "Is Rookie Season": False},
        {"Team": "New York Jets", "Season": 2025, "Player Name": "F.Bench",
         "Player ID": "00-6666666", "Dropbacks": 100, "EPA/Play": 0.0, "CPOE": 0.0,
         "ANY/A": 5.0, "Is Rookie Season": False},
    ])

    roles = compute_qb_roles(season_stats)

    assert len(roles) == 2  # one row per player, not per team-row
    jets = roles[roles["Team"] == "New York Jets"].sort_values("Dropbacks", ascending=False)
    assert list(jets["Player Name"]) == ["E.Traded", "F.Bench"]
    assert list(jets["Role"]) == ["Starter", "Backup"]
    assert "Miami Dolphins" not in set(roles["Team"])  # not double-counted on his old team
