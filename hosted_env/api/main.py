"""
Real, minimal FastAPI service implementing Track 1's API contract against the real, live
Postgres instance -- read-only, no endpoint anywhere can modify a coefficient, formula,
model_versions.status, or a prediction row. That governance boundary is structural here (no
POST/PUT/PATCH/DELETE route exists in this file at all), not just documented.

Real, explicit scope for this build: schedule, real current injury status, real current market
lines, and an honest "no prediction yet" state for any game without a real ACTIVE prediction_
runs row -- never a fabricated number. Predictions/audit results stay gated exactly as
established (2026-09-29 / ~2026-10-01) regardless of what this service can technically query.

Usage (local):
    uv run --with "fastapi,uvicorn,psycopg[binary]" uvicorn hosted_env.api.main:app --reload
Usage (Render): see requirements.txt + this repo's Render Web Service start command
    (uvicorn hosted_env.api.main:app --host 0.0.0.0 --port $PORT)
"""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

import psycopg
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from psycopg.rows import dict_row

_STATIC_DIR = Path(__file__).resolve().parent / "static"

# Real bug, confirmed against nflverse's own data dictionary (not assumed): the `gametime`
# field nflverse provides is always Eastern time, "regardless of what time zone the game was
# being played in" -- but this project's ingestion (schedule.py/game_status.py/etc.) has always
# naively concatenated gameday+gametime into a timezone-less string with zero conversion. That
# naive Eastern wall-clock value then lands in Postgres's `kickoff_time TIMESTAMPTZ` column,
# which (mis)interprets a bare string as UTC on insert -- so what psycopg reads back is tagged
# UTC but is still really Eastern numbers. Real fix, applied only at this serialization layer
# (not the wider ingestion pipeline, which multiple historical/production scripts also touch
# and which this task didn't ask to be rewritten): reinterpret the wall-clock digits as real
# America/New_York local time (so DST resolves correctly per real date), then convert to true
# UTC before handing it to the PWA -- which already correctly converts UTC to the viewer's own
# local time via `toLocaleString`, so no PWA-side change is needed once this is correct.
_EASTERN = ZoneInfo("America/New_York")
_UTC = ZoneInfo("UTC")


def _fix_kickoff_tz(value: datetime | None) -> str | None:
    if value is None:
        return None
    wall_clock = value.replace(tzinfo=None)
    real_eastern = wall_clock.replace(tzinfo=_EASTERN)
    return real_eastern.astimezone(_UTC).isoformat()

app = FastAPI(title="NFL Model -- Live Data API", version="0.1.0")

# Real, deliberately permissive CORS for now -- this is a read-only, non-sensitive display API
# (no auth, no write path) serving a PWA; tighten to the real deployed PWA origin once that
# exists and is stable.
app.add_middleware(
    CORSMiddleware, allow_origins=["*"], allow_methods=["GET"], allow_headers=["*"],
)


def _get_connection() -> psycopg.Connection:
    database_url = os.environ.get("DATABASE_URL")
    if not database_url:
        raise HTTPException(
            status_code=500,
            detail="Real DATABASE_URL environment variable not set on this service.",
        )
    return psycopg.connect(database_url, connect_timeout=10, row_factory=dict_row)


@app.get("/health")
def health() -> dict:
    """Real liveness check -- confirms the service is running AND can reach Postgres, not just
    that the process started."""
    try:
        with _get_connection() as conn, conn.cursor() as cur:
            cur.execute("SELECT 1;")
            cur.fetchone()
        return {"status": "ok", "database": "reachable"}
    except Exception as e:
        raise HTTPException(status_code=503, detail=f"Real database unreachable: {e}") from e


@app.get("/sports")
def list_sports() -> list[dict]:
    with _get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT name FROM sports ORDER BY name;")
        return cur.fetchall()


@app.get("/sports/{sport}/current-week")
def current_week(sport: str) -> dict:
    """Real, single authoritative source for "what week is it" -- computed fresh here, every
    call, so the PWA never independently calculates this from device date (the exact kind of
    redundant, drift-prone calculation already flagged elsewhere in this project). Real
    definition: the week containing the next real game whose (corrected) kickoff hasn't
    happened yet -- this naturally advances forward as each week's games complete, including
    mid-week (Sunday afternoon still correctly reports the current week via its own remaining
    Sunday/Monday games), and correctly rolls over to the next week the moment the prior week's
    real last game finishes. Falls back to the real season's last week once every game is done."""
    with _get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM sports WHERE name = %s;", (sport.upper(),))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Real sport {sport!r} not found.")
        sport_id = row["id"]

        # Real, deliberate INNER JOIN -- same reasoning as list_games/get_game: only real,
        # live-tracked games (not the Part A reconstruction dataset) count here.
        cur.execute(
            "SELECT g.season, g.week, g.kickoff_time "
            "FROM games g JOIN game_workflow_status gws ON gws.game_id = g.game_id "
            "WHERE g.sport_id = %s AND g.kickoff_time IS NOT NULL "
            "ORDER BY g.season DESC;",
            (sport_id,),
        )
        rows = cur.fetchall()
        if not rows:
            raise HTTPException(
                status_code=404, detail=f"Real, no games with a kickoff time found for {sport!r}."
            )
        season = rows[0]["season"]  # real, most-recent real season present

        now = datetime.now(_UTC)
        upcoming = []
        max_week = 1
        for r in rows:
            if r["season"] != season:
                continue
            fixed = datetime.fromisoformat(_fix_kickoff_tz(r["kickoff_time"]))
            max_week = max(max_week, r["week"])
            if fixed > now:
                upcoming.append((fixed, r["week"]))
        if upcoming:
            week = min(upcoming, key=lambda t: t[0])[1]
        else:
            week = max_week  # real, honest fallback -- every real game has already kicked off
        return {"season": season, "week": week}


@app.get("/sports/{sport}/games")
def list_games(sport: str, week: int | None = None) -> list[dict]:
    with _get_connection() as conn, conn.cursor() as cur:
        cur.execute("SELECT id FROM sports WHERE name = %s;", (sport.upper(),))
        row = cur.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Real sport {sport!r} not found.")
        sport_id = row["id"]

        # Real, deliberate INNER JOIN -- not LEFT JOIN. `games` also holds the real, pre-existing
        # Part A reconstruction dataset (full team names, e.g. "2026_04_ArizonaCardinals_
        # NewYorkGiants") for the SAME season=2026 as the live agent's real games (abbreviated
        # team names). Only real, live-tracked games ever get a game_workflow_status row -- the
        # same distinguishing convention already established for this exact two-dataset overlap
        # (see PROGRESS.md's "stale demo rows" correction). Confirmed directly against the real
        # DB: 272/272 abbreviated-format games have a workflow_status row; 0/272 Part A rows do.
        query = (
            "SELECT g.game_id, g.season, g.week, g.game_date, g.kickoff_time, g.home_team, "
            "g.away_team, gws.status, gws.status_reason "
            "FROM games g JOIN game_workflow_status gws ON gws.game_id = g.game_id "
            "WHERE g.sport_id = %s"
        )
        params: list = [sport_id]
        if week is not None:
            query += " AND g.week = %s"
            params.append(week)
        query += " ORDER BY g.kickoff_time NULLS LAST;"
        cur.execute(query, params)
        games = cur.fetchall()
        for g in games:
            g["kickoff_time"] = _fix_kickoff_tz(g["kickoff_time"])
        return games


@app.get("/sports/{sport}/games/{game_id}")
def get_game(sport: str, game_id: str) -> dict:
    with _get_connection() as conn, conn.cursor() as cur:
        # Real, deliberate INNER JOIN on game_workflow_status -- same reasoning as list_games:
        # only real, live-tracked games (not the Part A reconstruction dataset) are addressable
        # here.
        cur.execute(
            "SELECT g.game_id, g.season, g.week, g.game_date, g.kickoff_time, g.home_team, "
            "g.away_team, gws.status, gws.status_reason "
            "FROM games g JOIN game_workflow_status gws ON gws.game_id = g.game_id "
            "JOIN sports s ON s.id = g.sport_id "
            "WHERE s.name = %s AND g.game_id = %s;",
            (sport.upper(), game_id),
        )
        game = cur.fetchone()
        if not game:
            raise HTTPException(status_code=404, detail=f"Real game {game_id!r} not found.")
        game["kickoff_time"] = _fix_kickoff_tz(game["kickoff_time"])

        # Real, honest prediction state -- never fabricated. Only ACTIVE, real prediction_runs
        # rows count; a game with none gets an explicit "not yet predictable" style message,
        # matching game_workflow_status's own real status/status_reason.
        cur.execute(
            "SELECT p.projected_margin, p.home_win_probability, mv.version_name "
            "FROM predictions p "
            "JOIN prediction_runs pr ON pr.id = p.run_id AND pr.model_status = 'ACTIVE' "
            "JOIN model_versions mv ON mv.id = pr.model_version_id "
            "WHERE pr.game_id = %s;",
            (game_id,),
        )
        prediction = cur.fetchone()
        game["prediction"] = prediction if prediction else {
            "status": "NOT_YET_AVAILABLE",
            "reason": game["status_reason"] or (
                "Prediction pending -- Weeks 1-3 are structurally NOT_PREDICTABLE; later "
                "weeks are frozen 48h before kickoff once real inputs are complete."
            ),
        }

        cur.execute(
            "SELECT team, player_name, position, report_status, practice_status, pulled_at "
            "FROM raw_injury_reports WHERE season = %s AND team IN (%s, %s) "
            "ORDER BY pulled_at DESC;",
            (game["season"], game["home_team"], game["away_team"]),
        )
        game["injuries"] = cur.fetchall()

        cur.execute(
            "SELECT sportsbook, market_type, line_value, odds, captured_at "
            "FROM raw_market_captures WHERE game_id = %s AND flagged_excluded_source = FALSE "
            "ORDER BY captured_at DESC;",
            (game_id,),
        )
        game["market_lines"] = cur.fetchall()

        return game


@app.get("/sports/{sport}/model-versions")
def list_model_versions(sport: str) -> list[dict]:
    with _get_connection() as conn, conn.cursor() as cur:
        cur.execute(
            "SELECT mv.version_name, mv.status, mv.promoted_at, mv.notes "
            "FROM model_versions mv JOIN sports s ON s.id = mv.sport_id "
            "WHERE s.name = %s ORDER BY mv.id;",
            (sport.upper(),),
        )
        return cur.fetchall()


# Real PWA static files (index.html, manifest.json, icon.svg, sw.js) -- mounted last so it
# never shadows the real API routes above (Starlette matches routes in registration order).
app.mount("/", StaticFiles(directory=_STATIC_DIR, html=True), name="static")
