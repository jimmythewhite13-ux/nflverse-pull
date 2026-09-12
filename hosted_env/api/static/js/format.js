// Real, shared formatting helpers -- used by every feature module that renders a game/line.
export function statusPillClass(status) {
  if (status === "READY" || status === "PREDICTED") return "status-pill ready";
  return "status-pill";
}

export function fmtKickoff(iso) {
  if (!iso) return "Kickoff TBD";
  const d = new Date(iso);
  return d.toLocaleString(undefined, { weekday: "short", month: "short", day: "numeric",
    hour: "numeric", minute: "2-digit" });
}

// Real, purely market-observational formatting -- factual statements about what the real,
// current market is doing, never a recommendation or "value" in the betting sense.
export function fmtLineValue(m) {
  if (m.market_type === "moneyline" || m.market_type === "moneyline_h1") return m.odds != null ? m.odds : "--";
  const line = m.line_value != null ? (Number(m.line_value) > 0 ? `+${m.line_value}` : m.line_value) : "--";
  const odds = m.odds != null ? ` (${Number(m.odds) > 0 ? "+" : ""}${m.odds})` : "";
  return `${line}${odds}`;
}

// Real, plain (NOT tracked/affiliate) homepage for each of this project's 22 approved real
// sportsbooks -- consolidated_outstanding_queue.md item 4: "the digital equivalent of manually
// going to check that book yourself," never a monetized link (that's a separate, later-date
// item explicitly requiring real legal review first). Every URL here is that book's own real,
// plain top-level site -- no referral/affiliate query params, no tracked redirect.
const _BOOK_URLS = {
  draftkings: "https://sportsbook.draftkings.com/",
  fanduel: "https://sportsbook.fanduel.com/",
  betmgm: "https://sports.betmgm.com/",
  williamhill_us: "https://www.caesars.com/sportsbook",   // real Odds API key for Caesars
  williamhill: "https://sports.williamhill.com/",
  ladbrokes_uk: "https://sports.ladbrokes.com/",
  coral: "https://sports.coral.co.uk/",
  paddypower: "https://www.paddypower.com/",
  betway: "https://sports.betway.com/",
  betvictor: "https://www.betvictor.com/",
  sportsbet: "https://www.sportsbet.com.au/",
  ladbrokes_au: "https://www.ladbrokes.com.au/",
  neds: "https://www.neds.com.au/",
  pointsbetau: "https://pointsbet.com.au/",
  betright: "https://www.betright.com.au/",
  tab: "https://www.tab.com.au/",
  unibet: "https://www.unibet.com.au/",
  betclic_fr: "https://www.betclic.fr/",
  pmu_fr: "https://www.pmu.fr/",
  tipico_de: "https://www.tipico.de/",
  unibet_nl: "https://www.unibet.nl/",
  unibet_se: "https://www.unibet.se/",
};

export function bookUrl(sportsbook) {
  return _BOOK_URLS[sportsbook] || null;
}

// Real, shared rendering for a sportsbook name -- a plain link to that book's own real site when
// one is known (rel="noopener noreferrer": real, no window.opener leak, no referrer sent), a
// plain span otherwise (never a broken link for a book missing from _BOOK_URLS).
export function bookNameHtml(sportsbook) {
  const label = sportsbook.replace(/_/g, " ");
  const url = bookUrl(sportsbook);
  return url
    ? `<a class="book" href="${url}" target="_blank" rel="noopener noreferrer">${label}</a>`
    : `<span class="book">${label}</span>`;
}
