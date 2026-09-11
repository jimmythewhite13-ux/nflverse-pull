// Real week navigation + real week-level caveat rendering.
import { state } from "./state.js";
import { api } from "./api.js";
import { renderCurrentView } from "./views.js";
import { computeWeekCaveat } from "./week-caveat.js";

export function buildWeekDropdown() {
  const dd = document.getElementById("week-dropdown");
  const weeks = Array.from({ length: 18 }, (_, i) => i + 1);
  dd.innerHTML = weeks.map(w => `
    <button class="${w === state.viewingWeek ? 'current' : ''}" onclick="selectWeek(${w})">
      Week ${w}${w === state.currentWeek ? " (current)" : ""}
    </button>
  `).join("");
}

export function toggleWeekDropdown() {
  document.getElementById("week-dropdown").classList.toggle("open");
}

export function selectWeek(w) {
  state.viewingWeek = w;
  document.getElementById("week-dropdown").classList.remove("open");
  document.getElementById("week-number").textContent = w;
  buildWeekDropdown();
  loadGames();
}

export async function loadCurrentWeek() {
  try {
    const data = await api.getCurrentWeek();
    state.currentWeek = data.week;
    state.viewingWeek = data.week;
    document.getElementById("week-number").textContent = state.viewingWeek;
    buildWeekDropdown();
  } catch (e) {
    document.getElementById("week-number").textContent = "?";
    console.error("Real error loading current week:", e.message);
  }
}

function renderWeekCaveat() {
  const el = document.getElementById("week-caveat");
  const text = computeWeekCaveat(state.loadedGames, state.viewingWeek);
  if (text) {
    el.textContent = text;
    el.style.display = "block";
  } else {
    el.style.display = "none";
  }
}

export async function loadGames() {
  const loading = document.getElementById("loading");
  loading.style.display = "block";
  loading.textContent = "Loading real games...";
  document.getElementById("games").innerHTML = "";
  document.getElementById("cheatsheet-view").innerHTML = "";
  try {
    state.loadedGames = await api.getGames(state.viewingWeek);
    loading.style.display = "none";
    renderWeekCaveat();
    renderCurrentView();
  } catch (e) {
    loading.textContent = `Real error loading games: ${e.message}`;
  }
}
