// Real Historical/backtest tab (consolidated_outstanding_queue.md item 2) -- real,
// already-completed games from the model's validated 2025 (Phase 1, 224 games) and 2024
// (Phase 8, 220 games) reconstructions. Deliberately kept structurally and visually separate
// from the live Games view -- its own tab, a persistent disclaimer, and a "RECONSTRUCTED" badge
// in a real, third color (teal, distinct from both the live signal-yellow and the
// not-yet-available slate) -- so a viewer can never mistake a historical reconstruction for a
// current, live prediction. Deliberately shows EVERY real game from these two model_versions,
// not a curated subset -- the surest way to guarantee a genuinely representative sample (real
// hits AND real misses) is to never filter any of them out.
import { api } from "./api.js";
import { state } from "./state.js";
import { FULL_TEAM_NAME } from "./teams.js";

let cachedGames = null;
let cachedSummary = null;
let cachedPropSummary = null;

// Real, human-readable labels for player_prop_backtest.py's own real stat_type strings.
const _STAT_LABELS = {
  passing_yards: "Passing Yards", interceptions: "INTs Thrown", rushing_yards: "Rushing Yards",
  receiving_yards: "Receiving Yards", receptions: "Receptions",
};

// Real aggregate prop-backtest MAE per stat type (historical_player_prop_backtest.md) -- shown
// alongside the game-level headline stats above, same "real distribution before any one
// example" purpose. Renders nothing (not an empty error) when the backtest hasn't been run yet
// on this checkout -- an honest absence, not a broken feature.
function propSummaryHtml(propSummary) {
  if (!propSummary || !propSummary.length) return "";
  const tiles = propSummary.map(s => `
    <div class="summary-stat">
      <span class="summary-stat-label">${_STAT_LABELS[s.stat_type] || s.stat_type}</span>
      <span class="summary-stat-value">${s.mae}</span>
    </div>
  `).join("");
  return `
    <div class="summary-card">
      <div class="summary-season">Player Prop Backtest <span class="summary-n">(real MAE, walk-forward-safe replay of Player Prop Projections' own methodology)</span></div>
      <div class="summary-stats" style="grid-template-columns:repeat(${propSummary.length},1fr)">${tiles}</div>
    </div>
  `;
}

// Real per-game player-prop comparison rows, shown in the drill-down when this game has any
// real backtest rows.
function propRowsHtml(props) {
  if (!props || !props.length) return "";
  const byPlayer = {};
  props.forEach(p => (byPlayer[`${p.player_name} (${p.team})`] = byPlayer[`${p.player_name} (${p.team})`] || []).push(p));
  const rows = Object.entries(byPlayer).map(([label, stats]) => `
    <div class="readout-row" style="flex-direction:column;align-items:flex-start;gap:4px">
      <span class="readout-label" style="font-weight:600">${label}</span>
      ${stats.map(s => `
        <div style="display:flex;justify-content:space-between;width:100%;font-size:12.5px">
          <span class="readout-label">${_STAT_LABELS[s.stat_type] || s.stat_type}</span>
          <span>Proj ${Number(s.projected_value).toFixed(1)} &middot; Real ${Number(s.actual_value).toFixed(1)} &middot; off by ${s.error}</span>
        </div>
      `).join("")}
    </div>
  `).join("");
  return `<div class="readout-row" style="border-top:1px solid var(--border);padding-top:10px;margin-top:6px"></div>${rows}`;
}

// Real aggregate headline stats (check_total_accuracy_and_headline_stats.md) -- MAE for spread
// AND total shown separately (never blended into one number), winner accuracy, and Brier, per
// real season, so any one example game below can be read against the real overall distribution
// rather than in isolation.
function summaryHtml(summary) {
  if (!summary || !summary.length) return "";
  const tiles = summary.map(s => `
    <div class="summary-card">
      <div class="summary-season">${s.season} Season <span class="summary-n">(${s.n_games} real games)</span></div>
      <div class="summary-stats">
        <div class="summary-stat"><span class="summary-stat-label">Margin MAE</span><span class="summary-stat-value">${s.margin_mae}</span></div>
        <div class="summary-stat"><span class="summary-stat-label">Total MAE</span><span class="summary-stat-value">${s.total_mae}</span></div>
        <div class="summary-stat"><span class="summary-stat-label">Winner Acc.</span><span class="summary-stat-value">${s.winner_accuracy}%</span></div>
        <div class="summary-stat"><span class="summary-stat-label">Brier</span><span class="summary-stat-value">${s.brier}</span></div>
      </div>
    </div>
  `).join("");
  return `<div class="summary-cards">${tiles}</div>`;
}

function nickname(fullTeamName) {
  return fullTeamName.split(" ").pop();
}

function accuracyTagHtml(g) {
  return g.winner_correct
    ? `<span class="accuracy-tag correct">Winner correct &middot; Margin off by `
      + `${g.margin_error} pt${g.margin_error === 1 ? "" : "s"}</span>`
    : '<span class="accuracy-tag miss">Winner missed</span>';
}

function rowHtml(g, idx) {
  const modelSide = g.projected_margin > 0 ? g.home_team : g.away_team;
  const modelMargin = Math.abs(g.projected_margin).toFixed(1);
  const favoredHome = g.home_win_probability >= 0.5;
  const winProbSide = favoredHome ? g.home_team : g.away_team;
  const winProbPct = (favoredHome ? g.home_win_probability : 1 - g.home_win_probability) * 100;
  // Real total (O/U) comparison (fix_overlap_grouping_historical_props.md Issue 3) -- same real
  // projected_total the model already writes for every run, alongside the real actual combined
  // score. Purely observational (over/under vs. the real, actual number), same "no
  // recommendation" discipline as the game-line movement displays.
  // Real, deliberate Number() coercion -- Postgres NUMERIC columns arrive over the wire as
  // real JSON strings (confirmed live: a direct .toFixed() call threw "not a function"), unlike
  // projected_margin above which only ever reaches .toFixed() after Math.abs() already coerced
  // it to a real number.
  const projectedTotal = g.projected_total != null ? Number(g.projected_total) : null;
  const actualTotal = g.actual_total;
  const totalHtml = projectedTotal != null ? `
          <div class="readout-row">
            <span class="readout-label">Model total (at kickoff)</span>
            <span class="readout-value">${projectedTotal.toFixed(1)}</span>
          </div>
          <div class="result-compare">
            <div class="result-compare-col">
              <div class="result-compare-label">Model Predicted Total</div>
              <div class="result-compare-value">${projectedTotal.toFixed(1)}</div>
            </div>
            <div class="result-compare-col">
              <div class="result-compare-label">Real Actual Total</div>
              <div class="result-compare-value">${actualTotal}</div>
            </div>
          </div>
          <div style="text-align:center">
            <span class="readout-label">Off by ${g.total_error} pt${g.total_error === 1 ? "" : "s"}</span>
          </div>` : "";
  return `
    <div class="row-wrapper">
      <div class="game-row" onclick="toggleHistorical(this, ${idx})">
        <div class="matchup">
          <div class="teams">${nickname(g.away_team)} @ ${nickname(g.home_team)}</div>
          <div class="kickoff">${g.season} Season &middot; Week ${g.week}</div>
        </div>
        <div style="display:flex;align-items:center">
          <span class="historical-badge">RECONSTRUCTED</span>
          <span class="chevron">&rsaquo;</span>
        </div>
      </div>
      <div class="drilldown" id="hist-drilldown-${idx}">
        <div class="drilldown-inner">
          <div class="readout-row">
            <span class="readout-label">Model spread (at kickoff)</span>
            <span class="readout-value">${nickname(modelSide)} &minus;${modelMargin}</span>
          </div>
          <div class="readout-row">
            <span class="readout-label">Model win probability</span>
            <span class="readout-value">${nickname(winProbSide)} ${winProbPct.toFixed(0)}%</span>
          </div>
          <div class="result-compare">
            <div class="result-compare-col">
              <div class="result-compare-label">Model Predicted</div>
              <div class="result-compare-value">${nickname(modelSide)} &minus;${modelMargin}</div>
            </div>
            <div class="result-compare-col">
              <div class="result-compare-label">Real Final Score</div>
              <div class="result-compare-value">${nickname(g.away_team)} ${g.away_final_score}&ndash;${g.home_final_score} ${nickname(g.home_team)}</div>
            </div>
          </div>
          <div style="text-align:center">${accuracyTagHtml(g)}</div>
          ${totalHtml}
          ${propRowsHtml(g.player_props)}
        </div>
      </div>
    </div>
  `;
}

function renderRows(games) {
  const filterTeam = state.teamFilter ? FULL_TEAM_NAME[state.teamFilter] : null;
  const filtered = filterTeam
    ? games.filter(g => g.home_team === filterTeam || g.away_team === filterTeam)
    : games;
  const container = document.getElementById("historical-games");
  container.innerHTML = filtered.length
    ? filtered.map(rowHtml).join("")
    : '<div class="empty">No real historical games match that filter.</div>';
}

export async function renderHistoricalView() {
  const container = document.getElementById("historical-games");
  const summaryContainer = document.getElementById("historical-summary");
  if (!cachedGames) {
    container.innerHTML = "Loading real historical data...";
    try {
      const data = await api.getHistorical();
      cachedGames = data.games;
      cachedSummary = data.summary;
      cachedPropSummary = data.prop_summary;
    } catch (e) {
      container.innerHTML = `<div class="empty">Real error loading historical data: ${e.message}</div>`;
      return;
    }
  }
  summaryContainer.innerHTML = summaryHtml(cachedSummary) + propSummaryHtml(cachedPropSummary);
  renderRows(cachedGames);
}

export function toggleHistorical(rowEl, idx) {
  const drop = document.getElementById(`hist-drilldown-${idx}`);
  const isOpen = drop.classList.contains("open");
  document.querySelectorAll("#historical-view .drilldown.open").forEach(d => d.classList.remove("open"));
  document.querySelectorAll("#historical-view .game-row.expanded").forEach(r => r.classList.remove("expanded"));
  if (!isOpen) {
    drop.classList.add("open");
    rowEl.classList.add("expanded");
  }
}
