"""
Real capture for two new, explicitly-approved market categories (restructure_dropdown_
navigation.md, explicit user go-ahead 2026-09-12 after the real, measured cost below):
  - 1st-half game lines: `h2h_h1` (moneyline), `spreads_h1`, `totals_h1` -- same real shape and
    home-side/Over-side-only convention as market_lines.py's own full-game spread/total/
    moneyline, so these write into the SAME `raw_market_captures` table (as new `market_type`
    values 'moneyline_h1'/'spread_h1'/'total_h1'), not a new table.
  - `team_totals` -- a genuine GAME-level (not player-specific) prop, confirmed live: each real
    team gets its own real Over/Under total-points line. Structurally identical to a player prop
    (Over/Under + a `description` naming who it's about) except keyed by TEAM, not player -- own
    table, `raw_team_total_captures`, same real pattern as raw_player_prop_captures.

Real, measured cost (2026-09-12, directly against the live API before writing this file): these
4 markets together cost 4 credits/event, US-only, via the per-event endpoint (the bulk endpoint
this project's market_lines.py uses rejects them outright -- HTTP 422 "not supported by this
endpoint"). Same real once-daily cadence and per-event duplicate-run safety net as
player_props.py -- see that module's own docstring for why (explicit user request to keep the
beta period simple), and the same real post-kickoff exclusion / approved-book allow-list.

Usage:
    uv run python -m prediction_audit.ingestion.game_extras --season 2026
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
from prediction_audit.ingestion.player_props import _fetch_real_upcoming_events  # noqa: E402

# Real, explicit market scope (see module docstring). Each key confirmed live (2026-09-12) via
# a direct API call, not assumed from documentation.
GAME_LINE_MARKET_KEYS = {"h2h_h1": "moneyline_h1", "spreads_h1": "spread_h1",
                          "totals_h1": "total_h1"}
TEAM_TOTAL_MARKET_KEY = "team_totals"
ALL_MARKET_KEYS = [*GAME_LINE_MARKET_KEYS, TEAM_TOTAL_MARKET_KEY]

# Same real window as player_props.py -- don't probe an event more than this many days out.
WINDOW_DAYS = 6


def _should_capture_event(conn: sqlite3.Connection, game_id: str, now: datetime) -> tuple[bool, str]:
    """Real, same once-daily duplicate-run safety net as player_props.py's own gate -- checks
    BOTH real tables this script writes to, since either could hold the real last-captured
    timestamp for this game."""
    cur = conn.execute(
        "SELECT MAX(captured_at) FROM ("
        "  SELECT captured_at FROM raw_market_captures WHERE game_id = ? "
        "    AND market_type IN ('moneyline_h1', 'spread_h1', 'total_h1')"
        "  UNION ALL "
        "  SELECT captured_at FROM raw_team_total_captures WHERE game_id = ?"
        ")", (game_id, game_id),
    )
    row = cur.fetchone()
    last = datetime.fromisoformat(row[0]) if row and row[0] else None
    if last is None or (now - last) >= timedelta(hours=20):
        return True, "real once-daily capture due"
    return False, f"already captured {(now - last).total_seconds() / 3600:.1f}h ago " \
                   f"(<20h, once-daily gate not due yet)"


def _extract_team_total_rows(outcomes: list[dict]) -> dict[str, dict]:
    """Real, identical generic Over/Under-by-description grouping to player_props.py's own
    `_extract_prop_rows` -- team_totals uses the exact same real outcome shape (description =
    the real, full team name this line is about), just never a Yes/No single-sided market like
    player_anytime_td, so no such branch is needed here."""
    by_team: dict[str, dict] = {}
    for o in outcomes:
        team = o.get("description")
        if not team:
            continue
        entry = by_team.setdefault(team, {"line_value": None, "over_odds": None,
                                            "under_odds": None})
        point = o.get("point")
        if point is not None:
            entry["line_value"] = point
        name = o.get("name")
        if name == "Over":
            entry["over_odds"] = o.get("price")
        elif name == "Under":
            entry["under_odds"] = o.get("price")
    return by_team


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
            should, reason = True, "--force: cadence gate bypassed for a manual test capture"
        else:
            should, reason = _should_capture_event(conn, game_id, now)
        print(f"  {event['home_team']} vs {event['away_team']}: {reason}")
        if should:
            due_events.append((event["id"], game_id, event["home_team"], kickoff_time))

    if not due_events:
        raise CadenceSkip(
            f"No real event due for a game-extras capture this tick "
            f"({len(events)} real upcoming events checked, {unmatched} unmatched)."
        )
    if force:
        due_events = due_events[:1]  # real quota discipline -- a manual test needs only one

    captured_at = datetime.now(UTC).isoformat()
    line_rows = []
    team_total_rows = []
    for event_id, game_id, home_team_full, kickoff_time in due_events:
        r = requests.get(
            f"{BASE}/sports/americanfootball_nfl/events/{event_id}/odds",
            params={"apiKey": key, "regions": "us", "markets": ",".join(ALL_MARKET_KEYS),
                    "oddsFormat": "american"},
            timeout=30,
        )
        if r.status_code != 200:
            print(f"  real game-extras request failed for {game_id}: HTTP {r.status_code} -- "
                  f"{r.text[:200]}")
            continue
        data = r.json()
        for bm in data.get("bookmakers", []):
            book = bm["key"]
            if book not in APPROVED_BOOKMAKERS:
                continue  # real, deliberate default-deny -- same discipline as market_lines.py
            for market in bm.get("markets", []):
                mkey = market["key"]
                if mkey in GAME_LINE_MARKET_KEYS:
                    # Real, identical home-side/Over-side-only convention to market_lines.py's
                    # own full-game spread/total/moneyline capture -- see that module's own
                    # comment for the full rationale.
                    market_type = GAME_LINE_MARKET_KEYS[mkey]
                    for outcome in market.get("outcomes", []):
                        if market_type in ("moneyline_h1", "spread_h1") and \
                                outcome.get("name") != home_team_full:
                            continue
                        if market_type == "total_h1" and outcome.get("name") != "Over":
                            continue
                        line_rows.append((
                            ingestion_id, game_id, book, market_type, outcome.get("point"),
                            outcome.get("price"), captured_at, kickoff_time, SOURCE, "VERIFIED",
                        ))
                elif mkey == TEAM_TOTAL_MARKET_KEY:
                    for team, vals in _extract_team_total_rows(market.get("outcomes", [])).items():
                        team_total_rows.append((
                            ingestion_id, game_id, team, book,
                            vals["line_value"], vals["over_odds"], vals["under_odds"],
                            captured_at, kickoff_time, SOURCE, "VERIFIED",
                        ))

    if line_rows:
        conn.executemany(
            "INSERT INTO raw_market_captures (ingestion_id, game_id, sportsbook, "
            "market_type, line_value, odds, captured_at, kickoff_time, source, "
            "market_data_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            line_rows,
        )
    if team_total_rows:
        conn.executemany(
            "INSERT INTO raw_team_total_captures (ingestion_id, game_id, team, sportsbook, "
            "line_value, over_odds, under_odds, captured_at, kickoff_time, source, "
            "market_data_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            team_total_rows,
        )
    if line_rows or team_total_rows:
        conn.commit()
    total_rows = len(line_rows) + len(team_total_rows)
    print(f"  real events captured this tick: {len(due_events)}, real 1H rows: "
          f"{len(line_rows)}, real team-total rows: {len(team_total_rows)}")
    return total_rows


def main(season: int, force: bool = False) -> dict:
    result = run_job("game_extras", SOURCE, lambda conn, iid: _write(conn, iid, season, force))
    print(f"game_extras job: {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    parser.add_argument("--force", action="store_true",
                         help="Real, manual-test-only bypass of the cadence gate. Never used "
                              "by the scheduled workflow.")
    args = parser.parse_args()
    main(args.season, args.force)
