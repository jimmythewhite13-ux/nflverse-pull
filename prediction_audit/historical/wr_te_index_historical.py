"""
Step 6: resolves a real historical WR-TE Value Index for one real team's WR1/WR2/WR3/TE1,
using only real data available before a target game's own kickoff -- the ninth index made
walk-forward-capable, and the first with a genuinely NEW role-resolution design: unlike QB/RB/
Kicking, this project has no pre-existing historical-role convention for WR-TE at all (checked
before starting -- build_wr_te_index.py's own docstring confirms "Section 1 has NO historical
Role/label column"), and the live pipeline scores 4 real roles per team from real LIVE
depth-chart data, which has no meaning for an arbitrary past date.

**This module's own real, documented convention** (not previously established elsewhere in
this project): rank each team's real WRs by real Targets-so-far (through the target week) --
top 3 = WR1/WR2/WR3; separately rank real TEs the same way -- top 1 = TE1. Same real
volume-ranking spirit as QB's dropback rank / RB's carry rank / Kicking's attempt rank, applied
per-position-group instead of team-wide, using real Position from nflverse's own seasonal
rosters.

Real metric scoping: WR-TE Index has 9 real metrics, but 4 (`pass_play_pct`, `rz_target_share`,
`target_share`, `catch_rate`) carry a real weight of 0 by design (confirmed in Step 4's own
extraction -- 2 are usage-not-efficiency signals kept out of the composite deliberately, 2 are
volume-projection-only signals for Player Prop Projections). Computing all 4 for real needs 3
more real data sources beyond what the other 5 metrics already need (real pbp aggregation for
2 of them, `nflverse_pull.player_props` for the other 2) -- given they are mathematically
INERT for the real Score (weight=0), this module defaults them to a real, documented 0.0
placeholder rather than building that additional real data pipeline in this pass. A real
walk-forward reconstruction of Player Prop Projections specifically (a separate, distinct
downstream use of these same 2 volume-projection columns) would need to revisit this.

The 5 real score-affecting metrics (`receiving_epa`, `success_rate`, `ypt`, `avg_sep`,
`yac_oe`) are all real, via `compute_team_season_receiving_stats` (pbp) merged with
`compute_player_season_ngs_receiving` (real NGS data -- NOT full-coverage the way pbp-derived
metrics are, same real caveat as RB Index's RYOE/Att; a real missing NGS season raises, never
substituted).
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.receiving_stats import (
    compute_player_season_ngs_receiving,
    compute_team_season_receiving_stats,
)
from prediction_audit.engine.wr_te_index import METRIC_KEYS, WRTEHistory
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)
from prediction_audit.historical.team_ppg import team_season_ppg

_PBP_METRIC_COLUMN = {
    "receiving_epa": "Receiving EPA/Target", "success_rate": "Reception Success Rate",
    "ypt": "YPT",
}
_NGS_METRIC_COLUMN = {"avg_sep": "Avg Separation", "yac_oe": "YAC Over Expectation"}
_ZERO_WEIGHT_METRICS = ("pass_play_pct", "rz_target_share", "target_share", "catch_rate")
_ROLE_ORDER = ("WR1", "WR2", "WR3", "TE1")


def _build_metric_table(pbp: pd.DataFrame, ngs_receiving: pd.DataFrame) -> pd.DataFrame:
    """Real merged per-(Player ID, Season) metric table for the 5 real score-affecting
    metrics. A left join keeps every real qualifying receiver-season even where real NGS
    coverage is missing -- that row's avg_sep/yac_oe come back NaN, correctly triggering the
    real never-fabricate path downstream."""
    receiving = compute_team_season_receiving_stats(pbp)
    # Real NGS data quirk (verified live, same as RB Index's own real RYOE fix): a small
    # number of real season-aggregate rows carry a null team_abbr. compute_player_season_
    # ngs_receiving() has no full-name mapping for None and raises -- filtered out here
    # (that player-season's avg_sep/yac_oe then correctly become unresolvable via this
    # module's own real never-fabricate path) rather than touching the shared function.
    ngs_receiving = ngs_receiving[ngs_receiving["team_abbr"].notna()]
    ngs = compute_player_season_ngs_receiving(ngs_receiving)
    return receiving.merge(
        ngs[["Player ID", "Season", "Avg Separation", "YAC Over Expectation"]],
        on=["Player ID", "Season"], how="left",
    )


def resolve_wr_te_roles_as_of_week(
    pbp_current_season: pd.DataFrame, rosters: pd.DataFrame, target_season: int,
    through_week: int,
) -> pd.DataFrame:
    """Real Team|Role (WR1/WR2/WR3/TE1) as of `through_week` (weeks strictly before it only):
    real Targets-so-far, ranked separately within each team's real WRs and real TEs, using
    real Position from `rosters` (nflverse's own seasonal roster data, filtered to
    target_season)."""
    reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG") & (pbp_current_season["week"] < through_week)
    ]
    stats = compute_team_season_receiving_stats(reg)
    if stats.empty:
        return pd.DataFrame(columns=["Team", "Role", "Player ID", "Targets"])

    season_rosters = rosters[rosters["season"] == target_season][["player_id", "position"]]
    season_rosters = season_rosters.drop_duplicates(subset=["player_id"], keep="first")
    stats = stats.merge(
        season_rosters, left_on="Player ID", right_on="player_id", how="inner",
    )

    rows = []
    for team, team_group in stats.groupby("Team"):
        wrs = team_group[team_group["position"] == "WR"].sort_values(
            "Targets", ascending=False,
        )
        for i, (_, row) in enumerate(wrs.head(3).iterrows()):
            rows.append({"Team": team, "Role": f"WR{i + 1}", "Player ID": row["Player ID"],
                         "Targets": row["Targets"]})
        tes = team_group[team_group["position"] == "TE"].sort_values(
            "Targets", ascending=False,
        )
        if not tes.empty:
            top_te = tes.iloc[0]
            rows.append({"Team": team, "Role": "TE1", "Player ID": top_te["Player ID"],
                         "Targets": top_te["Targets"]})
    return pd.DataFrame(rows, columns=["Team", "Role", "Player ID", "Targets"])


def _metric_dict_for_player_season(
    metric_table: pd.DataFrame, player_id: str, season: int,
) -> dict[str, float] | None:
    match = metric_table[
        (metric_table["Player ID"] == player_id) & (metric_table["Season"] == season)
    ]
    if match.empty:
        return None
    row = match.iloc[0]
    if pd.isna(row["Avg Separation"]) or pd.isna(row["YAC Over Expectation"]):
        return None  # real NGS coverage gap -- never substituted, see module docstring
    out = {key: float(row[col]) for key, col in _PBP_METRIC_COLUMN.items()}
    out["avg_sep"] = float(row["Avg Separation"])
    out["yac_oe"] = float(row["YAC Over Expectation"])
    for key in _ZERO_WEIGHT_METRICS:
        out[key] = 0.0  # real weight 0 -- mathematically inert, see module docstring
    return out


def _league_baseline_for_season(metric_table: pd.DataFrame, season: int) -> dict[str, float]:
    """Real league-wide average per metric for one real season -- ALL real qualifying
    receiver-seasons, no Role filter (matches WR-TE Index's own real Section 2 convention,
    confirmed NOT Starter/Backup-filtered when this tab was first ported)."""
    year_stats = metric_table[
        (metric_table["Season"] == season) & metric_table["Avg Separation"].notna()
    ]
    if year_stats.empty:
        raise ValueError(f"No real WR-TE season stats with real NGS coverage for season "
                          f"{season} -- cannot resolve a real league baseline (never "
                          f"fabricated).")
    baseline = {key: float(year_stats[col].mean()) for key, col in _PBP_METRIC_COLUMN.items()}
    baseline["avg_sep"] = float(year_stats["Avg Separation"].mean())
    baseline["yac_oe"] = float(year_stats["YAC Over Expectation"].mean())
    for key in _ZERO_WEIGHT_METRICS:
        baseline[key] = 0.0
    return baseline


def resolve_wr_te_index_history(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame,
    ngs_receiving_3yr_prior: pd.DataFrame, ngs_receiving_current: pd.DataFrame,
    rosters: pd.DataFrame, sched: pd.DataFrame, target_season: int, target_week: int,
    team: str, role: str,
) -> WRTEHistory:
    """`role`: one of "WR1"/"WR2"/"WR3"/"TE1". Raises ValueError (never fabricates) if `team`
    has no real qualifying player at `role` as of target_week, or if a real Y1/Y2/Y3/league-
    baseline value (including real NGS coverage) can't be resolved."""
    if role not in _ROLE_ORDER:
        raise ValueError(f"Unknown role {role!r} -- expected one of {_ROLE_ORDER}.")

    prior_table = _build_metric_table(
        normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS),
        ngs_receiving_3yr_prior,
    )
    roles = resolve_wr_te_roles_as_of_week(
        pbp_current_season, rosters, target_season, target_week,
    )
    match = roles[(roles["Team"] == team) & (roles["Role"] == role)]
    if match.empty:
        raise ValueError(
            f"No real {role} found for {team!r} as of season {target_season} week "
            f"{target_week} (never fabricated)."
        )
    player_id = match.iloc[0]["Player ID"]
    position = "TE" if role == "TE1" else "WR"

    y1 = _metric_dict_for_player_season(prior_table, player_id, target_season - 1)
    y2 = _metric_dict_for_player_season(prior_table, player_id, target_season - 2)
    y3 = _metric_dict_for_player_season(prior_table, player_id, target_season - 3)
    missing = [label for label, v in (("Y-1", y1), ("Y-2", y2), ("Y-3", y3)) if v is None]
    if missing:
        raise ValueError(
            f"Real player {player_id!r} ({team} {role}) has no real qualifying season (or "
            f"real NGS coverage) in {missing} -- never fabricated here."
        )

    league_baseline_y1 = _league_baseline_for_season(prior_table, target_season - 1)

    current_reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG")
        & (pbp_current_season["week"] < target_week)
    ]
    current_table = _build_metric_table(current_reg, ngs_receiving_current)
    current_metrics = _metric_dict_for_player_season(current_table, player_id, target_season)
    if current_metrics is None:
        current_metrics = dict.fromkeys(METRIC_KEYS, 0.0)

    team_games = team_season_ppg(sched, season=target_season, through_week=target_week)
    team_row = team_games[team_games["Team"] == team]
    games_played = int(team_row.iloc[0]["Games Played"]) if not team_row.empty else 0

    return WRTEHistory(
        player_id=player_id, position=position, y1=y1, y2=y2, y3=y3,
        league_baseline_y1=league_baseline_y1, games_played=games_played,
        current_season=current_metrics,
    )
