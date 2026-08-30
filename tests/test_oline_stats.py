import pandas as pd
import pytest

from nflverse_pull.oline_stats import (
    compute_team_season_oline_stats,
    compute_team_season_sack_fault_stats,
)


def _pass_row(team, season, attempts, pressured):
    return {"team": team, "season": season, "pass_attempts": attempts,
            "times_pressured": pressured}


def _rush_row(tm, season, att, ybc):
    return {"tm": tm, "season": season, "att": att, "ybc": ybc}


def test_oline_stats_computes_attempt_weighted_team_pressure_and_ybc():
    """
    BUF 2025 pass protection: two QBs --
      QB1: 500 attempts, 100 pressured
      QB2 (backup, small sample): 10 attempts, 8 pressured
    Attempt-weighted pressure rate = (100+8)/(500+10) = 108/510 = 0.211764...
    Pass_Protection = 100 * (1 - 0.211764...) = 78.8235...

    A SIMPLE (unweighted) average of the two QBs' individual rates would be
    (20% + 80%)/2 = 50% pressured -- very different and wrong, since the backup's tiny
    10-attempt sample would count as much as the starter's full season.

    BUF 2025 run blocking: two RBs --
      RB1: 300 attempts, 900 yards before contact (3.0 YBC/att)
      RB2: 50 attempts, 100 yards before contact (2.0 YBC/att)
    Attempt-weighted YBC/Att = (900+100)/(300+50) = 1000/350 = 2.857142...
    """
    pfr_pass = pd.DataFrame([
        _pass_row("BUF", 2025, 500, 100),
        _pass_row("BUF", 2025, 10, 8),
    ])
    pfr_rush = pd.DataFrame([
        _rush_row("BUF", 2025, 300, 900),
        _rush_row("BUF", 2025, 50, 100),
    ])

    out = compute_team_season_oline_stats(pfr_pass, pfr_rush)

    assert len(out) == 1
    row = out.iloc[0]
    assert row["Team"] == "Buffalo Bills"
    assert row["Season"] == 2025
    assert row["Pass_Protection"] == pytest.approx(100 * (1 - 108 / 510))
    assert row["Run_Blocking"] == pytest.approx(1000 / 350)


def test_oline_stats_remaps_pfr_lar_lvr_and_excludes_multi_team_aggregate_rows():
    # Verified live before writing this: the 2023 PFR 'pass' dataset alone uses "LAR"/"LVR"
    # where every other year/dataset uses "LA"/"LV" -- and a traded player's "2TM" row
    # duplicates (not supplements) his real per-team split rows.
    pfr_pass = pd.DataFrame([
        _pass_row("LAR", 2023, 400, 80),
        _pass_row("LVR", 2023, 400, 100),
        # A traded QB's aggregate row must be excluded, or MIA's real numbers below would
        # be double-counted against this fabricated blend.
        _pass_row("2TM", 2023, 50, 10),
        _pass_row("MIA", 2023, 400, 90),
    ])
    pfr_rush = pd.DataFrame([
        _rush_row("LA", 2023, 300, 750),
        _rush_row("LV", 2023, 300, 900),
        _rush_row("MIA", 2023, 300, 600),
    ])

    out = compute_team_season_oline_stats(pfr_pass, pfr_rush).set_index("Team")

    assert out.loc["Los Angeles Rams", "Pass_Protection"] == pytest.approx(100 * (1 - 80 / 400))
    assert out.loc["Las Vegas Raiders", "Pass_Protection"] == pytest.approx(100 * (1 - 100 / 400))
    # MIA's real 90/400 rate, NOT diluted by the excluded 2TM aggregate row.
    assert out.loc["Miami Dolphins", "Pass_Protection"] == pytest.approx(100 * (1 - 90 / 400))


def test_oline_stats_raises_on_unmapped_team_abbreviation():
    pfr_pass = pd.DataFrame([_pass_row("ZZZ", 2025, 100, 20)])
    pfr_rush = pd.DataFrame([_rush_row("ZZZ", 2025, 100, 250)])
    with pytest.raises(ValueError, match="No full-name mapping"):
        compute_team_season_oline_stats(pfr_pass, pfr_rush)


def test_oline_stats_handles_a_team_present_in_only_one_of_pass_or_rush():
    # An outer merge -- a team missing from one side (e.g. a data gap) still gets a row,
    # with the other metric present, rather than being dropped from the whole output.
    pfr_pass = pd.DataFrame([_pass_row("MIA", 2025, 500, 100)])
    pfr_rush = pd.DataFrame([_rush_row("NYJ", 2025, 300, 750)])

    out = compute_team_season_oline_stats(pfr_pass, pfr_rush).set_index("Team")

    assert pd.isna(out.loc["Miami Dolphins", "Run_Blocking"])
    assert out.loc["Miami Dolphins", "Pass_Protection"] == pytest.approx(80.0)
    assert pd.isna(out.loc["New York Jets", "Pass_Protection"])
    assert out.loc["New York Jets", "Run_Blocking"] == pytest.approx(2.5)


def _pbp_row(posteam, season, pass_attempt=0, sack=0, game_id="G1", play_id=1):
    return {
        "season_type": "REG", "posteam": posteam, "season": season,
        "pass_attempt": pass_attempt, "sack": sack, "game_id": game_id, "play_id": play_id,
    }


def _ftn_row(game_id, play_id, is_qb_fault_sack):
    return {
        "nflverse_game_id": game_id, "nflverse_play_id": play_id,
        "is_qb_fault_sack": is_qb_fault_sack,
    }


def test_sack_fault_stats_excludes_qb_fault_sacks_from_ol_blame():
    """
    BUF, 2025: 10 real pass plays faced (including sacks, matching the "pass_attempt is
    TRUE on a sack too" quirk documented elsewhere in this project).
      - 2 sacks charted as the O-line's fault (is_qb_fault_sack=False)
      - 1 sack charted as the QB's own fault (is_qb_fault_sack=True) -- must NOT count
        against the line
    Sack-Free Rate (Fault-Adjusted) = 1 - (2 OL-fault sacks / 10 pass plays) = 0.8
    (NOT 1 - 3/10 = 0.7, which is what an unadjusted sack rate would give.)
    """
    pbp_rows = [
        _pbp_row("BUF", 2025, pass_attempt=1, sack=1, play_id=1),
        _pbp_row("BUF", 2025, pass_attempt=1, sack=1, play_id=2),
        _pbp_row("BUF", 2025, pass_attempt=1, sack=1, play_id=3),
    ]
    pbp_rows += [_pbp_row("BUF", 2025, pass_attempt=1, play_id=i) for i in range(4, 11)]
    ftn_rows = [
        _ftn_row("G1", 1, False),
        _ftn_row("G1", 2, False),
        _ftn_row("G1", 3, True),
    ]
    out = compute_team_season_sack_fault_stats(
        pd.DataFrame(pbp_rows), pd.DataFrame(ftn_rows)
    ).set_index("Team")
    assert out.loc["Buffalo Bills", "Sack-Free Rate (Fault-Adjusted)"] == pytest.approx(0.8)


def test_sack_fault_stats_treats_unmatched_sack_as_ol_fault_by_default():
    # A real sack with no FTN charting match at all (is_qb_fault_sack ends up NaN after the
    # left join) is NOT proven to be the QB's fault -- conservative default, counts against
    # the line, same as an ordinary sack would without this adjustment.
    pbp_rows = [_pbp_row("MIA", 2025, pass_attempt=1, sack=1, game_id="UNMATCHED", play_id=99)]
    pbp_rows += [_pbp_row("MIA", 2025, pass_attempt=1, play_id=i) for i in range(1, 4)]
    out = compute_team_season_sack_fault_stats(
        pd.DataFrame(pbp_rows), pd.DataFrame(columns=["nflverse_game_id", "nflverse_play_id",
                                                        "is_qb_fault_sack"])
    ).set_index("Team")
    assert out.loc["Miami Dolphins", "Sack-Free Rate (Fault-Adjusted)"] == pytest.approx(1 - 1 / 4)
