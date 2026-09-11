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
  if (m.market_type === "moneyline") return m.odds != null ? m.odds : "--";
  const line = m.line_value != null ? (Number(m.line_value) > 0 ? `+${m.line_value}` : m.line_value) : "--";
  const odds = m.odds != null ? ` (${Number(m.odds) > 0 ? "+" : ""}${m.odds})` : "";
  return `${line}${odds}`;
}
