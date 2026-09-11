// Real, purely market-observational player-prop rendering -- same real discipline as
// market-signals.js (factual "best real price available," never a recommendation), just grouped
// one level deeper (by stat, then by player) since a prop line is meaningless without knowing
// who it's for. Real, deliberate scope note shown at the bottom: props are currently captured
// US-only (game lines above stay all-region) -- a real, explicit cost tradeoff, not an oversight.
import { bookNameHtml } from "./format.js";

function fmtPropValue(p) {
  if (p.market_key === "player_anytime_td") {
    return p.over_odds != null ? `Yes ${Number(p.over_odds) > 0 ? "+" : ""}${p.over_odds}` : "--";
  }
  const line = p.line_value != null ? p.line_value : "--";
  const over = p.over_odds != null ? `O ${Number(p.over_odds) > 0 ? "+" : ""}${p.over_odds}` : "";
  const under = p.under_odds != null ? `U ${Number(p.under_odds) > 0 ? "+" : ""}${p.under_odds}` : "";
  const odds = [over, under].filter(Boolean).join(" / ");
  return odds ? `${line} (${odds})` : `${line}`;
}

export function renderPlayerProps(playerProps) {
  if (!playerProps.length) {
    return '<div class="empty">No real player-prop lines captured yet.</div>';
  }
  const groups = {};
  playerProps.forEach(p => (groups[p.market_label] = groups[p.market_label] || []).push(p));

  const byPlayer = label => {
    const players = {};
    groups[label].forEach(p => (players[p.player_name] = players[p.player_name] || []).push(p));
    return Object.keys(players).sort().map(player => {
      const rows = players[player].map(p => {
        const cls = p.best_value ? "best" : p.worst_value ? "worst" : "";
        return `
          <div class="line-row ${cls}">
            ${bookNameHtml(p.sportsbook)}
            <div class="value"><span>${fmtPropValue(p)}</span></div>
          </div>
        `;
      }).join("");
      return `<div class="prop-player"><div class="prop-player-name">${player}</div>${rows}</div>`;
    }).join("");
  };

  const html = Object.keys(groups).sort().map(label =>
    `<div class="market-group"><h4>${label}</h4>${byPlayer(label)}</div>`
  ).join("");

  return `${html}<div class="not-available-note" style="margin-top:8px">Player props are currently captured from US sportsbooks only (game lines above cover all regions) -- a real, explicit cost tradeoff, not every book.</div>`;
}
