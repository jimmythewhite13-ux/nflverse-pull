-- ============================================================================================
-- REAL, DRAFT-ONLY SQL -- DO NOT EXECUTE YET.
-- ============================================================================================
-- apply_epl_findings.md Part B (2026-09-13 explicit user request): "Plan (don't yet execute)
-- the transition to a read-only analyst role for Claude once the system moves into real
-- operation... Do not execute this yet -- draft the real role/permission SQL now, execute once
-- Sept 29's holdout work is complete and the system is genuinely transitioning to steady-state
-- operation, not mid-build."
--
-- Real, current state (confirmed live, 2026-09-13): Claude Code connects as
-- `nflverse_db_pull_user`, the real owner role on this Render-managed Postgres instance
-- (rolsuper=false, rolcreatedb=true) -- full real read/write access. Correct for the current
-- build phase, per the EPL document's own framing; not a mistake to fix now.
--
-- Real plan this file drafts (execute only after Sept 29):
--   - `pipeline_rw` -- used ONLY by scheduled GitHub Actions jobs (prediction_freeze.yml,
--     line_capture.yml, daily_refresh.yml, game_extras_capture.yml, player_props_capture.yml,
--     sync_to_postgres.yml) -- full real read/write, unchanged behavior for those jobs.
--   - `analyst_ro` -- used by Claude Code going forward -- real, strict SELECT only. Claude's
--     future write path to production becomes a pull request (a real code change, reviewed and
--     merged), never a direct database write.
--
-- Real, additional context worth noting (not something this migration needs to add): the
-- existing `predictions_no_delete`/`predictions_no_update` real database RULES already block
-- UPDATE/DELETE on `predictions`/`prediction_runs` regardless of role grants -- this role split
-- is a real, BROADER safety net across every table (not just those two), not a replacement for
-- that existing, narrower protection.
--
-- Real, manual steps this SQL file deliberately does NOT do (outside a SQL script's scope --
-- whoever executes this after Sept 29 must also do these):
--   1. Set a real password for each new role (via a real secrets manager -- `ALTER ROLE
--      pipeline_rw WITH PASSWORD '...'` / same for analyst_ro -- NEVER commit a real password
--      to this file or any other checked-in file).
--   2. Repoint the `NFLVERSE_DB_PULL` GitHub Actions secret to a new `pipeline_rw` connection
--      string.
--   3. Repoint this project's own local `.env` DATABASE_URL (and whatever Claude Code session
--      config references it) to a new `analyst_ro` connection string.
--   4. Run the real confirmation query at the bottom of this file and visually verify
--      `analyst_ro` has zero INSERT/UPDATE/DELETE grants anywhere before relying on it.
-- ============================================================================================

-- 1. Create the two real roles. LOGIN so each can hold its own real connection string;
--    passwords set separately per the manual step above, never inline here.
CREATE ROLE pipeline_rw WITH LOGIN;
CREATE ROLE analyst_ro WITH LOGIN;

-- 2. pipeline_rw: full real read/write on every existing real table, matching this project's
--    current behavior exactly -- this role changes WHO connects as what, not what the
--    scheduled jobs are allowed to do.
GRANT CONNECT ON DATABASE nflverse_db_pull TO pipeline_rw;
GRANT USAGE ON SCHEMA public TO pipeline_rw;
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO pipeline_rw;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO pipeline_rw;
-- Real future-proofing: a table created AFTER this point (by the owner role running a real
-- migration) automatically grants pipeline_rw the same real read/write access, so this file
-- doesn't need re-running on every future schema change.
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO pipeline_rw;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT USAGE, SELECT ON SEQUENCES TO pipeline_rw;

-- 3. analyst_ro: real, strict SELECT-only -- Claude Code's real future access level.
GRANT CONNECT ON DATABASE nflverse_db_pull TO analyst_ro;
GRANT USAGE ON SCHEMA public TO analyst_ro;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO analyst_ro;
ALTER DEFAULT PRIVILEGES IN SCHEMA public
    GRANT SELECT ON TABLES TO analyst_ro;

-- 4. Real, explicit confirmation query -- run this AFTER granting, BEFORE treating the
--    transition as done, and visually confirm analyst_ro shows ONLY 'SELECT' rows.
-- SELECT grantee, table_name, privilege_type
--   FROM information_schema.role_table_grants
--   WHERE grantee IN ('pipeline_rw', 'analyst_ro')
--   ORDER BY grantee, table_name, privilege_type;
