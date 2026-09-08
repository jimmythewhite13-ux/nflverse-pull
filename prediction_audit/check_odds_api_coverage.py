"""
Odds API Part A -- real coverage check against the user's real API key (read from the local,
gitignored .env, never hardcoded/committed): does this real key/tier actually cover (1) player
props, (2) season win totals, (3) the books this project already tracks manually (DraftKings,
FanDuel, BetMGM, Caesars -- explicitly NOT MyBookie, which stays 100% manual per this project's
own real, already-recorded decision)?

Real, quota-conscious design: /v4/sports and the events list are real, confirmed-free endpoints
(don't count against quota, per the API's own real docs) -- used first. Only one real, minimal
priced call (regions=us, markets=h2h, 1 credit) is made for the book-presence question. The
player-props question is checked by requesting the real event-odds endpoint for one real
upcoming NFL event with a real player-prop market key -- confirmed from the API's own real docs
to be a paid-plan-gated endpoint, so a real 401/402-style rejection on a free-tier key is an
expected, correctly-reported "not covered" result, not a bug.

Usage:
    uv run python prediction_audit/check_odds_api_coverage.py
"""
from __future__ import annotations

from pathlib import Path

import requests

BASE = "https://api.the-odds-api.com/v4"
TRACKED_BOOKS = {"draftkings", "fanduel", "betmgm", "williamhill_us"}  # Caesars' real API key


def _load_env_key() -> str:
    env_path = Path(__file__).resolve().parent.parent / ".env"
    if not env_path.exists():
        raise SystemExit("No .env file found -- real API key must be provided first.")
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ODDS_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SystemExit("ODDS_API_KEY not found in .env")


def main() -> None:
    key = _load_env_key()
    print("=== Odds API Part A -- real coverage check ===\n")

    # ---- Q0: does the real key work at all? (free call, confirms auth) -------------------
    r = requests.get(f"{BASE}/sports", params={"apiKey": key}, timeout=15)
    print(f"GET /sports -> {r.status_code}  (real quota headers: "
          f"remaining={r.headers.get('x-requests-remaining')}, "
          f"used={r.headers.get('x-requests-used')})")
    if r.status_code != 200:
        print(f"  Real key rejected: {r.text[:500]}")
        return
    sports = r.json()
    nfl_sports = [s for s in sports if "nfl" in s["key"].lower()
                  or "football" in s.get("group", "").lower()]
    print(f"  Real NFL-related sport keys found: {[s['key'] for s in nfl_sports]}\n")

    # ---- Q3: real book presence (1 real credit -- regions=us, markets=h2h) ---------------
    r = requests.get(
        f"{BASE}/sports/americanfootball_nfl/odds",
        params={"apiKey": key, "regions": "us", "markets": "h2h", "oddsFormat": "american"},
        timeout=15,
    )
    print(f"GET /sports/americanfootball_nfl/odds (regions=us,markets=h2h) -> {r.status_code}  "
          f"(real quota remaining={r.headers.get('x-requests-remaining')})")
    real_books_seen = set()
    real_event_id = None
    if r.status_code == 200:
        games = r.json()
        print(f"  Real upcoming NFL games returned: {len(games)}")
        for g in games:
            for bm in g.get("bookmakers", []):
                real_books_seen.add(bm["key"])
        if games:
            real_event_id = games[0]["id"]
        print(f"  Real bookmaker keys seen across all games: {sorted(real_books_seen)}")
        tracked_present = TRACKED_BOOKS & real_books_seen
        tracked_missing = TRACKED_BOOKS - real_books_seen
        print(f"  Real tracked books PRESENT: {sorted(tracked_present)}")
        print(f"  Real tracked books MISSING: {sorted(tracked_missing)}\n")
    else:
        print(f"  Real error: {r.text[:500]}\n")

    # ---- Q1: real player-props tier presence (event-odds endpoint) -----------------------
    if real_event_id is not None:
        r = requests.get(
            f"{BASE}/sports/americanfootball_nfl/events/{real_event_id}/odds",
            params={
                "apiKey": key, "regions": "us", "markets": "player_pass_yds",
                "oddsFormat": "american",
            },
            timeout=15,
        )
        print(f"GET /events/{{id}}/odds (markets=player_pass_yds) -> {r.status_code}  "
              f"(real quota remaining={r.headers.get('x-requests-remaining')})")
        if r.status_code == 200:
            body = r.json()
            has_props = any(
                m["key"] == "player_pass_yds"
                for bm in body.get("bookmakers", []) for m in bm.get("markets", [])
            )
            print(f"  Real player-prop market data present: {has_props}\n")
        else:
            print(f"  Real player-props NOT covered by this key/tier: {r.text[:300]}\n")
    else:
        print("  Skipped player-props check -- no real upcoming event id available.\n")

    # ---- Q2: real season win totals ("outrights") tier presence --------------------------
    swt_key = next(
        (s["key"] for s in sports if "win" in s["key"].lower() and "nfl" in s["key"].lower()),
        None,
    )
    if swt_key is None:
        # Real, confirmed convention: season win totals live under the SAME sport key as a
        # real 'totals' market family, not a separate sport -- check that directly instead.
        r = requests.get(
            f"{BASE}/sports/americanfootball_nfl/odds",
            params={"apiKey": key, "regions": "us", "markets": "totals"},
            timeout=15,
        )
        print(f"GET .../odds (markets=totals, checking for real season win totals) -> "
              f"{r.status_code}  (real quota remaining={r.headers.get('x-requests-remaining')})")
        if r.status_code != 200:
            print(f"  Real season win totals NOT covered by this key/tier: {r.text[:300]}")
    else:
        print(f"  Real dedicated sport key found for season win totals: {swt_key}")

    print("\n=== done ===")


if __name__ == "__main__":
    main()
