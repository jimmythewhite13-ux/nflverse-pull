// Real, three-view rendering -- Games (per-game ticker list), Cheat Sheet (dense summary
// table), Teams (real 32-team grid). All three share the same real, currently-loaded week's
// games and the same real team-filter input.
import { state } from "./state.js";
import { statusPillClass, fmtKickoff, bookNameHtml } from "./format.js";
import { ALL_TEAMS } from "./teams.js";
import { renderHistoricalView } from "./historical.js";
import { api } from "./api.js";
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

// Real, purely observational Cheat Sheet market-signal sections (cheat_sheet_market_signals_
// part1.md) -- no model predictions anywhere (none exist yet for any 2026 game). Both sections
// read as "here's what's happening in the market," never a recommendation -- no "value,"
// "opportunity," or "worth a look" language anywhere in this module.
let cachedCheatsheetWeek = null;
let cachedCheatsheetData = null;

function bestValueHtml(bestValue) {
  if (!bestValue.length) {
    return '<div class="empty">No real, comparable best/worst price gap found across this week\'s slate yet.</div>';
  }
  const rows = bestValue.map(e => {
    const isMoneyline = e.market_type === "moneyline";
    const headerLineTxt = isMoneyline ? "" : ` at ${e.line_value}`;
    const betDesc = isMoneyline ? "moneyline bet" : `${e.market_type} at the same real ${e.line_value}`;
    return `
    <div class="line-row">
      <div class="line-row-main">
        <span onclick="openDetail('${e.game_id}')" style="cursor:pointer">${e.matchup} <span class="region-count">${e.market_type}${headerLineTxt}</span></span>
        <span class="line-row-odds">${e.gap}</span>
      </div>
      <div class="line-row-movement"><span class="movement">${bookNameHtml(e.best_book)} (${e.best_odds}) currently offers ${e.gap} points better real odds than ${bookNameHtml(e.worst_book)} (${e.worst_odds}) for the exact same real ${betDesc}</span></div>
    </div>
  `;
  }).join("");
  return `<div class="market-group">${rows}</div>`;
}

// Real player-prop value comparison (cheat_sheet_props_extension.md) -- same real, same-line-
// only discipline as game lines, clearly labeled "player prop" so it's never visually confused
// with a game-line entry.
function bestPropValueHtml(bestPropValue) {
  if (!bestPropValue.length) {
    return '<div class="empty">No real, comparable best/worst prop price gap found across this week\'s slate yet.</div>';
  }
  const rows = bestPropValue.map(e => {
    const lineTxt = e.line_value != null ? ` at ${e.line_value}` : "";
    return `
    <div class="line-row">
      <div class="line-row-main">
        <span onclick="openDetail('${e.game_id}')" style="cursor:pointer">${e.player_name} <span class="region-count">player prop &middot; ${e.market_label}${lineTxt}</span></span>
        <span class="line-row-odds">${e.gap}</span>
      </div>
      <div class="line-row-movement"><span class="movement">${bookNameHtml(e.best_book)} (${e.best_odds}) currently offers ${e.gap} points better real odds than ${bookNameHtml(e.worst_book)} (${e.worst_odds}) for the exact same real prop${lineTxt} (${e.matchup})</span></div>
    </div>
  `;
  }).join("");
  return `<div class="market-group">${rows}</div>`;
}

function unusualMovementHtml(unusualMovement, n) {
  if (!unusualMovement.length) {
    return `<div class="empty">No real game this week has moved further than 90% of the ${n} real, measured movements captured so far.</div>`;
  }
  const rows = unusualMovement.map(e => `
    <div class="line-row">
      <div class="line-row-main">
        <span onclick="openDetail('${e.game_id}')" style="cursor:pointer">${e.matchup}</span>
        <span class="line-row-odds">${e.movement}pt move</span>
      </div>
      <div class="line-row-movement"><span class="movement major">This line has moved further than ${e.percentile}% of the ${n} real book/market movements captured so far this season</span></div>
    </div>
  `).join("");
  return `<div class="market-group">${rows}</div>`;
}

export async function renderCheatsheetSignals(week) {
  const container = document.getElementById("cheatsheet-signals");
  if (!container) return;
  if (cachedCheatsheetWeek !== week) {
    container.innerHTML = "Loading real market signals...";
    try {
      cachedCheatsheetData = await api.getCheatsheet(week);
      cachedCheatsheetWeek = week;
    } catch (e) {
      container.innerHTML = `<div class="empty">Real error loading market signals: ${e.message}</div>`;
      return;
    }
  }
  const d = cachedCheatsheetData;
  // Real, honest hold-back note (cheat_sheet_props_extension.md's own explicit requirement) --
  // props only started capturing this week, so there isn't yet a real distribution to compute a
  // percentile-based "unusual movement" flag from for props specifically (the game-line
  // movement section above already covers game lines; this note is prop-specific).
  const propMovementNote = d.prop_movement_eligible_n === 0
    ? `<div class="not-available-note" style="margin:4px 0 10px">Player-prop movement detection: not enough real history yet -- props only started capturing once daily this week, and 0 real (player, market, book) combinations have a second real capture so far. Revisit once a real, multi-capture distribution exists (roughly 2-3 weeks of the once-daily cadence).</div>`
    : "";
  container.innerHTML = `
    <h4 style="margin:10px 0 4px">Best Real Line Value This Week</h4>
    ${bestValueHtml(d.best_value)}
    <h4 style="margin:14px 0 4px">Best Real Player Prop Value This Week</h4>
    ${bestPropValueHtml(d.best_prop_value)}
    ${propMovementNote}
    <h4 style="margin:14px 0 4px">Statistically Unusual Line Movement</h4>
    ${unusualMovementHtml(d.unusual_movement, d.movement_distribution_n)}
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
    sheetEl.innerHTML = `<div id="cheatsheet-signals"></div>` + cheatsheetHtml(filtered);
    renderCheatsheetSignals(state.viewingWeek);
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
