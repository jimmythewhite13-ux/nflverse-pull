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
        // Real, same one-line structure as market-signals.js's .line-row-main -- player props
        // never carry a movement disclaimer, so there's no second line here.
        return `
          <div class="line-row ${cls}">
            <div class="line-row-main">
              ${bookNameHtml(p.sportsbook)}
              <span class="line-row-odds">${fmtPropValue(p)}</span>
            </div>
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

// Real, team-first Props nav (restructure_dropdown_navigation.md Part A): splits the same real
// captured props by the two real teams in this game (via the API's own best-effort team
// resolution -- see main.py's `_resolve_player_team`), each team collapsible, away team first
// (matches "Away @ Home" reading order used everywhere else in this app). A player prop the API
// couldn't confidently resolve to either team (`team` is null -- never guessed) gets its own
// honest "Team unclear" group rather than being silently dropped or misassigned.
export function renderPlayerPropsByTeam(playerProps, awayAbbr, homeAbbr, awayName, homeName) {
  if (!playerProps.length) {
    return '<div class="empty">No real player-prop lines captured yet.</div>';
  }
  const byTeam = { [awayAbbr]: [], [homeAbbr]: [], unresolved: [] };
  playerProps.forEach(p => {
    const key = p.team === awayAbbr ? awayAbbr : p.team === homeAbbr ? homeAbbr : "unresolved";
    byTeam[key].push(p);
  });
  const teamGroup = (label, rows, open) => rows.length
    ? `<details class="region-group"${open ? " open" : ""}>
         <summary>${label} <span class="region-count">${rows.length} lines</span></summary>
         ${renderPlayerProps(rows)}
       </details>`
    : "";
  const unresolved = byTeam.unresolved;
  const unresolvedHtml = unresolved.length
    ? `<details class="region-group">
         <summary>Team unclear <span class="region-count">${unresolved.length} lines</span></summary>
         <div class="not-available-note" style="margin-bottom:6px">Couldn't confidently match these players to either real roster (e.g. a name variant) -- shown here rather than guessed.</div>
         ${renderPlayerProps(unresolved)}
       </details>`
    : "";
  return teamGroup(awayName, byTeam[awayAbbr], true)
    + teamGroup(homeName, byTeam[homeAbbr], true)
    + unresolvedHtml;
}
