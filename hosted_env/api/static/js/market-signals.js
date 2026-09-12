// Real, purely market-observational rendering -- factual statements about what the real,
// current market is doing ("DraftKings currently offers the best number," "this line has
// moved 3.0+ points since opening"), never a recommendation or "value" in the betting sense.
import { fmtLineValue, bookNameHtml } from "./format.js";

// Real, human-readable labels (restructure_dropdown_navigation.md Part B, explicit user
// go-ahead 2026-09-12) -- the raw market_type strings ('spread_h1' etc.) are what the DB/API
// use, this is purely display.
const _MARKET_TYPE_LABELS = {
  spread: "Spread", total: "Total", moneyline: "Moneyline",
  spread_h1: "1H Spread", total_h1: "1H Total", moneyline_h1: "1H Moneyline",
};
const _MARKET_TYPE_ORDER = ["spread", "total", "moneyline", "spread_h1", "total_h1", "moneyline_h1"];

export function renderMarketLines(marketLines) {
  if (!marketLines.length) return '<div class="empty">No real market lines captured yet.</div>';
  const groups = {};
  marketLines.forEach(m => (groups[m.market_type] = groups[m.market_type] || []).push(m));
  return Object.keys(groups)
    .sort((a, b) => _MARKET_TYPE_ORDER.indexOf(a) - _MARKET_TYPE_ORDER.indexOf(b))
    .map(mtype => {
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
      // Real, deliberate two-line structure (fix_overlap_grouping_historical_props.md Issue 1):
      // book name + odds share one row (always short, always fits); the movement/disclaimer
      // text -- which can be much longer, e.g. "only one real capture so far -- insufficient
      // data for movement" -- gets its own full-width line below instead of fighting the book
      // name and odds for the same horizontal space. Confirmed real bug: cramming all three
      // into one flex row visually overlapped the disclaimer text onto the book name once book
      // names became links (dotted underline) with real, longer international names.
      return `
        <div class="line-row ${cls}">
          <div class="line-row-main">
            ${bookNameHtml(m.sportsbook)}
            <span class="line-row-odds">${fmtLineValue(m)}</span>
          </div>
          ${movementHtml ? `<div class="line-row-movement">${movementHtml}</div>` : ""}
        </div>
      `;
    }).join("");
    return `<div class="market-group"><h4>${_MARKET_TYPE_LABELS[mtype] || mtype}</h4>${rows}</div>`;
  }).join("");
}

// Real, deliberate region-first nav (restructure_dropdown_navigation.md Part A) -- adapted from
// the task's literal "North America / International -> Europe | Asia/Other" wording to this
// project's real, actually-captured taxonomy (US/UK/AU/EU; there is no real Asia region
// anywhere in this pipeline). North America stays open by default (the primary region, same
// convention fix_overlap_grouping_historical_props.md's Issue 2 asked for); the three real
// international sub-regions collapse under one "International" group, directly resolving the
// crowding that caused Issue 1's text-overlap bug -- a real, structural fix, not cosmetic.
//
// Real, deliberate fix (2026-09-12, confirmed via a real user screenshot): a region with zero
// real rows for THIS specific game used to be omitted entirely -- international books ARE
// captured (confirmed live for other games), so a game whose most recent capture simply didn't
// carry international data yet looked like international coverage didn't exist at all, with no
// way to even check. Every region group now always renders -- honest "not captured yet" text
// inside an EMPTY group, same discipline as every other "no real data" message in this app,
// instead of silently disappearing.
export function renderLinesNav(marketLines) {
  const byRegion = { us: [], uk: [], eu: [], au: [] };
  marketLines.forEach(m => { if (byRegion[m.region]) byRegion[m.region].push(m); });
  const regionGroup = (label, rows, open) => {
    const count = new Set(rows.map(r => r.sportsbook)).size;
    const body = rows.length
      ? renderMarketLines(rows)
      : `<div class="empty">No real ${label} lines captured yet for this game.</div>`;
    return `<details class="region-group"${open ? " open" : ""}>
         <summary>${label} <span class="region-count">${count} book${count === 1 ? "" : "s"}</span></summary>
         ${body}
       </details>`;
  };
  const naHtml = regionGroup("North America", byRegion.us, true);
  const intlInner = [
    regionGroup("UK", byRegion.uk, false),
    regionGroup("EU", byRegion.eu, false),
    regionGroup("Australia", byRegion.au, false),
  ].join("");
  const intlHtml = `<details class="region-group"><summary>International</summary>${intlInner}</details>`;
  return naHtml + intlHtml;
}
