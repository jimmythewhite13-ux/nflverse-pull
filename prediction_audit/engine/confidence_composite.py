"""
Market Comparison & Confidence's own real Confidence Composite (Part B) -- 4 real, small,
transparent components, weighted-summed, then bucketed into a real tier. Confirmed from the
real formula text directly; every underlying real fact each component reads (games played,
Backup-In status, manual roster overrides, a team's real starting Center's rookie status) is
taken here as an already-resolved given input per this project's established "arithmetic
only, not data sourcing" scoping -- these are roster/data-resolution facts, not Z/AA
arithmetic, same treatment as every other tab's own real inputs throughout this engine.

Real formulas, confirmed from the text (row 4, generalized to row r):

    Sample Size Component (P) =MIN(1,((HomeGamesPlayed+AwayGamesPlayed)/2)/17)

    QB/Override Certainty Component (Q) =1-((HomeBackupIn + AwayBackupIn +
        HomeHasOverride + AwayHasOverride)/4)
        -- each of the 4 terms is a real 0/1 flag; HasOverride is real (QB Index's own
        Section 7 Manual Roster Override table -- blank by default, filled in only when a
        beat-writer report supersedes the pulled roster).

    OL Center Continuity Component (R) =1-((HomeCenterIsRookie + AwayCenterIsRookie)/2)
        -- real per-team fact: is that team's real starting Center (Offensive Line Index's
        own Section 6, Position="C") a real rookie starter.

    Matchup Agreement Component (S) =IF(ModelSpread="","",
        (agree(Y,G)+agree(Z,G)+agree(AA,G))/3)
        where Y/Z/AA are real Net Home Advantage differentials (Phase Matchup Adj Home-Away,
        OL Pressure Adj Home-Away, Explosive Play Adj Home-Away -- all already composable
        from this project's own already-ported engines) and agree(x,G) is 1 exactly when
        Excel's own SIGN(x)=SIGN(G) (SIGN(0)=0 -- ties never "agree" with a nonzero spread,
        and a genuinely 0 spread ties with everything, including another 0).

    Confidence Composite (T) =P*C172 + Q*C173 + R*C174 + IF(S="",0,S)*C175

    Confidence Tier (U): tiered lookup on C176 (Low/Medium) < C177 (Medium/Medium-High) <
        C178 (Medium-High/High), real tunable thresholds.
"""
from __future__ import annotations


def _excel_sign(x: float) -> int:
    if x > 0:
        return 1
    if x < 0:
        return -1
    return 0


def sample_size_component(
    home_games_played: float, away_games_played: float, full_sample_games: float = 17.0,
) -> float:
    return min(1.0, ((home_games_played + away_games_played) / 2) / full_sample_games)


def qb_override_certainty_component(
    home_backup_in: str, away_backup_in: str,
    home_has_override: bool, away_has_override: bool,
) -> float:
    home_backup_flag = 1 if home_backup_in == "Backup In" else 0
    away_backup_flag = 1 if away_backup_in == "Backup In" else 0
    return 1 - (
        (home_backup_flag + away_backup_flag + int(home_has_override) + int(away_has_override))
        / 4
    )


def ol_center_continuity_component(
    home_center_is_rookie: bool, away_center_is_rookie: bool,
) -> float:
    return 1 - ((int(home_center_is_rookie) + int(away_center_is_rookie)) / 2)


def matchup_agreement_component(
    phase_net_home_adv: float, ol_pressure_net_home_adv: float,
    explosive_net_home_adv: float, model_spread: float | None,
) -> float | None:
    if model_spread in (None, ""):
        return None
    spread_sign = _excel_sign(model_spread)
    agreements = sum(
        1 for signal in (phase_net_home_adv, ol_pressure_net_home_adv, explosive_net_home_adv)
        if _excel_sign(signal) == spread_sign
    )
    return agreements / 3


def confidence_composite(
    sample_size: float, qb_override_certainty: float, ol_center_continuity: float,
    matchup_agreement: float | None,
    sample_size_weight: float, qb_override_weight: float, ol_continuity_weight: float,
    matchup_agreement_weight: float,
) -> float:
    matchup_agreement_or_zero = 0.0 if matchup_agreement is None else matchup_agreement
    return (
        sample_size * sample_size_weight
        + qb_override_certainty * qb_override_weight
        + ol_center_continuity * ol_continuity_weight
        + matchup_agreement_or_zero * matchup_agreement_weight
    )


def confidence_tier(
    composite: float, low_medium: float, medium_medium_high: float, medium_high_high: float,
) -> str:
    if composite >= medium_high_high:
        return "High"
    if composite >= medium_medium_high:
        return "Medium-High"
    if composite >= low_medium:
        return "Medium"
    return "Low"
