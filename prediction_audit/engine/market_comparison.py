"""
Market Comparison & Confidence's own real Win Probability model -- Part A of that tab. Takes
season_matchups.compute_model_home_away_score()'s own real output (Model Margin = Home Score
- Away Score, matching Season Matchups' own real AC column) and converts it to a real home
win probability via a standard logistic transform.

Real formula, confirmed from the text directly:
    Win Probability (Home) =1/(1+EXP(-Margin/C171))
        where C171 = "Win Probability Logistic Slope (pts per logit)", a real tunable
        Model Assumptions constant (10.5 in the frozen v35 baseline).

Part B of this tab (Confidence Composite -- Sample Size / QB-Override-Certainty / OL-Center-
Continuity / Matchup-Agreement components) is a separate, larger real system not yet ported;
see PROGRESS.md.
"""
from __future__ import annotations

import math


def win_probability_home(model_margin: float, logistic_slope: float) -> float:
    return 1 / (1 + math.exp(-model_margin / logistic_slope))
