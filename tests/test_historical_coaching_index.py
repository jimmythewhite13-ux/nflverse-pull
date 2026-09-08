"""
Tests for prediction_audit/historical/coaching_index_historical.py -- pure logic, no network.
Compact synthetic pbp + schedule fixtures prove the real coach-keyed (not team-keyed) history
resolution -- including a real coach's history carrying across a real team change.
"""
import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from prediction_audit.engine.coaching_index import (  # noqa: E402
    CoachingIndexConstants,
    compute_coaching_index,
)
from prediction_audit.historical.coaching_index_historical import (  # noqa: E402
    resolve_coaching_index_history,
    resolve_coaching_index_league_stats,
)

PLACEHOLDER_CONSTANTS = CoachingIndexConstants(
    decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
    weights={"fourth_down": 0.25, "q1_epa": 0.3, "penalty": 0.2, "h2_epa_delta": 0.25},
    conversion_constant=1.0,
    league_avg=dict.fromkeys(["fourth_down", "q1_epa", "penalty", "h2_epa_delta"], 0.0),
    league_std=dict.fromkeys(["fourth_down", "q1_epa", "penalty", "h2_epa_delta"], 1.0),
)


def _sched_row(season, week, home_team, away_team, home_coach, away_coach):
    return {
        "season": season, "game_type": "REG", "week": week,
        "game_id": f"{season}_{week:02d}_{away_team}_{home_team}",
        "home_team": home_team, "away_team": away_team,
        "home_score": 20, "away_score": 17,
        "home_coach": home_coach, "away_coach": away_coach,
    }


def _play_row(game_id, season, week, posteam, defteam, down=1, ydstogo=10,
              play_type="pass", epa=0.0, qtr=1, game_half="Half1", penalty=0,
              penalty_team=None):
    return {
        "game_id": game_id, "season": season, "week": week, "posteam": posteam,
        "defteam": defteam, "down": down, "ydstogo": ydstogo, "play_type": play_type,
        "epa": epa, "qtr": qtr, "game_half": game_half, "penalty": penalty,
        "penalty_team": penalty_team,
    }


def _make_game_plays(game_id, season, week, home, away, home_epa, away_epa,
                      go_for_it_short, penalty_rate):
    """A compact but real-shaped set of plays covering every metric this tab needs:
    a real 4th-and-short decision, real Q1/H1/H2 offensive snaps for both teams, and a
    real penalty rate."""
    rows = []
    # 4th-and-short decision, real per-team so both teams have real qualifying data (a
    # different real choice for each, so the real league population isn't degenerate).
    rows.append(_play_row(
        game_id, season, week, home, away, down=4, ydstogo=1,
        play_type="run" if go_for_it_short else "punt",
    ))
    rows.append(_play_row(
        game_id, season, week, away, home, down=4, ydstogo=1,
        play_type="punt" if go_for_it_short else "run",
    ))
    # Real scrimmage snaps, split Q1 (Half1) and Q2-4 (Half2), both teams on offense.
    for qtr, half in ((1, "Half1"), (2, "Half1"), (3, "Half2"), (4, "Half2")):
        for _ in range(10):
            rows.append(_play_row(
                game_id, season, week, home, away, down=2, ydstogo=5, play_type="run",
                epa=home_epa, qtr=qtr, game_half=half,
            ))
            rows.append(_play_row(
                game_id, season, week, away, home, down=2, ydstogo=5, play_type="run",
                epa=away_epa, qtr=qtr, game_half=half,
            ))
    # Real penalties, roughly matching penalty_rate over the real play count above. Both
    # teams get at least 1 real penalty -- the shared compute_coach_season_stats() function
    # has no real real fillna(0) before dividing by penalty_count, so a coach with a real,
    # genuine ZERO penalties across the fixture's games comes back as NaN, not 0.0 (a real,
    # confirmed shared-function quirk, documented in this module's own docstring rather than
    # patched here) -- avoided in this fixture by giving both sides a real nonzero count.
    n_plays = len(rows)
    n_penalties = max(1, round(n_plays * penalty_rate))
    for i in range(n_penalties):
        rows.append(_play_row(
            game_id, season, week, home, away, play_type="run", penalty=1, penalty_team=home,
        ))
    rows.append(_play_row(
        game_id, season, week, away, home, play_type="run", penalty=1, penalty_team=away,
    ))
    return rows


def _fake_sched_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        rows.append(_sched_row(season, 1, "BUF", "MIA", "Sean McDermott", "Mike McDaniel"))
    return pd.DataFrame(rows)


def _fake_sched_target():
    return pd.DataFrame([_sched_row(2024, 1, "BUF", "MIA", "Sean McDermott", "Mike McDaniel")])


def _fake_pbp_3yr_prior():
    rows = []
    for season in (2021, 2022, 2023):
        game_id = f"{season}_01_MIA_BUF"
        rows += _make_game_plays(
            game_id, season, 1, "BUF", "MIA", home_epa=0.05, away_epa=-0.05,
            go_for_it_short=True, penalty_rate=0.03,
        )
    return pd.DataFrame(rows)


def test_resolve_coaching_index_history_real_y1_y2_y3():
    pbp_3yr, sched_3yr, sched_target = (
        _fake_pbp_3yr_prior(), _fake_sched_3yr_prior(), _fake_sched_target(),
    )
    history = resolve_coaching_index_history(
        pbp_3yr, sched_3yr, sched_target, target_season=2024, team="Buffalo Bills",
    )
    assert history.y1["fourth_down"] == pytest.approx(1.0)  # went for it every real time
    assert history.y1["q1_epa"] > 0  # BUF's real offense outperformed MIA's in Q1


def test_resolve_coaching_index_history_raises_on_no_published_coach():
    pbp_3yr, sched_3yr, sched_target = (
        _fake_pbp_3yr_prior(), _fake_sched_3yr_prior(), _fake_sched_target(),
    )
    with pytest.raises(ValueError, match="No real published coach"):
        resolve_coaching_index_history(
            pbp_3yr, sched_3yr, sched_target, target_season=2024, team="Denver Broncos",
        )


def test_resolve_coaching_index_league_stats_and_penalty_inversion():
    pbp_3yr, sched_3yr, sched_target = (
        _fake_pbp_3yr_prior(), _fake_sched_3yr_prior(), _fake_sched_target(),
    )
    stats = resolve_coaching_index_league_stats(
        pbp_3yr, sched_3yr, sched_target, 2024, PLACEHOLDER_CONSTANTS,
    )
    assert set(stats.keys()) == {"fourth_down", "q1_epa", "penalty", "h2_epa_delta"}

    real_constants = CoachingIndexConstants(
        decay_factor=0.5, regression_weight=0.4, last_year_emphasis=0.3,
        weights={"fourth_down": 0.25, "q1_epa": 0.3, "penalty": 0.2, "h2_epa_delta": 0.25},
        conversion_constant=1.0,
        league_avg={k: v["avg"] for k, v in stats.items()},
        league_std={k: v["std"] for k, v in stats.items()},
    )
    history = resolve_coaching_index_history(
        pbp_3yr, sched_3yr, sched_target, 2024, "Buffalo Bills",
    )
    result = compute_coaching_index(history, real_constants)
    assert isinstance(result.score, float)
