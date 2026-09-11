// Real, week-level caveat -- explains the overall prediction-gating situation once, instead of
// requiring every individual game's drill-down to be opened to understand why none show a
// model prediction yet. Computed fresh from this week's actual real game states every load --
// never hardcoded to a week number, so it reflects reality even if the real schedule/gating
// ever shifts. Deliberately scoped to weeks 1-4 only (see week_level_caveat_banners.md) --
// weeks 5+ never show this banner; individual games' own honest "not yet predicted" states
// (already in the per-game drill-down) are sufficient once the mechanism is proven at Week 4.
export function computeWeekCaveat(games, week) {
  if (!games.length || week > 4) return null;
  const allNotPredictable = games.every(g => g.status === "NOT_PREDICTABLE");
  if (allNotPredictable) {
    return "Real market lines below are current, live sportsbook data. Game-level model " +
      "predictions aren't available for Weeks 1-3 in any season -- there's no reliable way " +
      "yet to confirm who's actually starting for each team this early. Predictions begin " +
      "appearing from Week 4 onward.";
  }
  if (week !== 4) return null;
  const anyHasPrediction = games.some(g => g.has_prediction);
  if (!anyHasPrediction) {
    return "Real market lines below are current, live sportsbook data. Model predictions " +
      "begin appearing for Week 4 games individually, as each one crosses its real 48-hour " +
      "pre-kickoff cutoff -- not all at once. A game showing “Not yet predicted” " +
      "simply hasn't reached that point yet.";
  }
  const allHavePrediction = games.every(g => g.has_prediction);
  if (allHavePrediction) return null;  // real, fully populated -- no caveat needed
  // Real, adjusted wording once predictions have genuinely started -- present tense, not
  // frozen as "begin appearing" after they already have.
  return "Real market lines below are current, live sportsbook data. Model predictions have " +
    "started appearing for some Week 4 games as each crosses its real 48-hour pre-kickoff " +
    "cutoff -- others are still pending theirs. A game showing “Not yet predicted” " +
    "simply hasn't reached that point yet.";
}
