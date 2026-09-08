"""
"Base Team Quality" -- Season Matchups' own Z01/AA01 components ((I+L)/2 for Home,
(K+J)/2 for Away), the real per-team scoring-rate foundation everything else in Z/AA adjusts.

Confirmed by reading the real formula chain across three sheets (never assumed): Season
Matchups' I/L/K/J columns are real INDEX/MATCH lookups into Team Ratings' own "Blended Off
(PPG Scored)"/"Blended Def (PPG Allowed)" columns (J/K there), NOT into Team Ratings' much
larger "Net Power Rating" composite (column N, itself a ~19-term sum of nearly every other
index tab's own real output) -- Season Matchups' Z/AA formula never references Net Power
Rating at all. Team Ratings' own Blended Off/Def in turn apply this project's existing
current-season blend_weight()/blended_value() functions to YoY Baseline Engine's own
"Projected 3-Yr Off/Def Baseline" columns (N/O there) -- which are themselves produced by
exactly this project's existing decay_weighted_average() -> team_history() -> projected_baseline()
chain (the same three functions Team-Specific HFA and every blend-shaped index tab already
reuse), applied here to real per-team-year Points-Per-Game Scored/Allowed instead of an
efficiency metric. No new shared engine functions were needed for this tab.

Real formula chain (row 110 in YoY Baseline Engine / row 3 in Team Ratings / row 3 in
Season Matchups, generalized to row r):

    YoY Baseline Engine (per team, Off and Def each):
        Off/Def Y-1/Y-2/Y-3: real SUMIFS over the tab's own real per-team-year game log
        Weighted Avg  =(Y1*1+Y2*C20+Y3*C20^2)/(1+C20+C20^2)            -- decay_weighted_average
        Team History  =Y1*C22+WeightedAvg*(1-C22)                       -- team_history
        League Baseline (Y-1) =INDEX/MATCH into the tab's own real Section 2 AVERAGEIF table
        Projected 3-Yr Baseline =TeamHistory*C21+LeagueBaseline*(1-C21)  -- projected_baseline

    Team Ratings (per team, Off and Def each):
        Current Season PPG Scored/Allowed, Games Played: real live-entered data
        Current Season Blend Weight =IF(H=0,0,MIN(C14,C12+(C13*(H-1))))  -- blend_weight
        Blended Off/Def =ProjBaseline*(1-Weight)+CurrentSeason*Weight     -- blended_value

    Season Matchups:
        I (Home Off PPG) = Team Ratings Blended Off, home team
        L (Away Def PPG) = Team Ratings Blended Def, away team
        K (Away Off PPG) = Team Ratings Blended Off, away team
        J (Home Def PPG) = Team Ratings Blended Def, home team
        Z01 Base Team Quality (Home) = (I+L)/2
        AA01 Base Team Quality (Away) = (K+J)/2

The real league_baseline_off_y1/league_baseline_def_y1 inputs (an AVERAGEIF over YoY Baseline
Engine's own real per-team-year data table) are taken here as already-resolved given inputs,
per this project's established "arithmetic only, not data sourcing" scoping -- consistent
with every other tab's league_avg/league_baseline_y1 treatment.
"""
from __future__ import annotations

from dataclasses import dataclass

from .decay_baseline import (
    blend_weight,
    blended_value,
    decay_weighted_average,
    projected_baseline,
    team_history,
)


@dataclass
class TeamQualityConstants:
    decay_factor: float          # C20
    last_year_emphasis: float    # C22
    regression_weight: float     # C21
    blend_base: float             # C12
    blend_per_game: float         # C13
    blend_cap: float               # C14


@dataclass
class TeamQualityTeamHistory:
    team: str
    off_y1: float
    off_y2: float
    off_y3: float
    def_y1: float
    def_y2: float
    def_y3: float
    league_baseline_off_y1: float
    league_baseline_def_y1: float
    current_season_off_ppg: float
    current_season_def_ppg: float
    games_played: int


@dataclass
class TeamQualityResult:
    team: str
    off_weighted_avg: float
    def_weighted_avg: float
    off_team_history: float
    def_team_history: float
    off_proj_baseline: float
    def_proj_baseline: float
    blend_weight: float
    blended_off: float  # Team Ratings' own "Blended Off (PPG Scored)" -- Season Matchups I/K
    blended_def: float  # Team Ratings' own "Blended Def (PPG Allowed)" -- Season Matchups L/J


def compute_team_quality(
    history: TeamQualityTeamHistory, constants: TeamQualityConstants,
) -> TeamQualityResult:
    off_weighted_avg = decay_weighted_average(
        history.off_y1, history.off_y2, history.off_y3, constants.decay_factor,
    )
    def_weighted_avg = decay_weighted_average(
        history.def_y1, history.def_y2, history.def_y3, constants.decay_factor,
    )
    off_team_history = team_history(
        history.off_y1, off_weighted_avg, constants.last_year_emphasis,
    )
    def_team_history = team_history(
        history.def_y1, def_weighted_avg, constants.last_year_emphasis,
    )
    off_proj_baseline = projected_baseline(
        off_team_history, history.league_baseline_off_y1, constants.regression_weight,
    )
    def_proj_baseline = projected_baseline(
        def_team_history, history.league_baseline_def_y1, constants.regression_weight,
    )

    weight = blend_weight(
        history.games_played, constants.blend_base, constants.blend_per_game,
        constants.blend_cap,
    )
    blended_off = blended_value(off_proj_baseline, history.current_season_off_ppg, weight)
    blended_def = blended_value(def_proj_baseline, history.current_season_def_ppg, weight)

    return TeamQualityResult(
        team=history.team,
        off_weighted_avg=off_weighted_avg, def_weighted_avg=def_weighted_avg,
        off_team_history=off_team_history, def_team_history=def_team_history,
        off_proj_baseline=off_proj_baseline, def_proj_baseline=def_proj_baseline,
        blend_weight=weight, blended_off=blended_off, blended_def=blended_def,
    )


def base_team_quality(
    home_blended_off: float, away_blended_def: float,
    away_blended_off: float, home_blended_def: float,
) -> tuple[float, float]:
    """Season Matchups Z01/AA01: (home_off, away_def) -> Base Team Quality (Home);
    (away_off, home_def) -> Base Team Quality (Away). Returns (home, away)."""
    home = (home_blended_off + away_blended_def) / 2
    away = (away_blended_off + home_blended_def) / 2
    return home, away
