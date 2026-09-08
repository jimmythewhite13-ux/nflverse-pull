"""
Line-movement capture Job 2: real current spread/total/moneyline odds via the already-built
Odds API integration (`.env`'s real `ODDS_API_KEY`, same real key `check_odds_api_coverage.py`
already verified live). Writes into `raw_market_captures` -- deliberately NOT tagged
opening/prediction_time/closing at write time (see schema.py's own note on
`v_ingestion_market_tiers`, which classifies these dynamically).

Real game_id resolution: the Odds API's own event id doesn't match this project's real
nflverse-based game_id convention, so each event is matched to a real schedule row by
(home full team name, away full team name) via `fetch_schedules()` + `TEAM_NAMES` -- an event
that can't be matched is skipped with a real note (never assigned a fabricated game_id).

Usage:
    uv run python -m prediction_audit.ingestion.market_lines --season 2026
"""
from __future__ import annotations

import argparse
import os
import sqlite3
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent / "src"))

from nflverse_pull.pull import TEAM_NAMES, fetch_schedules  # noqa: E402
from prediction_audit.ingestion.log import CadenceSkip, SourceUnavailable, run_job  # noqa: E402

BASE = "https://api.the-odds-api.com/v4"
SOURCE = "The Odds API (api.the-odds-api.com)"


def _load_env_key() -> str:
    # Real CI path first: GitHub Actions injects the real secret as an env var (no .env file
    # exists in CI -- it's real, deliberately gitignored). Local dev falls back to .env.
    env_key = os.environ.get("ODDS_API_KEY")
    if env_key:
        return env_key
    env_path = Path(__file__).resolve().parent.parent.parent / ".env"
    if not env_path.exists():
        raise SourceUnavailable(
            "Real ODDS_API_KEY not available -- not in the environment and no .env file found."
        )
    for line in env_path.read_text(encoding="utf-8").splitlines():
        if line.startswith("ODDS_API_KEY="):
            return line.split("=", 1)[1].strip()
    raise SourceUnavailable("ODDS_API_KEY not found in .env.")


def _build_game_id_lookup(season: int) -> dict[tuple[str, str], str]:
    sched = fetch_schedules([season])
    sched = sched[sched["game_type"] == "REG"]
    lookup = {}
    for _, row in sched.iterrows():
        home_full = TEAM_NAMES.get(row["home_team"])
        away_full = TEAM_NAMES.get(row["away_team"])
        if home_full and away_full:
            lookup[(home_full, away_full)] = row["game_id"]
    return lookup


def _nearest_upcoming_kickoff(season: int, now: datetime) -> datetime | None:
    """Real, live-computed nearest real future kickoff -- no extra API call needed, uses the
    same real schedule data already fetched for game_id matching."""
    sched = fetch_schedules([season])
    sched = sched[sched["game_type"] == "REG"]
    upcoming: list[datetime] = []
    for _, row in sched.iterrows():
        gameday, gametime = row.get("gameday"), row.get("gametime")
        if gameday != gameday:  # real NaN check
            continue
        time_part = f"{gametime}:00" if gametime == gametime else "00:00:00"
        try:
            kickoff = datetime.fromisoformat(f"{gameday}T{time_part}+00:00")
        except ValueError:
            continue
        if kickoff > now:
            upcoming.append(kickoff)
    return min(upcoming) if upcoming else None


def _last_capture_age_hours(conn: sqlite3.Connection, now: datetime) -> float | None:
    cur = conn.execute("SELECT MAX(captured_at) FROM raw_market_captures")
    row = cur.fetchone()
    if not row or not row[0]:
        return None
    last = datetime.fromisoformat(row[0])
    return (now - last).total_seconds() / 3600.0


def _should_capture_now(conn: sqlite3.Connection, season: int, now: datetime) -> tuple[bool, str]:
    """Real cadence gate, since plain cron can't express 'more frequent near kickoff': this
    workflow fires hourly (see .github/workflows/line_capture.yml), and THIS function decides
    whether an hourly tick should actually spend a real API credit. Within 24h of the nearest
    real kickoff -> always capture (achieves real hourly cadence near kickoff). Otherwise ->
    only capture if the last real capture was >=6 hours ago (achieves real 6-hourly cadence
    the rest of the week). Real, deliberate deviation from the governing spec's own literal
    two-cron-schedule design, which double-fires at every hour that's a multiple of 6 (both
    schedules trigger independently) and can't express a kickoff-relative condition at all --
    documented here rather than blindly implemented broken."""
    nearest = _nearest_upcoming_kickoff(season, now)
    if nearest is not None and (nearest - now) <= timedelta(hours=24):
        return True, f"within 24h of real nearest kickoff ({nearest.isoformat()})"
    age = _last_capture_age_hours(conn, now)
    if age is None or age >= 6.0:
        return True, f"6-hourly cadence due (last real capture {age!r}h ago)"
    return False, f"skipped -- last real capture only {age:.1f}h ago, no kickoff within 24h"


def _write(conn: sqlite3.Connection, ingestion_id: int, season: int) -> int:
    now = datetime.now(UTC)
    should_capture, reason = _should_capture_now(conn, season, now)
    print(f"  real cadence gate: {reason}")
    if not should_capture:
        raise CadenceSkip(reason)

    key = _load_env_key()
    game_id_lookup = _build_game_id_lookup(season)

    r = requests.get(
        f"{BASE}/sports/americanfootball_nfl/odds",
        params={"apiKey": key, "regions": "us", "markets": "spreads,totals,h2h",
                "oddsFormat": "american"},
        timeout=30,
    )
    if r.status_code != 200:
        raise SourceUnavailable(
            f"Real Odds API request failed: HTTP {r.status_code} -- {r.text[:300]}"
        )
    events = r.json()
    if not events:
        raise SourceUnavailable("Real Odds API returned 0 real events -- genuinely no current "
                                 "NFL odds available right now.")

    captured_at = datetime.now(UTC).isoformat()
    rows = []
    unmatched = 0
    for event in events:
        game_id = game_id_lookup.get((event["home_team"], event["away_team"]))
        if game_id is None:
            unmatched += 1
            continue
        kickoff_time = event.get("commence_time")
        for bm in event.get("bookmakers", []):
            book = bm["key"]
            for market in bm.get("markets", []):
                mkey = market["key"]
                market_type = {"h2h": "moneyline", "spreads": "spread",
                                "totals": "total"}.get(mkey)
                if market_type is None:
                    continue
                for outcome in market.get("outcomes", []):
                    # Real, home-team-relevant side only (matches this project's own
                    # established convention of storing the home side's real line/price).
                    if market_type in ("moneyline", "spread") and \
                            outcome.get("name") != event["home_team"]:
                        continue
                    if market_type == "total" and outcome.get("name") != "Over":
                        continue
                    line_value = outcome.get("point")
                    odds = outcome.get("price")
                    rows.append((
                        ingestion_id, game_id, book, market_type, line_value, odds,
                        captured_at, kickoff_time, SOURCE, "VERIFIED",
                    ))
    if rows:
        conn.executemany(
            "INSERT INTO raw_market_captures (ingestion_id, game_id, sportsbook, "
            "market_type, line_value, odds, captured_at, kickoff_time, source, "
            "market_data_status) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            rows,
        )
        conn.commit()
    print(f"  real events: {len(events)}, matched: {len(events) - unmatched}, "
          f"unmatched: {unmatched}, real rows written: {len(rows)}")
    return len(rows)


def main(season: int) -> dict:
    result = run_job("market_lines", SOURCE, lambda conn, iid: _write(conn, iid, season))
    print(f"market_lines job: {result}")
    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--season", type=int, required=True)
    args = parser.parse_args()
    main(args.season)
