// Real, shared API client -- every real backend call lives here, one place to update the real
// API contract later, rather than fetch() calls scattered across feature modules.
const API = "";  // real, live API is same-origin (this page is served by the FastAPI service)

async function realFetch(path) {
  const res = await fetch(`${API}${path}`);
  if (!res.ok) throw new Error(`Real API returned HTTP ${res.status}`);
  return res.json();
}

export const api = {
  getModelVersions: () => realFetch("/sports/NFL/model-versions"),
  getCurrentWeek: () => realFetch("/sports/NFL/current-week"),
  getGames: (week) => realFetch(`/sports/NFL/games?week=${week}`),
  getGame: (gameId) => realFetch(`/sports/NFL/games/${encodeURIComponent(gameId)}`),
  getTeam: (team) => realFetch(`/sports/NFL/teams/${encodeURIComponent(team)}`),
};
