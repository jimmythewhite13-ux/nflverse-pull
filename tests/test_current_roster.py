import pandas as pd
import pytest

from nflverse_pull.current_roster import OUTPUT_COLUMNS, compute_current_starters


def _row(dt, team, name, gsis_id, pos_abb, pos_rank):
    return {"dt": dt, "team": team, "player_name": name, "gsis_id": gsis_id,
            "pos_abb": pos_abb, "pos_rank": pos_rank}


def test_current_starters_uses_latest_snapshot_per_slot_not_per_player():
    """
    ARI's QB1 slot changes hands mid-window (a trade or camp competition): A.Old holds it
    in the March snapshot, B.New holds it in the later August snapshot. The August snapshot
    must win -- this is the mechanism that correctly picks up a real trade (e.g. the actual
    pulled data showed Kyler Murray moving from ARI to MIN's QB1 slot this way).
    """
    rows = [
        _row("2026-03-01T00:00:00Z", "ARI", "A.Old", "P1", "QB", 1),
        _row("2026-08-01T00:00:00Z", "ARI", "B.New", "P2", "QB", 1),
        _row("2026-08-01T00:00:00Z", "ARI", "C.Backup", "P3", "QB", 2),
        # A 3rd-string QB must be excluded (only ranks 1-2 are scored downstream).
        _row("2026-08-01T00:00:00Z", "ARI", "D.Third", "P4", "QB", 3),
    ]
    out = compute_current_starters(pd.DataFrame(rows))

    assert list(out.columns) == OUTPUT_COLUMNS
    assert len(out) == 2  # only the QB1 and QB2 slots, D.Third excluded
    starter = out[out["Depth Order"] == 1].iloc[0]
    backup = out[out["Depth Order"] == 2].iloc[0]
    assert starter["Player Name"] == "B.New"  # the later snapshot's occupant, not A.Old
    assert backup["Player Name"] == "C.Backup"
    assert starter["Team"] == "Arizona Cardinals"
    assert starter["Source"] == "depth_charts"


def test_current_starters_covers_qb_rb_wr_and_te():
    rows = [
        _row("2026-08-01T00:00:00Z", "KC", "P.Mahomes", "QB1", "QB", 1),
        _row("2026-08-01T00:00:00Z", "KC", "I.Pacheco", "RB1", "RB", 1),
        _row("2026-08-01T00:00:00Z", "KC", "R.Rice", "WR1", "WR", 1),
        _row("2026-08-01T00:00:00Z", "KC", "T.Kelce", "TE1", "TE", 1),
        # A position not in POSITIONS at all (e.g. WR-adjacent depth-chart noise like FB)
        # must be excluded entirely.
        _row("2026-08-01T00:00:00Z", "KC", "Some FB", "FB1", "FB", 1),
    ]
    out = compute_current_starters(pd.DataFrame(rows))
    assert len(out) == 4
    assert set(out["Position"]) == {"QB", "RB", "WR", "TE"}


def test_current_starters_wr_scores_three_slots_te_scores_one():
    rows = [
        _row("2026-08-01T00:00:00Z", "KC", "R.WR1", "PW1", "WR", 1),
        _row("2026-08-01T00:00:00Z", "KC", "R.WR2", "PW2", "WR", 2),
        _row("2026-08-01T00:00:00Z", "KC", "R.WR3", "PW3", "WR", 3),
        # WR4 must be excluded -- only ranks 1-3 are scored for WR.
        _row("2026-08-01T00:00:00Z", "KC", "R.WR4", "PW4", "WR", 4),
        _row("2026-08-01T00:00:00Z", "KC", "T.TE1", "PT1", "TE", 1),
        # TE2 must be excluded -- only rank 1 is scored for TE.
        _row("2026-08-01T00:00:00Z", "KC", "T.TE2", "PT2", "TE", 2),
    ]
    out = compute_current_starters(pd.DataFrame(rows))
    assert len(out) == 4
    assert set(out[out["Position"] == "WR"]["Depth Order"]) == {1, 2, 3}
    assert set(out[out["Position"] == "TE"]["Depth Order"]) == {1}


def test_current_starters_raises_on_unmapped_team_abbreviation():
    rows = [_row("2026-08-01T00:00:00Z", "ZZZ", "X.Player", "P1", "QB", 1)]
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_current_starters(pd.DataFrame(rows))
