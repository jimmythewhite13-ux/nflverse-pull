"""
Real per-COACH-SEASON metrics for the Coaching Index -- claude_code_spec_coaching_index.md.

CRITICAL DESIGN CHOICE (per the spec's own explicit instruction): every other 3-Yr decay-
weighted tab in this project blends a TEAM's own history. Coaching data must instead follow
the COACH -- if a team fired its HC after 2024, blending 2023-2025 "team" data as one
continuous coaching philosophy would attribute the old coach's decisions to the new one.
Real, verified live before building this: 'away_coach'/'home_coach' are real, populated
columns on nflverse's own schedules (0 nulls across 2023-2026, both historical and the
already-scheduled 2026 season) -- 13 of 32 teams had a real coaching change somewhere in
2023-2025, including three real IN-SEASON interim changes (CAR/LAC/LV, all 2023).

Because of those in-season changes, this module attributes each PLAY to whichever coach
actually ran that specific GAME (via schedules' own home_coach/away_coach, joined on
game_id) -- NOT "whichever coach coached the majority of a season," which would silently
misattribute an interim coach's real games to his predecessor or successor. This makes the
raw material keyed by (Coach Name, Season, Team) rather than (Team, Season) -- the same
identity-plus-season-offset pattern every other tab's own Section 3 already uses (SUMIFS by
identity, matched against 'Model Assumptions'!$C$18-k), just swapping Team for Coach as the
identity column. A coach who changed teams between seasons, or who had zero HC seasons
anywhere in the pulled window (a true rookie HC), is handled by the EXACT SAME "COUNTIFS(...)
=0 -> substitute that season's league average" mechanism QB Index's own Rookie Baseline
already uses -- no new fallback mechanism invented here.

4th Down Aggressiveness (highest confidence per the spec) -- HONESTY NOTE: nfl_data_py's pbp
does NOT ship a trained win-probability-optimal 4th-down decision model (the kind the R-only
`nfl4th` package or public "4th down bot" analyses provide) -- verified live before building
this (no 'go_boost'/'recommend'/'4th_down_prob'-style column exists anywhere in the 396 real
pbp columns). Building a full WP-optimal decision model from scratch would fabricate a level
of statistical rigor this project doesn't have, exactly the risk the project's later specs
explicitly warn against for "model variance." The closest honest real proxy, documented as
such rather than presented as a true WP-optimal comparison: real Go-For-It Rate specifically
on 4th-and-2-or-less (a situational bucket real published football-analytics research and
mainstream coaching-aggressiveness rankings broadly treat as "should usually go for it,"
narrow enough that the comparison is meaningful) versus the real league-wide average Go Rate
in that same bucket that season. This measures a real coaching CHOICE (attempted vs. not),
independent of execution, but is NOT a full win-probability-optimality score -- garbage-time/
desperation attempts are not separately excluded, a real, acknowledged scope limit.

Second-Half EPA Delta (lowest confidence, per the spec's own explicit instruction) --
real and computable (game_half's real Half1/Half2 split, verified live: 0 nulls, Overtime
excluded from both halves), but genuinely uncertain as a persistent coaching trait; see this
tab's own low default weight and explicit uncertainty note.

Penalty Discipline needs the SAME regression-to-mean treatment as turnover luck (per the
spec) -- raw penalty rate is real (penalty/penalty_team columns, verified live: 0 nulls on
penalty_team for every real penalty row) but some of its season-to-season variance is closer
to random noise than a stable coaching trait, same reasoning Turnover & Red-Zone Regression
already established for red-zone TD%. This module computes the RAW rate only; the Excel tab
applies its own dedicated (not reused-by-reference, since the sample-size scale differs --
total real plays vs. red-zone drives) blend-weight regression, built to the SAME shape.

Red Zone Conversion is deliberately NOT recomputed here -- already covered by
claude_code_spec_turnover_redzone_regression_engine.md.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES

# The situational bucket real published 4th-down analytics broadly treats as "should usually
# go for it" -- narrow enough (short yardage) that a real go-rate-vs-league-average
# comparison is meaningful without needing a full trained WP-optimal decision model.
FOURTH_DOWN_SHORT_YARDS_TO_GO = 2

REQUIRED_SCHED_COLS = [
    "game_id", "season", "game_type", "home_team", "away_team", "home_coach", "away_coach",
]


def compute_game_coach_map(sched: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real per-game (Team, Coach, Season, game_id) long-format
    table from schedules' own home_coach/away_coach -- the raw material every metric below
    joins pbp against, so a mid-season coaching change is attributed at REAL GAME precision,
    not smeared across a whole season.
    """
    missing = [c for c in REQUIRED_SCHED_COLS if c not in sched.columns]
    if missing:
        raise ValueError(f"Input schedule data is missing expected columns: {missing}")
    reg = sched[sched["game_type"] == "REG"].dropna(subset=["home_coach", "away_coach"])
    home = reg[["game_id", "season", "home_team", "home_coach"]].rename(
        columns={"home_team": "team_abbr", "home_coach": "coach"}
    )
    away = reg[["game_id", "season", "away_team", "away_coach"]].rename(
        columns={"away_team": "team_abbr", "away_coach": "coach"}
    )
    out = pd.concat([home, away], ignore_index=True)
    unmapped = sorted(set(out["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["team_abbr"].map(TEAM_NAMES)
    # Keeps BOTH the real abbreviation (team_abbr, for joining against pbp's own posteam/
    # defteam, which are always abbreviations, verified live -- a join on full team names
    # here would silently match nothing) and the full name (Team, for the final output rows
    # and for Team Ratings-style INDEX/MATCH lookups downstream, same convention every other
    # tab in this project already uses).
    return out[["game_id", "season", "team_abbr", "Team", "coach"]].rename(
        columns={"season": "Season"}
    )


def compute_coach_season_stats(pbp: pd.DataFrame, game_coach_map: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real per-(Coach, Season, Team) metrics, each play attributed
    to whichever coach actually ran that specific game (via game_coach_map's real game_id
    join -- NOT a season-majority approximation).

    Output columns: Coach | Season | Team | 4th Down Go Rate (Short) | 4th-and-Short
    Attempts (count) | 1Q Net EPA/Play | Penalty Rate | Total Plays (count, penalty-rate
    denominator) | 2H EPA Delta.

    A coach-season with zero qualifying plays for a given metric gets a null value for that
    metric (not zero) -- e.g. a coach whose team never faced a real 4th-and-2-or-less
    situation that season has no real Go Rate to report.
    """
    off = pbp.merge(
        game_coach_map, left_on=["game_id", "posteam"], right_on=["game_id", "team_abbr"],
        how="inner",
    )
    def_ = pbp.merge(
        game_coach_map, left_on=["game_id", "defteam"], right_on=["game_id", "team_abbr"],
        how="inner",
    )

    # ---- 4th Down Aggressiveness (short-yardage bucket only) -----------------------------
    real_decisions = off[
        (off["down"] == 4) & (off["play_type"].isin(["run", "pass", "field_goal", "punt"]))
    ]
    short = real_decisions[real_decisions["ydstogo"] <= FOURTH_DOWN_SHORT_YARDS_TO_GO]
    went_for_it = short["play_type"].isin(["run", "pass"]).astype(int)
    go_rate = (
        short.assign(went=went_for_it).groupby(["coach", "Season", "Team"])["went"]
        .agg(["mean", "size"])
        .rename(columns={"mean": "4th Down Go Rate (Short)", "size": "4th-and-Short Attempts"})
    )

    # ---- 1st-Quarter Net EPA/Play (own offense's Q1 EPA - Q1 EPA allowed on defense) -----
    scrimmage = ["run", "pass"]
    off_q1 = off[(off["qtr"] == 1) & off["epa"].notna() & off["play_type"].isin(scrimmage)]
    off_q1_epa = off_q1.groupby(["coach", "Season", "Team"])["epa"].mean()
    def_q1 = def_[(def_["qtr"] == 1) & def_["epa"].notna() & def_["play_type"].isin(scrimmage)]
    def_q1_epa = def_q1.groupby(["coach", "Season", "Team"])["epa"].mean()

    # ---- Penalty Discipline (raw rate; regression-to-mean applied in Excel) --------------
    real_plays = pd.concat([
        off[off["play_type"].isin(["run", "pass", "field_goal", "punt"])],
        def_[def_["play_type"].isin(["run", "pass", "field_goal", "punt"])],
    ])
    total_plays = real_plays.groupby(["coach", "Season", "Team"]).size()

    # penalty_team, like posteam/defteam, is a real abbreviation -- compared against
    # team_abbr (not Team, the full name) for the same reason the join above uses it.
    penalties_off = off[(off["penalty"] == 1) & (off["penalty_team"] == off["team_abbr"])]
    penalties_def = def_[(def_["penalty"] == 1) & (def_["penalty_team"] == def_["team_abbr"])]
    penalty_count = (
        pd.concat([penalties_off, penalties_def])
        .groupby(["coach", "Season", "Team"]).size()
    )

    # ---- 2nd-Half EPA Delta (own offense only; excludes Overtime from both halves) -------
    h1 = off[(off["game_half"] == "Half1") & off["epa"].notna() & off["play_type"].isin(scrimmage)]
    h2 = off[(off["game_half"] == "Half2") & off["epa"].notna() & off["play_type"].isin(scrimmage)]
    h1_epa = h1.groupby(["coach", "Season", "Team"])["epa"].mean()
    h2_epa = h2.groupby(["coach", "Season", "Team"])["epa"].mean()

    idx = go_rate.index.union(off_q1_epa.index).union(total_plays.index).union(h1_epa.index)
    out = pd.DataFrame(index=idx)
    out["4th Down Go Rate (Short)"] = go_rate["4th Down Go Rate (Short)"]
    out["4th-and-Short Attempts"] = go_rate["4th-and-Short Attempts"]
    out["1Q Net EPA/Play"] = (off_q1_epa - def_q1_epa)
    out["Total Plays"] = total_plays
    out["Penalty Rate"] = (penalty_count / total_plays)
    out["2H EPA Delta"] = (h2_epa - h1_epa)

    out = out.reset_index().rename(columns={"coach": "Coach"})
    out = out.sort_values(["Coach", "Season"]).reset_index(drop=True)
    return out[[
        "Coach", "Season", "Team", "4th Down Go Rate (Short)", "4th-and-Short Attempts",
        "1Q Net EPA/Play", "Penalty Rate", "Total Plays", "2H EPA Delta",
    ]]


def compute_current_coach_by_team(sched: pd.DataFrame, current_season: int) -> pd.DataFrame:
    """
    Pure function, no network. Real current (Team, Coach) for `current_season`, from
    schedules' own home_coach/away_coach -- works even pre-kickoff since the full season's
    schedule (with real, already-assigned coaches) is published well before Week 1.
    """
    missing = [c for c in REQUIRED_SCHED_COLS if c not in sched.columns]
    if missing:
        raise ValueError(f"Input schedule data is missing expected columns: {missing}")
    cur = sched[(sched["season"] == current_season) & (sched["game_type"] == "REG")]
    cur = cur.dropna(subset=["home_coach", "away_coach"])
    home = cur[["home_team", "home_coach"]].rename(
        columns={"home_team": "team_abbr", "home_coach": "coach"}
    )
    away = cur[["away_team", "away_coach"]].rename(
        columns={"away_team": "team_abbr", "away_coach": "coach"}
    )
    both = pd.concat([home, away], ignore_index=True).drop_duplicates()
    unmapped = sorted(set(both["team_abbr"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    both["Team"] = both["team_abbr"].map(TEAM_NAMES)
    # A team could show >1 distinct coach across its (already-published) schedule only in a
    # genuinely unusual real event (e.g. a real in-season firing announced before the season
    # started, which the schedule feed has already picked up) -- keep the most COMMON real
    # coach name for that team as the current one, a defensible real tie-break, not a guess.
    out = (
        both.groupby("Team")["coach"]
        .agg(lambda s: s.value_counts().idxmax())
        .reset_index()
        .rename(columns={"coach": "Coach"})
    )
    return out[["Team", "Coach"]]
