# Hosted Environment — API Contract (Track 1, Part B)

Design only — no real FastAPI service exists yet. This is the contract Track 2, Step 4
implements against the real, deployed Postgres instance.

## Core principle, unchanged from the original design

The frontend never queries the database directly. Every real data access goes through this API.

## Endpoints — confirmed against the real, refined schema

```
GET  /sports
GET  /sports/{sport}/games?week=N
GET  /sports/{sport}/games/{game_id}
GET  /sports/{sport}/model-versions
```

All four endpoints from the original sketch are confirmed real and sufficient against the
refined schema — no change needed to the list itself. The 5th, example-only endpoint from the
original sketch (`/standings/sos-check`) is dropped here: it was illustrative, not a real,
requested feature, and adding a placeholder route just to have one risks exactly the kind of
"looks built, isn't real" gap this project's discipline exists to catch. Add a real
research-facing endpoint if and when a real research candidate actually needs one.

### `GET /sports`
Returns every row in `sports`. Real, static, single row today (`NFL`).

### `GET /sports/{sport}/games?week=N`
Returns real games for the given week — `games` joined with `game_workflow_status` (status +
reason), and, where an ACTIVE prediction exists, the real `predictions` row too. A
`NOT_PREDICTABLE` game returns its real `status_reason`, never an empty/missing prediction
field silently standing in for "no prediction attempted."

### `GET /sports/{sport}/games/{game_id}`
One real game's full picture: identity (`games`), workflow status
(`game_workflow_status`), the ACTIVE prediction if one exists (`prediction_runs` +
`predictions` + `component_contributions`), real market data
(`raw_market_captures`/`v_ingestion_market_tiers`), the real result if known (`results`), and
real audit metrics if AUDITED (`prediction_audit_metrics`).

### `GET /sports/{sport}/model-versions`
Returns every row in `model_versions` for that sport, including real `status`/`promoted_at`.
This is the endpoint the PWA's model-version indicator (Part C) reads — the single, unambiguous
source of "what's live right now."

## Critical governance boundary — written into the contract, not left as an implementation detail

**There is no `POST`, `PUT`, `PATCH`, or `DELETE` route anywhere in this API's surface.** The
entire contract above is `GET`-only. This is a stronger, simpler guarantee than "the boundary is
enforced in code" — there is no code path to enforce, because there is no mutating route to
misuse. Concretely, none of the following are reachable through this API, under any real
endpoint, present or future, without a explicit, separate design change reviewed against this
exact document:

- `model_versions.status` or `.promoted_at` — promotion stays a manual, out-of-band action (a
  real, deliberate `UPDATE` run directly against Postgres by a human), never something the API
  surface can reach.
- Any `predictions` row's `projected_margin`/`home_win_probability`/etc. — enforced twice over:
  no mutating route exists, AND the real database-level `predictions_no_update`/
  `predictions_no_delete` rules (schema.sql) reject a write even if one somehow reached the
  table directly.
- Any `component_contributions` row — same double enforcement.

**Real verification this holds, required by Track 2 Step 4** (cannot be done yet — no real
service exists): attempt, in a safe test context, to reach `model_versions.status` or a
prediction's value through the deployed API and confirm the attempt fails because no such route
exists — not because it exists but returns an error. The distinction matters: a route that
exists and rejects a bad request is weaker evidence than a route that was never built.

## Response shape — real, honest fields, no fabricated defaults

Every response mirrors the real schema's own nullability. A game with no ACTIVE prediction yet
returns `"prediction": null`, never a fabricated zero-value prediction object. A market capture
with `market_data_status = 'MISSING'` is returned as such, not omitted or silently treated as
zero. This matches the project-wide "never invent a value to complete a row" discipline already
established for the SQLite ingestion layer.
