// Real, purely market-observational rendering -- factual statements about what the real,
// current market is doing ("DraftKings currently offers the best number," "this line has
// moved 3.0+ points since opening"), never a recommendation or "value" in the betting sense.
import { fmtLineValue, bookNameHtml } from "./format.js";

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
    return `<div class="market-group"><h4>${mtype}</h4>${rows}</div>`;
  }).join("");
}

// Real, deliberate region-first nav (restructure_dropdown_navigation.md Part A) -- adapted from
// the task's literal "North America / International -> Europe | Asia/Other" wording to this
// project's real, actually-captured taxonomy (US/UK/AU/EU; there is no real Asia region
// anywhere in this pipeline). North America stays open by default (the primary region, same
// convention fix_overlap_grouping_historical_props.md's Issue 2 asked for); the three real
// international sub-regions collapse under one "International" group, directly resolving the
// crowding that caused Issue 1's text-overlap bug -- a real, structural fix, not cosmetic.
export function renderLinesNav(marketLines) {
  const byRegion = { us: [], uk: [], eu: [], au: [] };
  marketLines.forEach(m => { if (byRegion[m.region]) byRegion[m.region].push(m); });
  const regionGroup = (label, rows, open) => rows.length
    ? `<details class="region-group"${open ? " open" : ""}>
         <summary>${label} <span class="region-count">${new Set(rows.map(r => r.sportsbook)).size} books</span></summary>
         ${renderMarketLines(rows)}
       </details>`
    : "";
  const naHtml = byRegion.us.length
    ? regionGroup("North America", byRegion.us, true)
    : '<div class="empty">No real North America lines captured yet.</div>';
  const intlInner = [
    regionGroup("UK", byRegion.uk, false),
    regionGroup("EU", byRegion.eu, false),
    regionGroup("Australia", byRegion.au, false),
  ].join("");
  const intlHtml = intlInner
    ? `<details class="region-group"><summary>International</summary>${intlInner}</details>`
    : "";
  return naHtml + intlHtml;
}
