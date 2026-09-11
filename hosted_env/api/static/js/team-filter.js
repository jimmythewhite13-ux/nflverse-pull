// Real, ported autocomplete team filter -- consolidated_outstanding_queue.md item 3.
// Reference implementation verified working in interface_mockup_home_drilldown.html: the team
// suggestions list stays hidden until typing, matches highlight live, clicking a suggestion
// applies the filter and shows a clearable "Showing: X" chip. Adapted here to drive this app's
// REAL, already-existing filtering (state.teamFilter + views.js's renderCurrentView(), which
// re-renders from real fetched data) instead of the mockup's static DOM row show/hide -- the
// interaction model is the same, the plumbing underneath is real, not static markup.
import { state } from "./state.js";
import { ALL_TEAMS } from "./teams.js";
import { renderCurrentView } from "./views.js";

let inputEl, suggestionsEl, chipEl, chipNameEl;

export function initTeamFilter() {
  inputEl = document.getElementById("team-filter-input");
  suggestionsEl = document.getElementById("team-suggestions");
  chipEl = document.getElementById("active-filter-chip");
  chipNameEl = document.getElementById("active-filter-name");

  inputEl.addEventListener("input", () => {
    const query = inputEl.value.trim().toUpperCase();
    if (!query) {
      suggestionsEl.classList.remove("visible");
      suggestionsEl.innerHTML = "";
      return;
    }
    const matches = ALL_TEAMS.filter(t => t.includes(query));
    if (!matches.length) {
      suggestionsEl.innerHTML = '<div class="team-suggestion-item no-match">No matching team</div>';
      suggestionsEl.classList.add("visible");
      return;
    }
    suggestionsEl.innerHTML = matches.map(team => {
      const idx = team.indexOf(query);
      const highlighted = team.slice(0, idx)
        + '<span class="match">' + team.slice(idx, idx + query.length) + '</span>'
        + team.slice(idx + query.length);
      return `<div class="team-suggestion-item" data-team="${team}">${highlighted}</div>`;
    }).join("");
    suggestionsEl.classList.add("visible");
  });

  suggestionsEl.addEventListener("click", (e) => {
    const item = e.target.closest(".team-suggestion-item[data-team]");
    if (item) selectTeam(item.dataset.team);
  });

  // Real, same real behavior as the mockup's reference implementation: hide the dropdown on an
  // outside click without breaking the click-to-select handler above (this listener runs after
  // the one on suggestionsEl since it's attached second, so a real click on a suggestion item
  // still lands there first).
  document.addEventListener("click", (e) => {
    if (!e.target.closest(".team-filter-wrap")) {
      suggestionsEl.classList.remove("visible");
    }
  });
}

function selectTeam(team) {
  inputEl.value = "";
  suggestionsEl.classList.remove("visible");
  suggestionsEl.innerHTML = "";
  state.teamFilter = team;
  chipNameEl.textContent = team;
  chipEl.classList.add("visible");
  renderCurrentView();
}

export function clearTeamFilter() {
  state.teamFilter = null;
  chipEl.classList.remove("visible");
  inputEl.value = "";
  renderCurrentView();
}
