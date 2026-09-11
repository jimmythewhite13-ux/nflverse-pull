// Real, three-view rendering -- Games (per-game ticker list), Cheat Sheet (dense summary
// table), Teams (real 32-team grid). All three share the same real, currently-loaded week's
// games and the same real team-filter input.
import { state } from "./state.js";
import { statusPillClass, fmtKickoff } from "./format.js";
import { ALL_TEAMS } from "./teams.js";
import { renderHistoricalView } from "./historical.js";
export { ALL_TEAMS, FULL_TEAM_NAME } from "./teams.js";

export function gameRowHtml(g) {
  return `
    <div class="game-row" onclick="openDetail('${g.game_id}')">
      <div>
        <div class="teams">${g.away_team} @ ${g.home_team}</div>
        <div class="meta">${fmtKickoff(g.kickoff_time)}</div>
      </div>
      <div class="badges">
        <span class="${statusPillClass(g.status)}">${g.status.replace(/_/g, " ")}</span>
        ${g.has_major_shift ? '<span class="shift-badge">&#9650; Line moved</span>' : ""}
      </div>
    </div>
  `;
}

// Real, additive second top-level view -- not a replacement for the per-game list. Same real
// games/data, denser one-glance layout. Deliberately no populated prediction/edge column yet
// (no real predictions exist for any 2026 game) -- the real structure (columns, sort-readiness)
// is built now so it needs no further work once Week 4's real predictions start populating it.
export function cheatsheetHtml(games) {
  if (!games.length) return '<div class="empty">No real games scheduled for this week yet.</div>';
  const rows = games.map(g => `
    <tr onclick="openDetail('${g.game_id}')">
      <td>${g.away_team} @ ${g.home_team}</td>
      <td>${fmtKickoff(g.kickoff_time)}</td>
      <td><span class="${statusPillClass(g.status)}">${g.status.replace(/_/g, " ")}</span></td>
      <td>${g.has_major_shift ? '<span class="shift-badge">&#9650; moved</span>' : "--"}</td>
    </tr>
  `).join("");
  return `
    <table class="cheatsheet">
      <thead><tr><th>Matchup</th><th>Kickoff</th><th>Status</th><th>Market</th></tr></thead>
      <tbody>${rows}</tbody>
    </table>
  `;
}

export function teamsGridHtml(filterTerm) {
  const teams = filterTerm ? ALL_TEAMS.filter(t => t.includes(filterTerm)) : ALL_TEAMS;
  if (!teams.length) return '<div class="empty">No real team matches that filter.</div>';
  return `<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:6px">` +
    teams.map(t => `<div class="game-row" style="justify-content:center" onclick="openTeamDetail('${t}')"><span class="teams">${t}</span></div>`).join("") +
    `</div>`;
}

export function renderCurrentView() {
  // Real, deliberate change (consolidated_outstanding_queue.md item 3): driven by the selected
  // team from the ported autocomplete filter (team-filter.js), not raw live input text -- the
  // reference implementation only ever filters once a real suggestion is clicked.
  const filterTerm = state.teamFilter || "";
  const filtered = filterTerm
    ? state.loadedGames.filter(g => g.home_team.includes(filterTerm) || g.away_team.includes(filterTerm))
    : state.loadedGames;
  const gamesEl = document.getElementById("games");
  const sheetEl = document.getElementById("cheatsheet-view");
  const teamsEl = document.getElementById("teams-view");
  const histEl = document.getElementById("historical-view");
  gamesEl.style.display = state.activeView === "games" ? "block" : "none";
  sheetEl.style.display = state.activeView === "cheatsheet" ? "block" : "none";
  teamsEl.style.display = state.activeView === "teams" ? "block" : "none";
  histEl.style.display = state.activeView === "historical" ? "block" : "none";
  if (state.activeView === "games") {
    gamesEl.innerHTML = filtered.length
      ? filtered.map(gameRowHtml).join("")
      : '<div class="empty">No real games match that filter.</div>';
  } else if (state.activeView === "teams") {
    teamsEl.innerHTML = teamsGridHtml(filterTerm);
  } else if (state.activeView === "historical") {
    renderHistoricalView();  // real, async -- own real fetch/cache, see historical.js
  } else {
    sheetEl.innerHTML = cheatsheetHtml(filtered);
  }
}

export function switchView(view) {
  state.activeView = view;
  document.getElementById("tab-games").classList.toggle("active", view === "games");
  document.getElementById("tab-cheatsheet").classList.toggle("active", view === "cheatsheet");
  document.getElementById("tab-teams").classList.toggle("active", view === "teams");
  document.getElementById("tab-historical").classList.toggle("active", view === "historical");
  renderCurrentView();
}
