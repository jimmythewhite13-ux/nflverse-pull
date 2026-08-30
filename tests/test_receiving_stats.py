import pandas as pd
import pytest

from nflverse_pull.receiving_stats import (
    MIN_QUALIFYING_TARGETS,
    SEASON_STATS_COLUMNS,
    compute_player_season_ngs_receiving,
    compute_team_season_receiving_stats,
)


def _target_rows(n, epa, success, yards, receiver_id, receiver_name, season, posteam,
                  pass_attempt=1, sack=0):
    return [
        {"season_type": "REG", "play_type": "pass", "posteam": posteam,
         "pass_attempt": pass_attempt, "sack": sack,
         "receiver_player_id": receiver_id, "receiver_player_name": receiver_name,
         "season": season, "epa": epa, "success": success, "yards_gained": yards}
        for _ in range(n)
    ]


def _fake_pbp():
    """
    WR1 "A.Target" (BUF, 2025), 40 targets total (exactly MIN_QUALIFYING_TARGETS):
      - 30 targets: epa=0.2, success=1, yards_gained=8
      - 10 targets: epa=-0.4, success=0, yards_gained=0

    Receiving EPA/Target = (30*0.2 + 10*-0.4) / 40 = (6.0 - 4.0) / 40 = 0.05
    Reception Success Rate = 30 / 40 = 0.75
    YPT = (30*8 + 10*0) / 40 = 240 / 40 = 6.0

    WR2 "B.Short" (BUF, 2025): 39 targets only -- one below the 40-target threshold, must be
    excluded entirely (not zero-filled).
    """
    wr1 = (
        _target_rows(30, 0.2, 1, 8, "00-1111111", "A.Target", 2025, "BUF")
        + _target_rows(10, -0.4, 0, 0, "00-1111111", "A.Target", 2025, "BUF")
    )
    wr2 = _target_rows(39, 0.0, 1, 5, "00-2222222", "B.Short", 2025, "BUF")
    return pd.DataFrame(wr1 + wr2)


def test_receiving_stats_computes_expected_metrics_and_excludes_below_threshold():
    out = compute_team_season_receiving_stats(_fake_pbp())

    assert list(out.columns) == SEASON_STATS_COLUMNS
    assert MIN_QUALIFYING_TARGETS == 40

    assert len(out) == 1  # WR2 (39 targets) excluded
    wr1 = out.iloc[0]

    assert wr1["Player Name"] == "A.Target"
    assert wr1["Team"] == "Buffalo Bills"
    assert wr1["Targets"] == 40
    assert wr1["Receiving EPA/Target"] == pytest.approx(0.05)
    assert wr1["Reception Success Rate"] == pytest.approx(0.75)
    assert wr1["YPT"] == pytest.approx(6.0)


def test_receiving_stats_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame(_target_rows(40, 0.1, 1, 8, "00-9999999", "Z.Zed", 2025, "ZZZ"))
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_receiving_stats(df)


def test_receiving_stats_excludes_sacks_even_with_pass_attempt_flag_set():
    # nflverse's own quirk (verified before writing this module): pass_attempt=1 is also
    # true on a sack. A sack has no receiver_player_id at all, so it's already excluded by
    # the notna() filter -- this confirms a sack row never accidentally counts as a target
    # even if some future data quirk gave it a stray receiver_player_id value.
    rows = _target_rows(40, 0.1, 1, 8, "00-3333333", "S.Real", 2025, "MIA")
    sack_row = _target_rows(1, -1.5, 0, -7, "00-3333333", "S.Real", 2025, "MIA", sack=1)
    out = compute_team_season_receiving_stats(pd.DataFrame(rows + sack_row))
    assert len(out) == 1
    assert out.iloc[0]["Targets"] == 40  # the sack row did NOT get counted as a 41st target


def test_receiving_stats_excludes_targetless_incompletions():
    # A throwaway/spike/intentional-grounding play: pass_attempt=1, sack=0, but no receiver
    # was ever credited (receiver_player_id is null) -- must not break grouping or get
    # miscounted against any real player.
    rows = _target_rows(40, 0.1, 1, 8, "00-4444444", "R.Real", 2025, "MIA")
    throwaway = [{
        "season_type": "REG", "play_type": "pass", "posteam": "MIA",
        "pass_attempt": 1, "sack": 0, "receiver_player_id": None,
        "receiver_player_name": None, "season": 2025, "epa": -1.0, "success": 0,
        "yards_gained": 0,
    }]
    out = compute_team_season_receiving_stats(pd.DataFrame(rows + throwaway))
    assert len(out) == 1
    assert out.iloc[0]["Targets"] == 40


def test_receiving_stats_flags_rookie_season_as_first_qualifying_season():
    below_threshold_2024 = _target_rows(20, 0.0, 0, 4, "00-5555555", "R.Young", 2024, "MIA")
    qualifying_2025 = _target_rows(40, 0.0, 0, 4, "00-5555555", "R.Young", 2025, "MIA")
    pbp = pd.DataFrame(below_threshold_2024 + qualifying_2025)

    out = compute_team_season_receiving_stats(pbp)

    assert list(out["Season"]) == [2025]  # 2024 excluded, not zero-filled
    assert out.iloc[0]["Is Rookie Season"]


def _ngs_row(player_id, season, team_abbr, week, avg_separation, avg_yac, avg_expected_yac):
    return {
        "player_gsis_id": player_id, "season": season, "team_abbr": team_abbr,
        "week": week, "avg_separation": avg_separation, "avg_yac": avg_yac,
        "avg_expected_yac": avg_expected_yac,
    }


def test_ngs_receiving_uses_real_season_aggregate_rows_only():
    # week=0 is the real season aggregate; weekly rows must be ignored, not averaged
    # manually -- NGS already computes the season total itself.
    rows = [
        _ngs_row("P1", 2025, "BUF", 0, 3.2, 6.5, 6.0),
        _ngs_row("P1", 2025, "BUF", 1, 2.9, 5.0, 5.5),
        _ngs_row("P1", 2025, "BUF", 2, 3.5, 7.0, 6.2),
    ]
    out = compute_player_season_ngs_receiving(pd.DataFrame(rows)).set_index("Player ID")
    assert len(out) == 1
    assert out.loc["P1", "Avg Separation"] == pytest.approx(3.2)
    assert out.loc["P1", "YAC Over Expectation"] == pytest.approx(0.5)  # 6.5 - 6.0
    assert out.loc["P1", "Team"] == "Buffalo Bills"


def test_ngs_receiving_remaps_ngs_lar_to_la():
    rows = [_ngs_row("P1", 2025, "LAR", 0, 3.0, 6.0, 5.5)]
    out = compute_player_season_ngs_receiving(pd.DataFrame(rows))
    assert out.iloc[0]["Team"] == "Los Angeles Rams"


def test_ngs_receiving_raises_on_unmapped_team_abbreviation():
    df = pd.DataFrame([_ngs_row("P1", 2025, "ZZZ", 0, 3.0, 6.0, 5.5)])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_player_season_ngs_receiving(df)


def test_ngs_receiving_skips_rows_with_no_real_player_id():
    rows = [
        _ngs_row(None, 2025, "BUF", 0, 3.0, 6.0, 5.5),
        _ngs_row("P1", 2025, "BUF", 0, 3.1, 6.1, 5.6),
    ]
    out = compute_player_season_ngs_receiving(pd.DataFrame(rows))
    assert len(out) == 1
    assert out.iloc[0]["Player ID"] == "P1"
