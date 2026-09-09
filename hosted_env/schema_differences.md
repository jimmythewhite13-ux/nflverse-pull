# Schema Differences — Original Sketch vs. Real Postgres Design

Every difference below is grounded in the real SQLite structure (`PRAGMA table_info()` output,
captured live against `prediction_audit.sqlite3` — see `schema.sql`'s own inline comments for
the per-table detail), not preference. Real evidence for the source structure this maps: the
full `PRAGMA table_info()` dump for every table below was pulled directly from the live
database as part of this task, not recalled from memory.

## 1. `games.status` split into a separate `game_workflow_status` table

**Original sketch**: a single `status` column directly on `games`.
**Real, built system**: two tables — `games` (identity) and `game_workflow_status` (workflow
state), joined on `game_id`.
**Why the real design is better, not just different**: a Week 1-3 `NOT_PREDICTABLE` game never
needs a "prediction attempt" concept forced into its own identity row. This decoupling is what
let `game_status.py` update status independently and idempotently (monotonic-safe — never
downgrades a game past READY) without ever touching game identity. Kept as two tables in
Postgres.

## 2. Immutability mechanism: `model_status` ENUM, not `is_correction`/`corrects_id`

**Original sketch**: `is_correction BOOLEAN` + `corrects_id INT REFERENCES predictions(id)`.
**Real, built system**: `prediction_runs.model_status CHECK IN ('ACTIVE','SUPERSEDED','VOID')`
— no self-referencing pointer at all.
**Why**: this is the real, already-tested mechanism (`capture_snapshot.py` +
`tests/test_capture_snapshot.py`'s real, passing double-capture test). A correction is just a
new row for the same `game_id` with the old one marked `SUPERSEDED`; "what did this correct" is
answerable with `WHERE game_id = X AND model_status = 'SUPERSEDED' ORDER BY
prediction_timestamp DESC LIMIT 1` — no dedicated column needed. Per the governing task's own
explicit instruction, this is mapped directly, not redesigned.

## 3. `component_contributions` — a real table the original sketch never had

Required for parity with the real, already-proven per-component audit granularity (Step 4 of
the original master spec, and every Pre-Game Snapshot / research phase since). Added as its own
normalized table (one row per named term per run), matching the real SQLite structure exactly.

## 4. `raw_market_captures`: no stored `tier` column

**Original sketch**: `market_lines.tier TEXT CHECK IN ('opening','prediction_time','closing')`
— stored at write time.
**Real, built system**: no `tier` column at all — computed dynamically via
`v_ingestion_market_tiers`, a view using `MIN()`/`MAX() OVER (PARTITION BY ...)`.
**Why**: a stored `closing` tag written before a game's real kickoff would need to be updated
later as more captures arrive before that kickoff — exactly the kind of mutable-derived-fact
this project's "compute fresh, never cache" discipline (already established via
`v_prediction_errors`) exists to avoid. Also documents a real, known caveat carried forward:
a `closing` label for a game that hasn't kicked off yet means "latest capture so far," not
"confirmed final" — this is inherent to the *definition*, not a Postgres-specific bug, and
applies identically in the ported view.

## 5. `raw_market_captures.source` vs. `.sportsbook` — two real, distinct fields

**Original sketch**: one `source TEXT NOT NULL` field, presumably meant as "the sportsbook."
**Real, built system**: `sportsbook` (the real book — draftkings, betmgm, ...) and `source`
(the real DATA PROVIDER — e.g. "The Odds API (api.the-odds-api.com)") are two separate, real
columns. Kept separate in Postgres — collapsing them would lose real information the live agent
already captures correctly.

## 6. Four entirely new tables: the live agent's own ingestion-log layer

`ingestion_runs`, `raw_injury_reports`, `raw_roster_snapshots`, `raw_schedule_checks` — the
original sketch never anticipated a distinct, standalone ingestion-audit layer separate from
the prediction pipeline at all (it predates the automated agent). Added directly, real columns
mapped from live `PRAGMA table_info()` output.

## 7. `results`: no `recorded_at` in the real table — flagged as a real, recommended addition

The real SQLite `results` table has no timestamp column at all (just `game_id`,
`away_final_score`, `home_final_score`). The Postgres design adds `recorded_at TIMESTAMPTZ
DEFAULT now()` as a genuine improvement — **flagged explicitly as new scope, not a silent
migration decision**. Confirm before Track 2 whether this is wanted; if not, drop the column
before deployment.

## 8. `prediction_audit_metrics.log_loss` — included but will be NULL until a real gap is closed

The real `results_and_audit.py` never computes log_loss today (only `margin_error` and
`brier_score`), even though the original design sketch wanted it. The column is included in the
Postgres schema (cheap, and this is a fresh build) but will be `NULL` for every row until the
real SQLite ingestion script is extended to compute it. **This is a known, real gap being
carried forward, not silently closed** — confirm with the user whether extending
`results_and_audit.py` is in scope before or alongside Track 2.

## 9. `model_versions.status`/`promoted_at` — a genuinely NEW capability, not a migration

**Real, important finding**: no structured "which model is live" fact exists anywhere in the
real system today. The real system distinguishes models only by the `MODEL_VERSION` string
literal each script hardcodes (`v35.0-live-production`, `v35.0-hfa-a-selected`, etc.) — there is
no queryable `status` field anywhere real. `model_versions` is being built fresh in Postgres,
not migrated from a proven mechanism. This is exactly the ambiguity Part C's PWA "model version
indicator" screen is designed to finally resolve — worth being explicit that Postgres is where
that resolution actually happens, not something already solved elsewhere waiting to be copied.

## What did NOT change from the original sketch

`sports`, `users` — kept as designed; genuinely new, no real precedent either way, and the
original reasoning (cheap to build now, expensive to retrofit) still holds.
