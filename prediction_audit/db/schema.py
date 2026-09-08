"""
Step 2 of the NFL Model v35 Validation/Audit master spec: the permanent Prediction Audit
database. Every future model prediction creates an immutable audit record here -- rows are
INSERT-only; re-running the model for a game that already has a prediction creates a NEW
`prediction_runs` row (new run_id), never an UPDATE to an existing one. This is the
foundation the spec's own Steps 3-14 build on (state snapshots, component attribution,
market/CLV, ablation, calibration).

Design choices, and why:
- SQLite, not the Excel workbook itself -- tracking thousands of historical predictions with
  full component/state breakdowns doesn't fit a spreadsheet, and the spec's own Step 6
  (walk-forward reconstruction) needs to run this programmatically at scale.
- Normalized `component_contributions` (one row per named term per prediction) rather than
  ~80 individual columns -- matches Step 4's own example ("Base Team Rating = -2.4, QB =
  -0.8, ...") directly: querying "every game's HFA Delta contribution" is one WHERE clause,
  not 80 hardcoded column names, and adding a new component later needs no schema migration.
- `state_snapshot_json` (one JSON blob per prediction, covering every category Step 3 lists:
  team strength, QB, OL, RB, WR/TE, defense, matchups, environment, regression, injuries) --
  the spec's own field list runs to 80+ fields, most of which are already exactly what this
  project's own Excel tabs compute per player/team; storing them as one real structured
  snapshot per prediction avoids either an 80-column table (mostly NULL for any given game)
  or hand-picking which subset to normalize. Queryable at the top level via SQLite's own
  JSON1 functions when a specific field is needed for analysis.
- `market_lines` carries a `market_data_status` column (VERIFIED / UNVERIFIED / MISSING) per
  the spec's own explicit instruction -- this project has never sourced verified historical
  odds with real timestamps, so every row inserted for a pre-existing game defaults to
  MISSING rather than a fabricated line ("Do not fabricate historical betting lines").
- `errors` and `clv` are NOT separate stored tables -- both are pure functions of
  predictions+results (error) and predictions+market_lines (CLV), which would otherwise risk
  drifting stale if results/market data is corrected after being entered. Exposed as SQL VIEWs
  instead (see VIEWS_SQL below), computed fresh on every query.
- No fabricated data anywhere: every INSERT helper takes real values as arguments; there is
  no "if missing, invent a plausible value" branch anywhere in this module.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path

DEFAULT_DB_PATH = Path(__file__).resolve().parent / "prediction_audit.sqlite3"

SCHEMA_SQL = """
-- ==== Models: one row per real model version this audit ever scored a prediction with =====
CREATE TABLE IF NOT EXISTS models (
    model_version   TEXT PRIMARY KEY,      -- e.g. 'v35.0', 'v36.0'
    description     TEXT NOT NULL,
    workbook_sha256 TEXT,                  -- real checksum of the frozen .xlsx, if Excel-based
    frozen_at       TEXT NOT NULL,         -- ISO8601 -- when this version became immutable
    notes           TEXT
);

-- ==== Games: one row per real NFL game (any season) ========================================
CREATE TABLE IF NOT EXISTS games (
    game_id         TEXT PRIMARY KEY,      -- real nflverse game_id where available
    season          INTEGER NOT NULL,
    week            INTEGER NOT NULL,
    game_date       TEXT,                  -- ISO8601 date
    kickoff_time    TEXT,                  -- ISO8601 datetime, real, if known
    away_team       TEXT NOT NULL,
    home_team       TEXT NOT NULL,
    neutral_site    INTEGER NOT NULL DEFAULT 0,
    stadium         TEXT,
    surface         TEXT,
    timezone        TEXT
);

-- ==== Prediction runs: one row per (model_version, game, real prediction timestamp) ========
-- Immutable -- a re-run of the same model against the same game creates a NEW row, never an
-- UPDATE. run_id is the join key every other table below hangs off of.
CREATE TABLE IF NOT EXISTS prediction_runs (
    run_id                INTEGER PRIMARY KEY AUTOINCREMENT,
    model_version         TEXT NOT NULL REFERENCES models(model_version),
    game_id               TEXT NOT NULL REFERENCES games(game_id),
    prediction_timestamp  TEXT NOT NULL,   -- ISO8601 -- when this specific run was made
    data_cutoff_timestamp TEXT,            -- ISO8601 -- latest real info this run could use
    data_version          TEXT,            -- free-text id for the real data pull this run used
    model_status          TEXT NOT NULL DEFAULT 'ACTIVE'  -- ACTIVE / SUPERSEDED / VOID
);

-- ==== Predictions: the model's real output for one run ======================================
CREATE TABLE IF NOT EXISTS predictions (
    run_id                INTEGER PRIMARY KEY REFERENCES prediction_runs(run_id),
    away_projected_points REAL NOT NULL,
    home_projected_points REAL NOT NULL,
    projected_margin      REAL NOT NULL,   -- home - away, matches this project's convention
    projected_total       REAL NOT NULL,
    home_win_probability  REAL NOT NULL,
    away_win_probability  REAL NOT NULL,
    confidence            REAL             -- real Confidence Composite (0-1), if computed
);

-- ==== Component contributions: one row per named term per run (Step 4) =====================
CREATE TABLE IF NOT EXISTS component_contributions (
    run_id             INTEGER NOT NULL REFERENCES prediction_runs(run_id),
    component_name     TEXT NOT NULL,   -- e.g. 'HFA Delta (Home)', matches
                                         -- v35_core_formula_components.csv's Component_Name
    contribution_value REAL NOT NULL,   -- real points contributed, signed
    side               TEXT NOT NULL,   -- 'HOME' or 'AWAY'
    PRIMARY KEY (run_id, component_name, side)
);

-- ==== Full model-state snapshot (Step 3) -- one row per run, one JSON blob covering every ==
-- category the spec lists (team strength, QB, OL, RB, WR/TE, defense, matchups, environment,
-- regression, injuries). See this module's own docstring for why JSON, not 80 columns.
CREATE TABLE IF NOT EXISTS state_snapshots (
    run_id              INTEGER PRIMARY KEY REFERENCES prediction_runs(run_id),
    state_snapshot_json TEXT NOT NULL   -- real JSON object, see snapshot.py for the real schema
);

-- ==== Market lines: real sportsbook data, honestly labeled when unverified/missing =========
CREATE TABLE IF NOT EXISTS market_lines (
    line_id            INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id             INTEGER NOT NULL REFERENCES prediction_runs(run_id),
    sportsbook         TEXT NOT NULL,
    market_type        TEXT NOT NULL,   -- 'spread' / 'total' / 'moneyline'
    line_stage         TEXT NOT NULL,   -- 'opening' / 'prediction_time' / 'closing'
    line_value         REAL,            -- NULL if genuinely not captured
    odds               REAL,
    line_timestamp     TEXT,            -- ISO8601, real, if known
    source             TEXT,
    market_data_status TEXT NOT NULL DEFAULT 'MISSING'
                        CHECK (market_data_status IN ('VERIFIED', 'UNVERIFIED', 'MISSING'))
);

-- ==== Results: real final outcomes, once known =============================================
CREATE TABLE IF NOT EXISTS results (
    game_id          TEXT PRIMARY KEY REFERENCES games(game_id),
    away_final_score INTEGER NOT NULL,
    home_final_score INTEGER NOT NULL
);

-- ==== Prop predictions (Step 14): one row per real player-prop prediction, same immutable ==
-- INSERT-only discipline as `predictions` -- a corrected/re-run prop projection gets a NEW row
-- via a new prediction_runs run_id, never an UPDATE. Mirrors predictions/results' own real
-- split: the prediction itself, its own real market line(s), and the real actual outcome
-- (once known) are three separate tables, not one, so a later result/line correction can never
-- silently overwrite an already-recorded prediction.
CREATE TABLE IF NOT EXISTS prop_predictions (
    prop_id         INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id          INTEGER NOT NULL REFERENCES prediction_runs(run_id),
    player_name     TEXT NOT NULL,
    team            TEXT NOT NULL,
    stat_type       TEXT NOT NULL,   -- e.g. 'passing_yards', 'receptions', 'rushing_yards'
    projected_value REAL NOT NULL
);

-- ==== Prop market lines: real sportsbook prop lines, honestly labeled when unverified/missing
-- (same real market_data_status convention as market_lines) ==================================
CREATE TABLE IF NOT EXISTS prop_market_lines (
    prop_line_id       INTEGER PRIMARY KEY AUTOINCREMENT,
    prop_id            INTEGER NOT NULL REFERENCES prop_predictions(prop_id),
    sportsbook         TEXT NOT NULL,
    line_value         REAL,            -- NULL if genuinely not captured
    over_odds          REAL,
    under_odds         REAL,
    line_stage         TEXT NOT NULL,   -- 'opening' / 'prediction_time' / 'closing'
    line_timestamp     TEXT,            -- ISO8601, real, if known
    source             TEXT,
    market_data_status TEXT NOT NULL DEFAULT 'MISSING'
                        CHECK (market_data_status IN ('VERIFIED', 'UNVERIFIED', 'MISSING'))
);

-- ==== Prop results: real final stat outcomes, once known =====================================
CREATE TABLE IF NOT EXISTS prop_results (
    prop_id      INTEGER PRIMARY KEY REFERENCES prop_predictions(prop_id),
    actual_value REAL NOT NULL
);

-- ==== Data quality flags per run =============================================================
CREATE TABLE IF NOT EXISTS data_quality (
    run_id                INTEGER PRIMARY KEY REFERENCES prediction_runs(run_id),
    missing_data_flag     INTEGER NOT NULL DEFAULT 0,
    data_quality_score    REAL,
    data_quality_status   TEXT,
    future_data_leak_flag INTEGER NOT NULL DEFAULT 0,
    timestamp_validation  TEXT,
    duplicate_flag        INTEGER NOT NULL DEFAULT 0,
    source_conflict_flag  INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_runs_game ON prediction_runs(game_id);
CREATE INDEX IF NOT EXISTS idx_runs_model ON prediction_runs(model_version);
CREATE INDEX IF NOT EXISTS idx_contrib_run ON component_contributions(run_id);
CREATE INDEX IF NOT EXISTS idx_market_run ON market_lines(run_id);
CREATE INDEX IF NOT EXISTS idx_prop_run ON prop_predictions(run_id);
CREATE INDEX IF NOT EXISTS idx_prop_market_prop ON prop_market_lines(prop_id);

-- ==== Automated agent layer (2026-09-08) -- real, INPUT-ONLY ingestion logging =============
-- Deliberately NOT keyed off prediction_runs/run_id: the automated agent's whole real purpose
-- is refreshing raw input data (injuries, rosters, schedule, market lines), never generating or
-- touching a model prediction. Tying this to run_id would require a prediction_runs row to
-- exist for every upcoming 2026 game before ingestion could even log a value -- i.e. it would
-- require "running the model" on 2026 data before Phase 11's single, official holdout
-- evaluation, which is exactly what the governance spec forbids. These tables are real,
-- standalone, timestamped ingestion logs -- structurally incapable of touching a coefficient,
-- formula, or prediction, by construction, not merely by convention.

-- One row per real scheduled ingestion job invocation -- the audit trail for Section 4's
-- "never skip silently" rule. status='MISSING' + source=NULL is a REAL, valid, expected
-- outcome (a genuinely unavailable source), not an error to hide.
CREATE TABLE IF NOT EXISTS ingestion_runs (
    ingestion_id    INTEGER PRIMARY KEY AUTOINCREMENT,
    job_name        TEXT NOT NULL,    -- 'injuries'/'rosters'/'schedule'/'stats'/'market_lines'
    run_timestamp   TEXT NOT NULL,    -- ISO8601, real
    status          TEXT NOT NULL CHECK (status IN ('SUCCESS', 'MISSING', 'FAILURE', 'SKIPPED')),
    source          TEXT,             -- real source name, or NULL if genuinely unavailable
    rows_written    INTEGER NOT NULL DEFAULT 0,
    detail          TEXT              -- free text: real error message, or a real note
);

CREATE TABLE IF NOT EXISTS raw_injury_reports (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ingestion_id    INTEGER NOT NULL REFERENCES ingestion_runs(ingestion_id),
    season          INTEGER NOT NULL,
    week            INTEGER,
    team            TEXT NOT NULL,
    player_name     TEXT NOT NULL,
    position        TEXT,
    report_status   TEXT,             -- real 'Out'/'Doubtful'/'Questionable'/etc, or NULL
    practice_status TEXT,
    pulled_at       TEXT NOT NULL,    -- ISO8601, real
    source          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_roster_snapshots (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ingestion_id    INTEGER NOT NULL REFERENCES ingestion_runs(ingestion_id),
    season          INTEGER NOT NULL,
    team            TEXT NOT NULL,
    player_name     TEXT NOT NULL,
    position        TEXT,
    depth_rank      INTEGER,
    roster_status   TEXT,
    pulled_at       TEXT NOT NULL,
    source          TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS raw_schedule_checks (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    ingestion_id    INTEGER NOT NULL REFERENCES ingestion_runs(ingestion_id),
    game_id         TEXT NOT NULL,
    season          INTEGER NOT NULL,
    week            INTEGER NOT NULL,
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    kickoff_time    TEXT,
    change_detected INTEGER NOT NULL DEFAULT 0,
    change_detail   TEXT,
    checked_at      TEXT NOT NULL,
    source          TEXT NOT NULL
);

-- Real market-line captures for CLV -- deliberately NOT tagged 'opening'/'closing' at write
-- time (a capture can't know it's the real LAST one before kickoff until kickoff has already
-- happened). Every capture is a real, timestamped snapshot; `v_ingestion_market_tiers` below
-- classifies opening/prediction_time/closing dynamically, same real pattern this project's
-- own v_clv view already uses for the prediction-linked market_lines table.
CREATE TABLE IF NOT EXISTS raw_market_captures (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    ingestion_id        INTEGER NOT NULL REFERENCES ingestion_runs(ingestion_id),
    game_id             TEXT NOT NULL,
    sportsbook          TEXT NOT NULL,
    market_type         TEXT NOT NULL,   -- 'spread' / 'total' / 'moneyline'
    line_value          REAL,
    odds                REAL,
    captured_at         TEXT NOT NULL,   -- ISO8601, real
    kickoff_time        TEXT,            -- real, for real elapsed-time tier classification
    source              TEXT NOT NULL,
    market_data_status  TEXT NOT NULL DEFAULT 'MISSING'
                         CHECK (market_data_status IN ('VERIFIED', 'UNVERIFIED', 'MISSING'))
);

CREATE INDEX IF NOT EXISTS idx_ingestion_runs_job ON ingestion_runs(job_name, run_timestamp);
CREATE INDEX IF NOT EXISTS idx_raw_injury_ingestion ON raw_injury_reports(ingestion_id);
CREATE INDEX IF NOT EXISTS idx_raw_roster_ingestion ON raw_roster_snapshots(ingestion_id);
CREATE INDEX IF NOT EXISTS idx_raw_schedule_ingestion ON raw_schedule_checks(ingestion_id);
CREATE INDEX IF NOT EXISTS idx_raw_market_game
    ON raw_market_captures(game_id, sportsbook, market_type);
"""

VIEWS_SQL = """
-- Real margin/total error -- a pure function of predictions+results, computed fresh every
-- query rather than stored, so a later results correction can never leave a stale cached
-- error value behind.
CREATE VIEW IF NOT EXISTS v_prediction_errors AS
SELECT
    p.run_id,
    pr.game_id,
    p.projected_margin,
    (r.home_final_score - r.away_final_score) AS actual_margin,
    p.projected_margin - (r.home_final_score - r.away_final_score) AS margin_error,
    ABS(p.projected_margin - (r.home_final_score - r.away_final_score)) AS absolute_margin_error,
    p.projected_total,
    (r.home_final_score + r.away_final_score) AS actual_total,
    p.projected_total - (r.home_final_score + r.away_final_score) AS total_error,
    ABS(p.projected_total - (r.home_final_score + r.away_final_score)) AS absolute_total_error,
    CASE WHEN (p.projected_margin > 0) = (r.home_final_score > r.away_final_score)
         THEN 1 ELSE 0 END AS winner_correct
FROM predictions p
JOIN prediction_runs pr ON pr.run_id = p.run_id
JOIN results r ON r.game_id = pr.game_id;

-- Real closing-line value -- only ever computed where a real closing line has actually been
-- entered (market_data_status='VERIFIED'); returns no row otherwise rather than a fabricated
-- CLV number.
CREATE VIEW IF NOT EXISTS v_clv AS
SELECT
    open_line.run_id,
    open_line.market_type,
    open_line.line_value AS prediction_time_line,
    close_line.line_value AS closing_line,
    close_line.line_value - open_line.line_value AS clv_movement
FROM market_lines open_line
JOIN market_lines close_line
    ON close_line.run_id = open_line.run_id
   AND close_line.market_type = open_line.market_type
   AND close_line.line_stage = 'closing'
   AND close_line.market_data_status = 'VERIFIED'
WHERE open_line.line_stage = 'prediction_time'
  AND open_line.market_data_status = 'VERIFIED';

-- Real dynamic opening/prediction_time/closing classification for raw_market_captures --
-- same real principle as v_clv: never store a tier label that could go stale, compute it fresh.
-- Opening = the real earliest capture for that (game, book, market). Closing = the real latest
-- capture that happened before kickoff. Everything else is prediction_time.
CREATE VIEW IF NOT EXISTS v_ingestion_market_tiers AS
SELECT
    m.*,
    CASE
        WHEN m.captured_at = MIN(m.captured_at) OVER (
            PARTITION BY m.game_id, m.sportsbook, m.market_type
        ) THEN 'opening'
        WHEN m.kickoff_time IS NOT NULL AND m.captured_at < m.kickoff_time
             AND m.captured_at = MAX(m.captured_at) OVER (
                 PARTITION BY m.game_id, m.sportsbook, m.market_type
             ) THEN 'closing'
        ELSE 'prediction_time'
    END AS line_stage
FROM raw_market_captures m;

-- Real prop error -- same pure-function-of-prediction+result pattern as v_prediction_errors,
-- computed fresh every query so a later real result correction never leaves a stale cached
-- error behind.
CREATE VIEW IF NOT EXISTS v_prop_errors AS
SELECT
    pp.prop_id,
    pp.run_id,
    pp.player_name,
    pp.stat_type,
    pp.projected_value,
    pres.actual_value,
    pp.projected_value - pres.actual_value AS prop_error,
    ABS(pp.projected_value - pres.actual_value) AS absolute_prop_error
FROM prop_predictions pp
JOIN prop_results pres ON pres.prop_id = pp.prop_id;
"""


def create_database(db_path: Path | str = DEFAULT_DB_PATH) -> sqlite3.Connection:
    """
    Idempotent -- safe to call against an existing database (CREATE TABLE/VIEW IF NOT EXISTS
    throughout). Returns an open connection with foreign_keys enforcement on (off by default
    in SQLite -- this project wants a real referential-integrity guarantee, not a silent
    orphaned row).
    """
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA_SQL)
    conn.executescript(VIEWS_SQL)
    conn.commit()
    return conn
