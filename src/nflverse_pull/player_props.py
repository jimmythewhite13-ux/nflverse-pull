"""
Real data layer for claude_code_spec_player_prop_projections.md -- Volume x Per-Unit-
Efficiency, deterministic point-estimate projections. No scraping, no Monte Carlo -- see
that spec's own explicit "what this is NOT" section.

compute_team_season_pass_rush_volume(): real team-level Pass Attempts/Game and Rush
Attempts/Game -- feeds Part A's "Expected Volume" (team pace, before the real game-script
adjustment applied in Excel using Season Matchups' own already-entered spread).

compute_player_season_qb_yards_per_attempt(): a SEPARATE, PURE Yards/Attempt metric,
deliberately distinct from QB Index's own ANY/A (which bakes in +20*TD/-45*INT, correct for
skill evaluation but wrong for projecting raw passing yards -- a QB's ANY/A can be inflated
by touchdowns without his actual yards-per-attempt being high, per the spec's own explicit
instruction). ANY/A itself is never touched by this module.

compute_player_season_target_share(): real player Target Share = that player's own real
targets / his team's own real total real pass attempts that season -- genuinely new,
distinct from claude_code_spec_route_redzone_usage.md's own Pass-Play Snap Participation %
(which measures how often a player runs a route, not how often he's actually targeted).

compute_player_season_catch_rate(): real Receptions/Targets per player-season -- the
"derivable from existing Success Rate/completion data" the spec calls for.
"""
from __future__ import annotations

import pandas as pd

from nflverse_pull.pull import TEAM_NAMES


def compute_team_season_pass_rush_volume(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real team-level Pass Attempts/Game and Rush Attempts/Game,
    per real (Team, Season). "Pass Attempts" here means real real dropbacks that end in a
    real thrown pass (pass_attempt==1, sacks excluded -- a sack is a real dropback but not
    a real "pass attempt" in the standard box-score sense); "Rush Attempts" means real
    play_type=="run" plays. Both divided by that team's own real number of games played
    that season (from the same real play-by-play, not assumed to be a fixed 17).

    Output: Team | Season | Pass Attempts/Game | Rush Attempts/Game
    """
    reg = pbp[pbp["season_type"] == "REG"]

    pass_plays = reg[reg["pass_attempt"] == 1]
    rush_plays = reg[reg["play_type"] == "run"]

    games = reg.groupby(["posteam", "season"])["game_id"].nunique().rename("games")
    pass_att = pass_plays.groupby(["posteam", "season"]).size().rename("pass_att")
    rush_att = rush_plays.groupby(["posteam", "season"]).size().rename("rush_att")

    out = games.to_frame().join(pass_att).join(rush_att).fillna(0).reset_index()
    unmapped = sorted(set(out["posteam"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["posteam"].map(TEAM_NAMES)
    out["Pass Attempts/Game"] = out["pass_att"] / out["games"]
    out["Rush Attempts/Game"] = out["rush_att"] / out["games"]
    out = out.rename(columns={"season": "Season"})
    return out[["Team", "Season", "Pass Attempts/Game", "Rush Attempts/Game"]]


def compute_player_season_qb_yards_per_attempt(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real PURE Yards/Attempt per (Player ID, Season, Team) --
    real passing_yards summed over real thrown pass attempts (sacks excluded, since a sack
    has no real passing yards and isn't a real "attempt" in the box-score sense), divided
    by that same real attempt count. Deliberately does NOT touch ANY/A (QB Index's own
    skill-evaluation metric, which stays as-is) -- this is a separate real metric for
    volume-projection purposes only, per the spec's own explicit instruction.

    Output: Player ID | Season | Team | Y/A
    """
    reg = pbp[pbp["season_type"] == "REG"]
    attempts = reg[(reg["pass_attempt"] == 1) & (reg["sack"] == 0)]
    attempts = attempts[attempts["passer_id"].notna()]

    group_cols = ["passer_id", "season", "posteam"]
    att_count = attempts.groupby(group_cols).size().rename("att")
    pass_yards = attempts.groupby(group_cols)["passing_yards"].sum().rename("yards")

    out = att_count.to_frame().join(pass_yards).reset_index()
    unmapped = sorted(set(out["posteam"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["posteam"].map(TEAM_NAMES)
    out["Y/A"] = out["yards"] / out["att"]
    out = out.rename(columns={"passer_id": "Player ID", "season": "Season"})
    return out[["Player ID", "Season", "Team", "Y/A"]]


def compute_player_season_target_share(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real player Target Share = that player's own real targets
    (real thrown pass attempts, sacks excluded, credited to a real receiver_player_id)
    divided by his own team's real TOTAL pass attempts that season (the same real
    denominator compute_team_season_pass_rush_volume() uses, joined by (Team, Season) --
    not re-derived independently, to avoid two versions of "team pass attempts" silently
    drifting apart).

    Output: Player ID | Season | Team | Target Share
    """
    reg = pbp[pbp["season_type"] == "REG"]
    targets = reg[(reg["pass_attempt"] == 1) & (reg["sack"] == 0)]
    targets = targets[targets["receiver_player_id"].notna()]

    player_targets = (
        targets.groupby(["receiver_player_id", "season", "posteam"]).size().rename("targets")
    )
    team_pass_att = (
        reg[reg["pass_attempt"] == 1].groupby(["posteam", "season"]).size().rename("team_att")
    )

    out = player_targets.reset_index()
    out = out.merge(
        team_pass_att.reset_index(), on=["posteam", "season"], how="left",
    )
    unmapped = sorted(set(out["posteam"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["posteam"].map(TEAM_NAMES)
    out["Target Share"] = out["targets"] / out["team_att"]
    out = out.rename(columns={"receiver_player_id": "Player ID", "season": "Season"})
    return out[["Player ID", "Season", "Team", "Target Share"]]


def compute_player_season_catch_rate(pbp: pd.DataFrame) -> pd.DataFrame:
    """
    Pure function, no network. Real Catch Rate = real completions credited to a receiver
    divided by his own real targets that season -- "derivable from existing Success Rate/
    completion data" per the spec's own instruction (complete_pass is real nflverse pbp
    data, not derived/estimated).

    Output: Player ID | Season | Team | Catch Rate
    """
    reg = pbp[pbp["season_type"] == "REG"]
    targets = reg[(reg["pass_attempt"] == 1) & (reg["sack"] == 0)]
    targets = targets[targets["receiver_player_id"].notna()]

    group_cols = ["receiver_player_id", "season", "posteam"]
    target_count = targets.groupby(group_cols).size().rename("targets")
    completions = targets.groupby(group_cols)["complete_pass"].sum().rename("completions")

    out = target_count.to_frame().join(completions).reset_index()
    unmapped = sorted(set(out["posteam"]) - set(TEAM_NAMES))
    if unmapped:
        raise ValueError(f"No full-name mapping for team abbreviation(s): {unmapped}")
    out["Team"] = out["posteam"].map(TEAM_NAMES)
    out["Catch Rate"] = out["completions"] / out["targets"]
    out = out.rename(columns={"receiver_player_id": "Player ID", "season": "Season"})
    return out[["Player ID", "Season", "Team", "Catch Rate"]]
