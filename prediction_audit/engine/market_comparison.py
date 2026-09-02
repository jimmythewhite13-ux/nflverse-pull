"""
Market Comparison & Confidence's own real Win Probability model -- Part A of that tab. Takes
season_matchups.compute_model_home_away_score()'s own real output (Model Margin = Home Score
- Away Score, matching Season Matchups' own real AC column) and converts it to a real home
win probability via a standard logistic transform.

Real formula, confirmed from the text directly:
    Win Probability (Home) =1/(1+EXP(-Margin/C171))
        where C171 = "Win Probability Logistic Slope (pts per logit)", a real tunable
        Model Assumptions constant (10.5 in the frozen v35 baseline).

Part B of this tab (Confidence Composite) is ported separately in confidence_composite.py.

Also includes the real "Model WP -> ML" conversion (Part A's own columns BB/BC): the model's
own real win probability, converted to a real American moneyline. Standard formula, confirmed
from the text -- favorites (win prob >= 50%) get a negative line, underdogs a positive one:
    Home =IF(WP>=0.5, -(WP/(1-WP))*100, ((1-WP)/WP)*100)
    Away = the same formula applied to (1-WP)

The rest of this tab's real Moneyline system (Home/Away Moneyline itself, Raw/De-Vigged
Implied Probability, Moneyline Edge) is NOT ported: Season Matchups' own real Home/Away
Moneyline input cells (DG/DH) are confirmed blank for every one of the 272 real 2026 games (no
manual entry was ever made) -- every downstream column has zero real Excel-computed value to
verify against, not just a documented zero-coverage branch. Kalshi/Polymarket contract prices
are confirmed blank for the same reason (manual entry only), and separately carry a real,
active legal-availability caveat per this tab's own opening disclaimer. See PROGRESS.md.
"""
from __future__ import annotations

import math


def win_probability_home(model_margin: float, logistic_slope: float) -> float:
    return 1 / (1 + math.exp(-model_margin / logistic_slope))


def model_win_probability_to_moneyline(win_probability: float) -> float:
    """Real American-odds conversion of a real win probability -- applied to win_probability_
    home() for the home line, and to (1 - win_probability_home()) for the away line."""
    if win_probability >= 0.5:
        return -(win_probability / (1 - win_probability)) * 100
    return ((1 - win_probability) / win_probability) * 100
