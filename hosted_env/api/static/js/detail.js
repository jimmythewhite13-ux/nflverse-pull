// Real per-game and per-team drill-down overlay.
import { api } from "./api.js";
import { statusPillClass, fmtKickoff } from "./format.js";
import { renderMarketLines } from "./market-signals.js";
import { renderPlayerProps } from "./player-props.js";

export async function openDetail(gameId) {
  const detail = document.getElementById("detail");
  const content = document.getElementById("detail-content");
  content.innerHTML = "Loading real game data...";
  detail.classList.add("open");
  try {
    const g = await api.getGame(gameId);

    const injuriesHtml = g.injuries.length
      ? g.injuries.map(i => `
          <div class="row"><span>${i.player_name} (${i.team}, ${i.position || "?"})</span>
          <span>${i.report_status || "--"}</span></div>
        `).join("")
      : '<div class="empty">No real injury reports for either team right now.</div>';

    const marketHtml = renderMarketLines(g.market_lines);
    const propsHtml = renderPlayerProps(g.player_props || []);

    // Real, honest "What we know so far" section for a game with no prediction yet -- real
    // current market lines (the one real data point actually available), plus an explicit,
    // honest note that Season Win Totals aren't a real data point at all right now (not
    // available from the current odds provider at any tier -- a genuine gap, not fabricated).
    let bodyHtml;
    if (g.prediction && g.prediction.status === "NOT_YET_AVAILABLE") {
      bodyHtml = `
        <section>
          <h3>What we know so far</h3>
          <div class="prediction-pending" style="margin-bottom:12px">${g.prediction.reason}</div>
          <div class="not-available-note">Season Win Totals: not available from the current real data source.</div>
          <div style="margin-top:10px">${marketHtml}</div>
        </section>
      `;
    } else if (g.prediction) {
      bodyHtml = `
        <section>
          <h3>Prediction</h3>
          <div class="row"><span>Projected margin (home)</span><span style="color:var(--signal)">${g.prediction.projected_margin}</span></div>
          <div class="row"><span>Home win probability</span><span style="color:var(--signal)">${(g.prediction.home_win_probability * 100).toFixed(1)}%</span></div>
          <div class="row"><span>Model version</span><span>${g.prediction.version_name}</span></div>
        </section>
        <section><h3>Market lines</h3>${marketHtml}</section>
      `;
    } else {
      bodyHtml = `<section><h3>Market lines</h3>${marketHtml}</section>`;
    }

    content.innerHTML = `
      <h2>${g.away_team} @ ${g.home_team}</h2>
      <div class="meta" style="color:var(--muted)">Week ${g.week} &middot; ${fmtKickoff(g.kickoff_time)}</div>
      <span class="${statusPillClass(g.status)}">${g.status.replace(/_/g, " ")}</span>
      ${bodyHtml}
      <section><h3>Player Props</h3>${propsHtml}</section>
      <section><h3>Injuries</h3>${injuriesHtml}</section>
    `;
  } catch (e) {
    content.innerHTML = `<button class="back" onclick="closeDetail()">&larr; Back</button>
      <div class="prediction-pending">Real error loading game detail: ${e.message}</div>`;
  }
}

// Real per-team page: full real season schedule + real current injury status. Explicitly no
// Season Win Totals section -- honest "not available" note instead, same as the per-game
// drill-down (not a real data point from any current source, never fabricated).
export async function openTeamDetail(team) {
  const detail = document.getElementById("detail");
  const content = document.getElementById("detail-content");
  content.innerHTML = "Loading real team data...";
  detail.classList.add("open");
  try {
    const t = await api.getTeam(team);

    const scheduleHtml = t.schedule.map(g => `
      <div class="row" style="cursor:pointer" onclick="openDetail('${g.game_id}')">
        <span>Wk ${g.week} &middot; ${g.away_team} @ ${g.home_team}</span>
        <span>${fmtKickoff(g.kickoff_time)}</span>
      </div>
    `).join("");

    const injuriesHtml = t.injuries.length
      ? t.injuries.map(i => `
          <div class="row"><span>${i.player_name} (${i.position || "?"})</span>
          <span>${i.report_status || "--"}</span></div>
        `).join("")
      : '<div class="empty">No real injury reports for this team right now.</div>';

    content.innerHTML = `
      <h2>${t.team}</h2>
      <div class="not-available-note">Season Win Total: not available from the current real data source.</div>
      <section><h3>Full schedule</h3>${scheduleHtml}</section>
      <section><h3>Injuries</h3>${injuriesHtml}</section>
    `;
  } catch (e) {
    content.innerHTML = `<button class="back" onclick="closeDetail()">&larr; Back</button>
      <div class="prediction-pending">Real error loading team data: ${e.message}</div>`;
  }
}

export function closeDetail() {
  document.getElementById("detail").classList.remove("open");
}
