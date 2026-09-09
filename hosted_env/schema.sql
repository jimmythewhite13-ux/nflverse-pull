-- Hosted Environment — Track 1, Part A: Real Postgres schema
--
-- Refined against the ACTUAL real SQLite structure (prediction_audit.sqlite3), confirmed via
-- direct PRAGMA table_info() against the live database, not guessed from memory or the original
-- sketch (hosted_environment_architecture.md). See schema_differences.md alongside this file
-- for every place this differs from that original sketch and why.
--
-- This file is DESIGN ONLY. It has never been run against a real Postgres instance -- that is
-- explicitly Track 2, Step 1, gated on Step 3/4's real results (first possible 2026-09-29).

-- ============================================================================================
-- Genuinely new tables (did not exist in any form in the real SQLite implementation)
-- ============================================================================================

-- Ready for hockey/basketball later; only 'NFL' exists as a real row today. Kept from the
-- original sketch unchanged -- this is a real, deliberate structural choice, not something the
-- SQLite implementation ever needed (single-sport so far) but genuinely cheap to add now.
CREATE TABLE sports (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,        -- 'NFL', later 'NHL', 'NBA'
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE users (
    id          SERIAL PRIMARY KEY,
    email       TEXT NOT NULL UNIQUE,
    access_tier TEXT NOT NULL DEFAULT 'owner',
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Real, honest note: this table's `status`/`promoted_at` concept does NOT exist anywhere in the
-- real SQLite implementation today. The real system distinguishes "which model ran" only by the
-- MODEL_VERSION string literal each script hardcodes (e.g. 'v35.0-live-production',
-- 'v35.0-hfa-a-selected') -- there is no structured, queryable "this one is PRODUCTION" fact
-- anywhere real yet. This table is a genuinely NEW capability, not a migration of an existing
-- mechanism -- flagged so nobody mistakes it for "already proven, just moving house."
CREATE TABLE model_versions (
    id           SERIAL PRIMARY KEY,
    sport_id     INT NOT NULL REFERENCES sports(id),
    version_name TEXT NOT NULL,             -- e.g. 'v35.0-live-production', matches the real
                                             -- MODEL_VERSION strings already in use
    git_tag      TEXT,                      -- e.g. 'v35-audit-passed-hfa-fix', where applicable
    status       TEXT NOT NULL DEFAULT 'RESEARCH'
                 CHECK (status IN ('RESEARCH', 'PRODUCTION', 'DEPRECATED')),
    promoted_at  TIMESTAMPTZ,               -- NULL until a human deliberately promotes it --
                                             -- HFA-A stays NULL here until Phase 11 (or explicit
                                             -- sign-off) says otherwise; the real production
                                             -- champion (v35.0-live-production) is the only real
                                             -- candidate for PROMOTED status as of this writing
    notes        TEXT,
    UNIQUE (sport_id, version_name)
);

-- ============================================================================================
-- Games: maps the real `games` table, plus the real, SEPARATE `game_workflow_status` table --
-- kept as two tables, not merged into one `games.status` column the way the original sketch
-- had it. Real reason this is better, not just different: a NOT_PREDICTABLE (Weeks 1-3) game
-- never needs a "prediction attempt" concept forced into its own identity row, and this
-- decoupling is exactly what let game_status.py update status independently and idempotently
-- without ever touching game identity. Confirmed via real PRAGMA table_info(games) and
-- PRAGMA table_info(game_workflow_status).
-- ============================================================================================

CREATE TABLE games (
    id                SERIAL PRIMARY KEY,
    sport_id          INT NOT NULL REFERENCES sports(id),
    game_id           TEXT NOT NULL UNIQUE,   -- real format: YYYY_WW_AWAY_HOME (abbreviations
                                               -- for the live agent's own real games; NOTE: a
                                               -- real, pre-existing Part A dataset also uses
                                               -- full team names for the SAME season number --
                                               -- see schema_differences.md's own note on this)
    season            INT NOT NULL,
    week              INT NOT NULL,
    game_date         DATE,
    kickoff_time      TIMESTAMPTZ,
    away_team         TEXT NOT NULL,
    home_team         TEXT NOT NULL,
    neutral_site      BOOLEAN NOT NULL DEFAULT FALSE,
    stadium           TEXT,
    surface           TEXT,
    timezone          TEXT
);

CREATE TABLE game_workflow_status (
    game_id       TEXT PRIMARY KEY REFERENCES games(game_id),
    status        TEXT NOT NULL CHECK (status IN (
                      'PENDING', 'READY', 'PREDICTED', 'COMPLETED', 'AUDITED',
                      'NOT_PREDICTABLE', 'BLOCKED'
                  )),
    status_reason TEXT,
    updated_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================================
-- Predictions: maps the real, ALREADY-TESTED immutability mechanism directly -- model_status
-- ENUM (ACTIVE/SUPERSEDED/VOID), NOT the original sketch's is_correction/corrects_id design.
-- Real reason for the change: the real, proven mechanism (write.py + capture_snapshot.py,
-- covered by a real passing test) never needs an explicit "this row corrects that row" pointer
-- -- a correction is just a new row for the same game_id with the old one marked SUPERSEDED;
-- "what did this correct" is answerable by a real query
-- (WHERE game_id = X AND model_status = 'SUPERSEDED' ORDER BY prediction_timestamp DESC LIMIT 1)
-- without a dedicated self-referencing column. Do not reintroduce is_correction/corrects_id --
-- it would be a real, unproven redesign of a mechanism that already works.
-- ============================================================================================

CREATE TABLE prediction_runs (
    id                    SERIAL PRIMARY KEY,
    model_version_id      INT NOT NULL REFERENCES model_versions(id),
    game_id               TEXT NOT NULL REFERENCES games(game_id),
    prediction_timestamp  TIMESTAMPTZ NOT NULL,
    data_cutoff_timestamp TIMESTAMPTZ,
    data_version          TEXT,
    model_status          TEXT NOT NULL DEFAULT 'ACTIVE'
                          CHECK (model_status IN ('ACTIVE', 'SUPERSEDED', 'VOID'))
);
CREATE INDEX idx_prediction_runs_game ON prediction_runs(game_id);
CREATE INDEX idx_prediction_runs_active ON prediction_runs(game_id, model_status)
    WHERE model_status = 'ACTIVE';

CREATE TABLE predictions (
    run_id                INT PRIMARY KEY REFERENCES prediction_runs(id),
    away_projected_points NUMERIC NOT NULL,
    home_projected_points NUMERIC NOT NULL,
    projected_margin      NUMERIC NOT NULL,
    projected_total       NUMERIC NOT NULL,
    home_win_probability  NUMERIC NOT NULL,
    away_win_probability  NUMERIC NOT NULL,
    confidence            NUMERIC
);
-- Real, database-level immutability -- not just application-code discipline. Confirmed this is
-- the correct real Postgres mechanism for what write.py's own docstring already established in
-- SQLite by convention alone (SQLite has no equivalent rule/trigger primitive this simple).
CREATE RULE predictions_no_update AS ON UPDATE TO predictions DO INSTEAD NOTHING;
CREATE RULE predictions_no_delete AS ON DELETE TO predictions DO INSTEAD NOTHING;

-- Real table the original sketch never had at all -- required for parity with the real,
-- already-proven per-component audit granularity (Step 4 of the original 15-step master spec,
-- and every real Pre-Game Snapshot / research phase built on top of it since).
CREATE TABLE component_contributions (
    run_id             INT NOT NULL REFERENCES prediction_runs(id),
    component_name     TEXT NOT NULL,
    contribution_value NUMERIC NOT NULL,
    side               TEXT NOT NULL CHECK (side IN ('HOME', 'AWAY', 'SHARED')),
    PRIMARY KEY (run_id, component_name, side)
);
-- Real immutability here too -- a component_contributions row is written once alongside its
-- real prediction and never touched again, same real discipline.
CREATE RULE component_contributions_no_update AS ON UPDATE TO component_contributions
    DO INSTEAD NOTHING;
CREATE RULE component_contributions_no_delete AS ON DELETE TO component_contributions
    DO INSTEAD NOTHING;

-- ============================================================================================
-- Results and audit metrics
-- ============================================================================================

CREATE TABLE results (
    game_id          TEXT PRIMARY KEY REFERENCES games(game_id),
    away_final_score INT NOT NULL,
    home_final_score INT NOT NULL,
    -- Real, recommended ADDITION over the real SQLite table (which has no timestamp at all) --
    -- flagged as a genuine improvement, not a silent scope change. Confirm before Track 2.
    recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE prediction_audit_metrics (
    run_id        INT PRIMARY KEY REFERENCES prediction_runs(id),
    margin_error  NUMERIC NOT NULL,
    brier_score   NUMERIC NOT NULL,
    -- Real, honest gap carried forward from SQLite, not silently fixed here: results_and_audit.py
    -- never computes log_loss today, even though the original design sketch wanted it. Column
    -- included now (cheap, and Postgres is being newly built) but will be NULL until the real
    -- ingestion script is extended to compute it -- confirm with the user before assuming this
    -- is in scope for this migration.
    log_loss      NUMERIC,
    clv_movement  NUMERIC,
    computed_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ============================================================================================
-- Live agent tables -- ALL genuinely new; the original sketch never anticipated a distinct
-- ingestion-log layer separate from the prediction pipeline at all. Mapped directly from real
-- PRAGMA table_info() output.
-- ============================================================================================

CREATE TABLE ingestion_runs (
    id             SERIAL PRIMARY KEY,
    job_name       TEXT NOT NULL,
    run_timestamp  TIMESTAMPTZ NOT NULL,
    status         TEXT NOT NULL CHECK (status IN ('SUCCESS', 'MISSING', 'FAILURE', 'SKIPPED')),
    source         TEXT,
    rows_written   INT NOT NULL DEFAULT 0,
    detail         TEXT
);
CREATE INDEX idx_ingestion_runs_job ON ingestion_runs(job_name, run_timestamp);

CREATE TABLE raw_injury_reports (
    id              SERIAL PRIMARY KEY,
    ingestion_id    INT NOT NULL REFERENCES ingestion_runs(id),
    season          INT NOT NULL,
    week            INT,
    team            TEXT NOT NULL,
    player_name     TEXT NOT NULL,
    position        TEXT,
    report_status   TEXT,
    practice_status TEXT,
    pulled_at       TIMESTAMPTZ NOT NULL,
    source          TEXT NOT NULL
);

CREATE TABLE raw_roster_snapshots (
    id            SERIAL PRIMARY KEY,
    ingestion_id  INT NOT NULL REFERENCES ingestion_runs(id),
    season        INT NOT NULL,
    team          TEXT NOT NULL,
    player_name   TEXT NOT NULL,
    position      TEXT,
    depth_rank    INT,
    roster_status TEXT,
    pulled_at     TIMESTAMPTZ NOT NULL,
    source        TEXT NOT NULL
);

CREATE TABLE raw_schedule_checks (
    id              SERIAL PRIMARY KEY,
    ingestion_id    INT NOT NULL REFERENCES ingestion_runs(id),
    game_id         TEXT NOT NULL,
    season          INT NOT NULL,
    week            INT NOT NULL,
    home_team       TEXT NOT NULL,
    away_team       TEXT NOT NULL,
    kickoff_time    TIMESTAMPTZ,
    change_detected BOOLEAN NOT NULL DEFAULT FALSE,
    change_detail   TEXT,
    checked_at      TIMESTAMPTZ NOT NULL,
    source          TEXT NOT NULL
);

-- Real, deliberate design choice carried forward unchanged: NO stored `tier` column, unlike the
-- original sketch's `market_lines.tier`. The real, proven SQLite implementation computes tier
-- dynamically via a view specifically because a stored 'closing' tag written before a game's
-- real kickoff would need to be updated later as more captures arrive -- exactly the kind of
-- mutable-derived-fact this project's whole "compute fresh, never cache" discipline exists to
-- avoid (see v_prediction_errors' own real precedent). Do not add a stored tier column.
CREATE TABLE raw_market_captures (
    id                 SERIAL PRIMARY KEY,
    ingestion_id       INT NOT NULL REFERENCES ingestion_runs(id),
    game_id            TEXT NOT NULL,
    sportsbook         TEXT NOT NULL,      -- the real book (draftkings, betmgm, ...)
    market_type        TEXT NOT NULL CHECK (market_type IN ('spread', 'total', 'moneyline')),
    line_value         NUMERIC,
    odds               NUMERIC,
    captured_at        TIMESTAMPTZ NOT NULL,
    kickoff_time       TIMESTAMPTZ,
    source             TEXT NOT NULL,      -- the real DATA PROVIDER (e.g. "The Odds API"),
                                            -- a REAL, DISTINCT concept from `sportsbook` above
                                            -- -- the original sketch's single `source` field
                                            -- conflated these two; kept separate here to match
                                            -- what the real implementation actually needed
    market_data_status TEXT NOT NULL DEFAULT 'MISSING'
                        CHECK (market_data_status IN ('VERIFIED', 'UNVERIFIED', 'MISSING'))
);
CREATE INDEX idx_raw_market_game ON raw_market_captures(game_id, sportsbook, market_type);

-- Real, dynamic tier classification -- direct Postgres port of v_ingestion_market_tiers'own
-- real window-function logic (Postgres supports the same OVER (PARTITION BY ... ) syntax
-- SQLite does; no rewrite needed beyond the CREATE VIEW dialect itself).
CREATE VIEW v_ingestion_market_tiers AS
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

-- Real, pure-function-of-predictions+results error view -- same real "compute fresh, never
-- cache" principle as v_ingestion_market_tiers above, direct port of the real SQLite view.
CREATE VIEW v_prediction_errors AS
SELECT
    p.run_id,
    pr.game_id,
    p.projected_margin,
    (r.home_final_score - r.away_final_score) AS actual_margin,
    p.projected_margin - (r.home_final_score - r.away_final_score) AS margin_error,
    ABS(p.projected_margin - (r.home_final_score - r.away_final_score)) AS absolute_margin_error,
    CASE WHEN (p.projected_margin > 0) = (r.home_final_score > r.away_final_score)
         THEN TRUE ELSE FALSE END AS winner_correct
FROM predictions p
JOIN prediction_runs pr ON pr.id = p.run_id
JOIN results r ON r.game_id = pr.game_id;
