// Real, shared mutable state -- a single, real source of truth across modules (mutated via
// property assignment, e.g. state.viewingWeek = 4, not by reassigning the whole export, per
// real ES module semantics for a const binding).
export const state = {
  currentWeek: null,
  viewingWeek: null,
  loadedGames: [],   // real, currently-loaded week's games -- source for both views + filter
  activeView: "games",
  teamFilter: null,  // real, selected team abbreviation (or null) -- set via team-filter.js's
                      // autocomplete selection, not raw input text (see that module's own note)
};
