"""
Real player-prop line capture -- sibling to market_lines.py, same real established patterns
(allow-list default-deny via APPROVED_BOOKMAKERS, real post-kickoff exclusion, real cadence
gating), but structurally different in one way market_lines.py isn't: the Odds API bills player
props via the PER-EVENT endpoint (`/v4/sports/{sport}/events/{event_id}/odds`), not the bulk
game-odds endpoint, and the real, measured cost scales with region count AND market count, per
event. Real, explicit scope decision (2026-09-11), after measuring real cost directly against
the live API before writing this file:
  - Region: US ONLY. Real, measured cost: 20 credits/event for these 5 markets across all 4
    regions (us,uk,eu,au) vs. 5 credits/event for US only -- a real, permanent 4x cost, and this
    account's real remaining quota (317 at last check) can't sustain even the cheapest realistic
    weekly cadence at all-region scope. Explicit user decision: US-only for props, while game
    lines (raw_market_captures) stay all-region (already working, already paid for).
  - Markets: 5 to start ("core 4 + QB interceptions" -- explicit user scope-down from an
    initially much larger requested list). MARKET_KEYS below is the one place to extend later.
  - Cadence: real, deliberately SIMPLIFIED for the beta period (2026-09-11 revision -- explicit
    user request: "for now during the beta process let's do a once a day trigger", superseding
    the originally-specified "twice daily + hour-before-kickoff" cadence). The workflow's own
    cron now fires once daily (see player_props_capture.yml), and `_should_capture_event` below
    is a simple per-event safety net (skip if already captured for this game in the last ~20h),
    not the finer-grained pre-kickoff-hour logic market_lines.py's own cadence gate uses --
    revisit adding a dedicated closing-line (hour-before-kickoff) capture once beta is
    graduated, per the same user request.

Real game_id resolution and CLV/post-kickoff exclusion: identical real logic to market_lines.py
(reused directly, not reimplemented) -- see that module's own comments for the full rationale.

Usage:
    uv run python -m prediction_audit.ingestion.player_props --season 2026
"""
from __future__ import annotations

import argparse
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from prediction_audit.ingestion.log import CadenceSkip, SourceUnavailable, run_job  # noqa: E402
from prediction_audit.ingestion.market_lines import (  # noqa: E402
    APPROVED_BOOKMAKERS,
    BASE,
    SOURCE,
    _build_game_id_lookup,
    _load_env_key,
)

# Real, explicit start-of-list market scope (see module docstring). Odds API keys confirmed live
# (2026-09-11): each one was directly requested and returned real bookmaker data, not assumed
# from documentation alone.
MARKET_KEYS = [
    "player_anytime_td",
    "player_pass_yds",
    "player_rush_yds",
    "player_reception_yds",
    "player_pass_interceptions",
]

# Real, deliberate window -- don't spend real credits probing an event more than this many days
# out; sportsbooks generally haven't posted real player-prop lines that early anyway, and this
# bounds the real, total weekly cost to games actually close enough to have markets.
WINDOW_DAYS = 6


def _fetch_real_upcoming_events(key: str) -> list[dict]:
    """Real, FREE call (confirmed directly -- doesn't move x-requests-remaining) -- just event
    ids/metadata, no odds, so this can be called every tick with zero real cost."""
    r = requests.get(f"{BASE}/sports/americanfootball_nfl/events",
                      params={"apiKey": key}, timeout=30)
    if r.status_code != 200:
        raise SourceUnavailable(
            f"Real Odds API events request failed: HTTP {r.status_code} -- {r.text[:300]}"
        )
    return r.json()


def _should_capture_event(conn: sqlite3.Connection, game_id: str, kickoff: datetime,
                           now: datetime) -> tuple[bool, str]:
    """Real, deliberately simple beta-phase gate: the workflow's own cron already fires once
    daily (see player_props_capture.yml), so this is just a safety net against a real duplicate
    capture (e.g. a manual workflow_dispatch re-run the same day) -- skip only if this exact
    game was already captured within the last ~20 real hours."""
    cur = conn.execute(
        "SELECT MAX(captured_at) FROM raw_player_prop_captures WHERE game_id = ?", (game_id,)
    )
    row = cur.fetchone()
    last = datetime.fromisoformat(row[0]) if row and row[0] else None
    if last is None or (now - last) >= timedelta(hours=20):
        return True, "real once-daily capture due"
    return False, f"already captured {(now - last).total_seconds() / 3600:.1f}h ago " \
                   f"(<20h, once-daily gate not due yet)"


def _extract_prop_rows(outcomes: list[dict]) -> dict[str, dict]:
    """Real, generic grouping across the two real outcome shapes confirmed live: Over/Under
    pairs (with a real `point`) for yardage/attempt markets, and single Yes prices (no `point`)
    for player_anytime_td."""
    by_player: dict[str, dict] = {}
    for o in outcomes:
        player = o.get("description")
        if not player:
            continue
        entry = by_player.setdefault(player, {"line_value": None, "over_odds": None,
                                                "under_odds": None})
        point = o.get("point")
        if point is not None:
            entry["line_value"] = point
        name = o.get("name")
        if name in ("Over", "Yes"):
            entry["over_odds"] = o.get("price")
        elif name in ("Under", "No"):
            entry["under_odds"] = o.get("price")
    return by_player


def _write(conn: sqlite3.Connection, ingestion_id: int, season: int, force: bool = False) -> int:
    now = datetime.now(UTC)
    key = _load_env_key()
    game_id_lookup = _build_game_id_lookup(season)

    events = _fetch_real_upcoming_events(key)
    if not events:
        raise SourceUnavailable("Real Odds API returned 0 real upcoming events.")

    due_events = []
    unmatched = 0
    for event in events:
        game_id = game_id_lookup.get((event["home_team"], event["away_team"]))
        if game_id is None:
            unmatched += 1
            continue
        kickoff_time = event.get("commence_time")
        if kickoff_time is None:
            continue
        real_kickoff = datetime.fromisoformat(kickoff_time.replace("Z", "+00:00"))
        if real_kickoff <= now or real_kickoff - now > timedelta(days=WINDOW_DAYS):
            continue
        if force:
            # Real, deliberate manual-test bypass ONLY -- never used by the scheduled workflow
            # (which never passes --force). Skips the cadence gate but nothing else: still a
            # real API call, real approved-book filter, real post-kickoff exclusion.
            should, reason = True, "--force: cadence gate bypassed for a manual test capture"
        else:
            should, reason = _should_capture_event(conn, game_id, real_kickoff, now)
        print(f"  {event['home_team']} vs {event['away_team']}: {reason}")
        if should:
            due_events.append((event["id"], game_id, kickoff_time))

    if not due_events:
        raise CadenceSkip(
            f"No real event due for a props capture this tick "
            f"({len(events)} real upcoming events checked, {unmatched} unmatched)."
        )
    if force:
        due_events = due_events[:1]  # real quota discipline -- a manual test needs only one

    captured_at = datetime.now(UTC).isoformat()
    rows = []
    for event_id, game_id, kickoff_time in due_events:
        r = requests.get(
            f"{BASE}/sports/americanfootball_nfl/events/{event_id}/odds",
            params={"apiKey": key, "regions": "us", "markets": ",".join(MARKET_KEYS),
                    "oddsFormat": "american"},
            timeout=30,
        )
        if r.status_code != 200:
            print(f"  real props request failed for {game_id}: HTTP {r.status_code} -- "
                  f"{r.text[:200]}")
            continue
        data = r.json()
        for bm in data.get("bookmakers", []):
            book = bm["key"]
            if book not in APPROVED_BOOKMAKERS:
                continue  # real, deliberate default-deny -- same discipline as market_lines.py
            for market in bm.get("markets", []):
                if market["key"] not in MARKET_KEYS:
                    continue
                for player, vals in _extract_prop_rows(market.get("outcomes", [])).items():
                    rows.append((
                        ingestion_id, game_id, player, market["key"], book,
                        vals["line_value"], vals["over_odds"], vals["under_odds"],
                        captured_at, kickoff_time, SOURCE, "VERIFIED",
                    ))

    if rows:
        conn.executemany(
            "INSERT INTO raw_player_prop_captures (ingestion_id, game_id, player_name, "
            "market_key, sportsbook, line_value, over_odds, under_odds, captured_at, "
            "kickoff_time, source, market_data_status) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    print(f"  real events captured this tick: {len(due_events)}, real rows written: {len(rows)}")
    return len(rows)


def main(season: int, force: bool = False) -> dict:
    result = run_job("player_props", SOURCE, lambda conn, iid: _write(conn, iid, season, force))
    print(f"player_props job: {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--force", action="store_true",
                         help="Real, manual-test-only bypass of the cadence gate (captures "
                              "one due event regardless of anchor hour / pre-kickoff window). "
                              "Never used by the scheduled workflow.")
    args = parser.parse_args()
    main(args.season, args.force)
