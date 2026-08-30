"""
Rank -> percentile -> historical-tier crosswalk for rookie assumptions, using real
draft-market data instead of a single flat Rookie Baseline. See
claude_code_spec_rookie_adp_crosswalk.md. Position-generic (works for QB, RB, and any future
position) -- pass in whichever metric columns and rookie-season stats apply.

Never write a market number (ADP, trade value) directly into a stat column -- it only
decides which historical performance tier a rookie's assumption comes from.

Data sources, checked live against the real APIs before writing this (not guessed):
  - Fantasy Football Calculator's Dynasty Rookie ADP API (primary, per the spec). Confirmed
    real endpoint: https://fantasyfootballcalculator.com/api/v1/adp/rookie -- the exact
    format slug ("rookie") was found from the site's own /adp page (labeled "Dynasty Rookie
    ADP"), not the sparse help-center docs, and verified by checking the response's own
    meta.type field ("Dynasty Rookie"). As of this writing it genuinely returns an empty
    players array (confirmed via direct curl, not a parsing artifact) -- too early in the
    2026 rookie class's draft cycle for FFC's aggregation to have populated players yet.
  - api.fantasycalc.com dynasty trade values (secondary/fallback per the spec) -- used here
    as the effective primary source, since FFC's rookie-specific data is empty for every
    player right now, which the spec's own fallback language ("unavailable... doesn't cover
    a given player") anticipates.
  - nfl_data_py.import_ids() for real draft_round/draft_pick per player (used for the
    HISTORICAL tier crosswalk, segmenting 2023-2025 rookie seasons -- draft round is the
    real, available stand-in for "how regarded was this player entering his rookie year";
    we don't have historical ADP pulled for past rookie classes).
"""
from __future__ import annotations

import pandas as pd

TIER_TOP = "Tier 1 (Top)"
TIER_MID = "Tier 2 (Mid)"
TIER_LATE = "Tier 3 (Late/UDFA)"
TIER_LABELS = [TIER_TOP, TIER_MID, TIER_LATE]

# Draft-round cutoffs for the HISTORICAL tier crosswalk -- Round 1 is its own tier (the
# clearest "highly regarded" signal), Rounds 2-3 are a middle tier, Round 4+ or undrafted
# (no draft_round at all) is the late/UDFA tier.
TIER_1_MAX_ROUND = 1
TIER_2_MAX_ROUND = 3


def fetch_ffc_dynasty_rookie_adp(teams: int = 12) -> pd.DataFrame:
    """
    Network call. Primary source per the spec. Returns an empty DataFrame (not an error) if
    FFC has no players populated yet for this query -- confirmed this genuinely happens
    early in a rookie class's draft cycle, not a bug in this function.
    """
    import requests

    resp = requests.get(
        "https://fantasyfootballcalculator.com/api/v1/adp/rookie",
        params={"teams": teams, "position": "all"},
        timeout=30,
    )
    resp.raise_for_status()
    players = resp.json().get("players", [])
    if not players:
        return pd.DataFrame(columns=["name", "position", "adp", "times_drafted"])
    return pd.DataFrame(players)


def fetch_fantasycalc_values(num_qbs: int = 1, num_teams: int = 12, ppr: int = 1) -> pd.DataFrame:
    """Network call. Secondary/fallback source per the spec -- dynasty trade values."""
    import requests

    resp = requests.get(
        "https://api.fantasycalc.com/values/current",
        params={"isDynasty": "true", "numQbs": num_qbs, "numTeams": num_teams, "ppr": ppr},
        timeout=30,
    )
    resp.raise_for_status()
    return pd.json_normalize(resp.json())


def fetch_draft_info() -> pd.DataFrame:
    """Network call -- nflverse's player ID crosswalk, carrying real draft_round/draft_pick."""
    import nfl_data_py as nfl

    return nfl.import_ids()


def assign_historical_tier(draft_round: float | None) -> str:
    """Pure function. Maps a draft round to a historical tier; undrafted (NaN) -> late/UDFA."""
    if draft_round is None or pd.isna(draft_round):
        return TIER_LATE
    if draft_round <= TIER_1_MAX_ROUND:
        return TIER_TOP
    if draft_round <= TIER_2_MAX_ROUND:
        return TIER_MID
    return TIER_LATE


def compute_historical_tier_averages(
    rookie_season_stats: pd.DataFrame,
    draft_info: pd.DataFrame,
    metric_cols: list[str],
    id_col: str = "Player ID",
) -> pd.DataFrame:
    """
    Pure function, no network. Segments `rookie_season_stats` (rows already filtered to
    Is Rookie Season == True) into the 3 historical tiers by draft round, and computes each
    tier's average across `metric_cols` plus its sample size -- same small-sample honesty
    already applied to the flat Rookie Baseline (label a tier with few examples as such;
    don't hide it).
    """
    draft_lookup = draft_info.dropna(subset=["gsis_id"]).set_index("gsis_id")["draft_round"]
    draft_lookup = draft_lookup[~draft_lookup.index.duplicated(keep="first")].to_dict()

    df = rookie_season_stats.copy()
    df["Historical Tier"] = df[id_col].map(
        lambda pid: assign_historical_tier(draft_lookup.get(pid))
    )

    rows = []
    for tier in TIER_LABELS:
        tier_df = df[df["Historical Tier"] == tier]
        row: dict[str, object] = {"Historical Tier": tier, "Sample Size": len(tier_df)}
        for col in metric_cols:
            row[col] = tier_df[col].mean() if len(tier_df) else None
        rows.append(row)
    return pd.DataFrame(rows)


def rank_rookie_class(
    market_data: pd.DataFrame,
    rank_col: str,
    ascending: bool,
    name_col: str = "name",
) -> pd.DataFrame:
    """
    Pure function, no network. Ranks a rookie class (already position-filtered by the
    caller) by `rank_col` (ascending=True if lower is better, e.g. ADP; False if higher is
    better, e.g. trade value), converts rank to a percentile (100 = best), and assigns each
    rookie to an Assumption Tier by splitting the class into top/middle/bottom thirds -- the
    same 3-way split the historical draft-round tiers use, so a rookie's percentile within
    THIS year's class maps onto the same tier structure as the historical crosswalk.
    """
    df = market_data.sort_values(rank_col, ascending=ascending).reset_index(drop=True)
    n = len(df)
    if n == 0:
        return df.assign(**{"Position Rank": [], "Percentile": [], "Assumption Tier": []})

    df["Position Rank"] = range(1, n + 1)
    df["Percentile"] = [100.0 * (n - i) / n for i in range(n)]
    # Exact thirds (100/3, 200/3), not the rounded 33.33/66.67 -- a percentile computed via
    # float division (e.g. 100/3 = 33.333...) must land in the SAME bin its own exact
    # fraction defines, or floating-point rounding silently bumps a boundary case into the
    # wrong tier.
    df["Assumption Tier"] = pd.cut(
        df["Percentile"], bins=[-0.01, 100 / 3, 200 / 3, 100.01],
        labels=[TIER_LATE, TIER_MID, TIER_TOP],
    ).astype(str)
    df = df.rename(columns={name_col: "Player Name"})
    return df


def assign_rookie_assumptions(
    rookie_class_ranking: pd.DataFrame,
    tier_averages: pd.DataFrame,
    metric_cols: list[str],
    flat_rookie_baseline: dict[str, float],
    all_rookie_names: list[str],
) -> pd.DataFrame:
    """
    Pure function, no network. Assigns each rookie in `all_rookie_names` his tier's
    historical average per metric. A rookie present in `rookie_class_ranking` gets his
    tier's average (or the flat baseline if that tier has zero historical sample size). A
    rookie MISSING from `rookie_class_ranking` entirely (no market data found for him at
    all -- an extremely deep UDFA) falls back to the flat Rookie Baseline. Either way,
    Source records exactly which happened -- never left ambiguous.
    """
    tier_lookup = tier_averages.set_index("Historical Tier")
    rank_lookup = (
        rookie_class_ranking.set_index("Player Name") if len(rookie_class_ranking) else None
    )

    rows = []
    for name in all_rookie_names:
        if rank_lookup is not None and name in rank_lookup.index:
            tier = rank_lookup.loc[name, "Assumption Tier"]
            has_tier = tier in tier_lookup.index
            sample_size = int(tier_lookup.loc[tier, "Sample Size"]) if has_tier else 0
            if sample_size > 0:
                row = {"Player Name": name, "Assumption Tier": tier, "Sample Size": sample_size,
                       "Source": "market-informed tier average"}
                for col in metric_cols:
                    row[col] = tier_lookup.loc[tier, col]
                rows.append(row)
                continue
        row = {"Player Name": name, "Assumption Tier": None, "Sample Size": None,
               "Source": "flat Rookie Baseline (no market data or empty tier)"}
        row.update(flat_rookie_baseline)
        rows.append(row)

    return pd.DataFrame(rows)
