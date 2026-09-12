// Real entry point -- wires up the page's existing inline onclick="..." handlers (unchanged
// from before the refactor, to minimize real behavioral risk) by exposing the needed
// functions on window, then boots the real initial data load.
import { api } from "./api.js";
import { switchView } from "./views.js";
import { openDetail, openTeamDetail, closeDetail, showOddsTab } from "./detail.js";
import { toggleWeekDropdown, selectWeek, loadCurrentWeek, loadGames } from "./week-nav.js";
import { initTeamFilter, clearTeamFilter } from "./team-filter.js";
import { toggleHistorical } from "./historical.js";

Object.assign(window, {
  switchView, openDetail, openTeamDetail, closeDetail, showOddsTab,
  toggleWeekDropdown, selectWeek, clearTeamFilter, toggleHistorical,
});

async function loadModelBanner() {
  try {
    const versions = await api.getModelVersions();
    const prod = versions.find(v => v.status === "PRODUCTION");
    document.getElementById("model-banner").innerHTML = prod
      ? `Live model: <b>${prod.version_name}</b> (PRODUCTION)`
      : `No model currently marked PRODUCTION -- real predictions are not yet being served live.`;
  } catch (e) {
    document.getElementById("model-banner").textContent = "Real model-version check failed.";
  }
}

document.addEventListener("click", (e) => {
  const nav = document.querySelector(".week-nav");
  if (nav && !nav.contains(e.target)) {
    document.getElementById("week-dropdown").classList.remove("open");
  }
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(() => {});
}

initTeamFilter();
loadModelBanner();
loadCurrentWeek().then(loadGames);
