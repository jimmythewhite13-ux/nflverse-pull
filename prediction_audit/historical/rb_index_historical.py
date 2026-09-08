"""
Step 6: resolves a real historical RB Value Index for one real team's Starter or Backup, using
only real data available before a target game's own kickoff -- the second player-level index
made walk-forward-capable, following the exact pattern QB Index proved out.

Reuses nflverse_pull.rb_stats's own already-real, already-parameterized functions
(`compute_team_season_rb_stats`, `compute_historical_rb_roles`,
`compute_player_season_red_zone_carry_share`, `fetch_ngs_rushing`/`compute_player_season_ryoe`)
-- built for the live 2026 pipeline but take pbp/season years directly, so they work unchanged
for a historical target.

Real historical Starter/Backup role resolution reuses `compute_historical_rb_roles()`'s own
real carries-ranking method, applied to the target season's own real carries-so-far (strictly
before the target week) -- the exact same walk-forward-appropriate use QB Index's own
dropback-ranking proxy gets, even though the LIVE 2026 pipeline itself uses this function only
to label PAST seasons (current Starter/Backup there comes from live depth-chart data, which
has no meaning for an arbitrary past date).

Two of the 5 real metrics need extra real data sources, not just pbp:
- **RYOE/Att** needs real NGS rushing data (`fetch_ngs_rushing`) -- NOT full-coverage the way
  the pbp-derived metrics are (confirmed in rb_index.py's own module docstring). v35's own real
  Y-1/Y-2/Y-3 substitution formula for this specific metric is measurably different (an extra
  existence check + ISBLANK-guarded rookie fallback) and has NOT been replicated here -- a real
  player-season missing real NGS RYOE data raises (skipped), same as a real missing rushing-
  EPA/SR/YPC season, rather than attempting an unverified substitute.
- **Red-Zone Carry Share** carries a real weight of 0 (Step 4's own extraction, confirmed
  again in rb_index.py's docstring) -- included for completeness, not because it affects any
  real score. A player with zero real qualifying red-zone carries in a season genuinely has a
  real 0.0 share (not a data gap), so this one metric defaults to 0.0 rather than raising.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.rb_stats import (
    compute_historical_rb_roles,
    compute_player_season_red_zone_carry_share,
    compute_player_season_ryoe,
    compute_team_season_rb_stats,
)
from prediction_audit.engine.rb_index import METRIC_KEYS, RBHistory, compute_rb_index
from prediction_audit.historical.relocations import (
    PBP_TEAM_COLUMNS,
    normalize_relocated_abbreviations,
)
from prediction_audit.historical.team_ppg import team_season_ppg

_PBP_METRIC_COLUMN = {
    "rushing_epa": "Rushing EPA/Play", "rushing_sr": "Rushing Success Rate", "ypc": "YPC",
}


def resolve_rb_roles_as_of_week(
    pbp_current_season: pd.DataFrame, through_week: int,
) -> pd.DataFrame:
    """Real Team|Role (Starter/Backup/Other) as of `through_week` (weeks strictly before it
    only), via the project's own real compute_team_season_rb_stats + compute_historical_rb_roles
    chain applied to a real partial-season pbp slice."""
    reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG") & (pbp_current_season["week"] < through_week)
    ]
    season_stats = compute_team_season_rb_stats(reg)
    if season_stats.empty:
        return season_stats.assign(Role=pd.Series(dtype=str))
    return compute_historical_rb_roles(season_stats)


def _build_metric_table(pbp: pd.DataFrame, ngs_rushing: pd.DataFrame) -> pd.DataFrame:
    """Real merged per-(Player ID, Season) metric table across all 5 real metrics, from the 3
    real underlying sources -- pbp-derived rushing stats, real NGS RYOE, real red-zone share."""
    rb_stats = compute_team_season_rb_stats(pbp)
    rz_stats = compute_player_season_red_zone_carry_share(pbp)
    # Real NGS data quirk (verified live, confirmed to real players -- not a bug in this
    # module): a small number of real season-aggregate rows (7/149 in 2021, notable qualifying
    # backs among them) carry a null team_abbr. compute_player_season_ryoe() has no full-name
    # mapping for None and raises on it -- filtered out here (that player-season's RYOE is
    # then genuinely unresolvable and correctly triggers this module's own real
    # missing-data-never-fabricated path downstream) rather than modifying the shared function.
    ngs_rushing = ngs_rushing[ngs_rushing["team_abbr"].notna()]
    ryoe_stats = compute_player_season_ryoe(ngs_rushing)

    merged = rb_stats.merge(
        rz_stats[["Player ID", "Season", "Red-Zone Carry Share"]],
        on=["Player ID", "Season"], how="left",
    )
    merged["Red-Zone Carry Share"] = merged["Red-Zone Carry Share"].fillna(0.0)
    merged = merged.merge(
        ryoe_stats[["Player ID", "Season", "RYOE/Att"]],
        on=["Player ID", "Season"], how="left",
    )
    return merged


def _metric_dict_for_player_season(
    metric_table: pd.DataFrame, player_id: str, season: int,
) -> dict[str, float] | None:
    match = metric_table[
        (metric_table["Player ID"] == player_id) & (metric_table["Season"] == season)
    ]
    if match.empty:
        return None
    row = match.iloc[0]
    if pd.isna(row["RYOE/Att"]):
        return None  # real NGS coverage gap -- never substituted here, see module docstring
    out = {key: float(row[col]) for key, col in _PBP_METRIC_COLUMN.items()}
    out["ryoe"] = float(row["RYOE/Att"])
    out["rz_share"] = float(row["Red-Zone Carry Share"])
    return out


def _league_baseline_for_season(metric_table: pd.DataFrame, season: int) -> dict[str, float]:
    """Real Starters+Backups-only league average per metric for one real season."""
    year_stats = metric_table[metric_table["Season"] == season]
    if year_stats.empty:
        raise ValueError(f"No real RB season stats for season {season} -- cannot resolve a "
                          f"real league baseline (never fabricated).")
    roles = compute_historical_rb_roles(year_stats)
    qualifying_ids = set(roles[roles["Role"] != "Other"]["Player ID"])
    pool = year_stats[
        year_stats["Player ID"].isin(qualifying_ids) & year_stats["RYOE/Att"].notna()
    ]
    if pool.empty:
        raise ValueError(f"No real Starters/Backups with real RYOE data found for season "
                          f"{season} -- cannot resolve a real league baseline (never "
                          f"fabricated).")
    baseline = {key: float(pool[col].mean()) for key, col in _PBP_METRIC_COLUMN.items()}
    baseline["ryoe"] = float(pool["RYOE/Att"].mean())
    baseline["rz_share"] = float(pool["Red-Zone Carry Share"].mean())
    return baseline


def _resolve_history_for_player(
    player_id: str, team: str, prior_metrics: pd.DataFrame, current_metrics_table: pd.DataFrame,
    sched_games: pd.DataFrame, target_season: int, league_baseline_y1: dict[str, float],
) -> RBHistory | None:
    y1 = _metric_dict_for_player_season(prior_metrics, player_id, target_season - 1)
    y2 = _metric_dict_for_player_season(prior_metrics, player_id, target_season - 2)
    y3 = _metric_dict_for_player_season(prior_metrics, player_id, target_season - 3)
    if y1 is None or y2 is None or y3 is None:
        return None

    current = _metric_dict_for_player_season(current_metrics_table, player_id, target_season)
    if current is None:
        current = dict.fromkeys(METRIC_KEYS, 0.0)

    team_row = sched_games[sched_games["Team"] == team]
    games_played = int(team_row.iloc[0]["Games Played"]) if not team_row.empty else 0

    return RBHistory(
        player_id=player_id, y1=y1, y2=y2, y3=y3,
        league_baseline_y1=league_baseline_y1, games_played=games_played,
        current_season=current,
    )


def resolve_rb_index_history(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame,
    ngs_rushing_3yr_prior: pd.DataFrame, ngs_rushing_current: pd.DataFrame,
    sched: pd.DataFrame, target_season: int, target_week: int,
    team: str, role: str,
) -> RBHistory:
    """Raises ValueError (never fabricates) if `team` has no real qualifying RB at `role` as of
    target_week, or if a real Y1/Y2/Y3/league-baseline value can't be resolved."""
    prior_pbp = normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    prior_metrics = _build_metric_table(prior_pbp, ngs_rushing_3yr_prior)

    current_roles = resolve_rb_roles_as_of_week(pbp_current_season, target_week)
    match = current_roles[(current_roles["Team"] == team) & (current_roles["Role"] == role)]
    if match.empty:
        raise ValueError(
            f"No real {role} found for {team!r} as of season {target_season} week "
            f"{target_week} (never fabricated)."
        )
    player_id = match.iloc[0]["Player ID"]

    league_baseline_y1 = _league_baseline_for_season(prior_metrics, target_season - 1)

    current_reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG")
        & (pbp_current_season["week"] < target_week)
    ]
    current_metrics_table = _build_metric_table(current_reg, ngs_rushing_current)
    team_games = team_season_ppg(sched, season=target_season, through_week=target_week)

    history = _resolve_history_for_player(
        player_id, team, prior_metrics, current_metrics_table, team_games, target_season,
        league_baseline_y1,
    )
    if history is None:
        raise ValueError(
            f"Real player {player_id!r} ({team} {role}) has no real qualifying season (or real "
            f"NGS RYOE coverage) in Y-1/Y-2/Y-3 -- never fabricated here."
        )
    return history


def resolve_rb_index_league_stats(
    pbp_3yr_prior: pd.DataFrame, pbp_current_season: pd.DataFrame,
    ngs_rushing_3yr_prior: pd.DataFrame, ngs_rushing_current: pd.DataFrame,
    sched: pd.DataFrame, target_season: int, target_week: int,
    constants_without_league_stats,
) -> dict[str, dict[str, float]]:
    """Real Section 4: league-wide average/std-dev of the real BLENDED metric value, across
    every real Starter/Backup league-wide as of target_week -- same real convention as QB
    Index's own resolve_qb_index_league_stats(). Real players missing Y-1/Y-2/Y-3 (or real NGS
    RYOE coverage) are skipped, never fabricated a substitute."""
    prior_pbp = normalize_relocated_abbreviations(pbp_3yr_prior, columns=PBP_TEAM_COLUMNS)
    prior_metrics = _build_metric_table(prior_pbp, ngs_rushing_3yr_prior)

    current_roles = resolve_rb_roles_as_of_week(pbp_current_season, target_week)
    qualifying = current_roles[current_roles["Role"].isin(["Starter", "Backup"])]

    league_baseline_y1 = _league_baseline_for_season(prior_metrics, target_season - 1)
    current_reg = pbp_current_season[
        (pbp_current_season["season_type"] == "REG")
        & (pbp_current_season["week"] < target_week)
    ]
    current_metrics_table = _build_metric_table(current_reg, ngs_rushing_current)
    team_games = team_season_ppg(sched, season=target_season, through_week=target_week)

    blended_values: dict[str, list[float]] = {key: [] for key in METRIC_KEYS}
    for _, row in qualifying.iterrows():
        history = _resolve_history_for_player(
            row["Player ID"], row["Team"], prior_metrics, current_metrics_table, team_games,
            target_season, league_baseline_y1,
        )
        if history is None:
            continue
        result = compute_rb_index(history, constants_without_league_stats)
        for key in METRIC_KEYS:
            blended_values[key].append(result.blended[key])

    stats = {}
    for key in METRIC_KEYS:
        values = pd.Series(blended_values[key])
        if values.empty:
            raise ValueError(
                f"No real qualifying RBs resolved league-wide for metric {key!r} as of "
                f"season {target_season} week {target_week} (never fabricated)."
            )
        stats[key] = {"avg": float(values.mean()), "std": float(values.std(ddof=0))}
    return stats
