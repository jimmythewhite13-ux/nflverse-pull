// Real, purely market-observational rendering -- factual statements about what the real,
// current market is doing ("DraftKings currently offers the best number," "this line has
// moved 3.0+ points since opening"), never a recommendation or "value" in the betting sense.
import { fmtLineValue } from "./format.js";

export function renderMarketLines(marketLines) {
  if (!marketLines.length) return '<div class="empty">No real market lines captured yet.</div>';
  const groups = {};
  marketLines.forEach(m => (groups[m.market_type] = groups[m.market_type] || []).push(m));
  const order = ["spread", "total", "moneyline"];
  return Object.keys(groups).sort((a, b) => order.indexOf(a) - order.indexOf(b)).map(mtype => {
    const rows = groups[mtype].map(m => {
      const cls = m.best_value ? "best" : m.worst_value ? "worst" : "";
      let movementHtml = "";
      if (m.movement_status === "MEASURED" && m.line_movement !== undefined) {
        const delta = Number(m.line_movement);
        const isMajor = m.major_shift;
        movementHtml = delta === 0
          ? '<span class="movement">no real movement since opening</span>'
          : `<span class="movement${isMajor ? " major" : ""}">${isMajor ? "&#9650; " : ""}opened ${m.opening_line_value} &rarr; ${Math.abs(delta).toFixed(1)}pt ${delta > 0 ? "up" : "down"}</span>`;
      } else if (m.movement_status === "MEASURED" && m.odds_movement !== undefined) {
        const oddsDelta = Number(m.odds_movement);
        movementHtml = oddsDelta === 0
          ? '<span class="movement">no real odds movement since opening</span>'
          : `<span class="movement">opened ${m.opening_odds} &rarr; moved ${Math.abs(oddsDelta)} ${oddsDelta > 0 ? "better" : "worse"}</span>`;
      } else if (m.movement_status === "INSUFFICIENT_DATA") {
        movementHtml = '<span class="movement">only one real capture so far -- insufficient data for movement</span>';
      } else if (m.movement_status === "NO_REAL_PREGAME_DATA") {
        movementHtml = '<span class="movement">no real pregame data captured</span>';
      }
      return `
        <div class="line-row ${cls}">
          <span class="book">${m.sportsbook.replace(/_/g, " ")}</span>
          <div class="value">${movementHtml}<span>${fmtLineValue(m)}</span></div>
        </div>
      `;
    }).join("");
    return `<div class="market-group"><h4>${mtype}</h4>${rows}</div>`;
  }).join("");
}
