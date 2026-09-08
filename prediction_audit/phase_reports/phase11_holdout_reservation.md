# Phase 11 — Untouched Holdout Reservation

**Filed: 2026-09-07, before the 2026 NFL regular season has kicked off.** This timestamp
matters: the reservation below is made *before* any real 2026 game has been played, so its
choice cannot have been influenced — even inadvertently — by what would make the Phase
10-selected model (v35 + HFA-A revised) look good.

## Why 2024 and 2025 are both disqualified

- **2025**: every real week (4-18) has already been used for training (4-10) or
  testing/selection (11-18) across Phases 2-10, including the Phase 10 selection itself.
- **2024**: was used this same session for a *secondary* check of whether the Phase 10 ranking
  holds up in a second real season (`phase8_2024_reconstruction.py`) — even though that check
  used a degraded (non-production) OL Index and never changed the Phase 10 decision, having
  looked at 2024 at all disqualifies it from serving as a genuinely untouched holdout too. This
  is stated explicitly rather than glossed over.

## Real, verified state of 2026 as of this filing

Checked live against `nflverse_pull.pull.fetch_schedules([2026])`:
- 272 real REG games scheduled.
- **0 real games have a final score yet** — every game is still in the future.
- Earliest real kickoff: **2026-09-09** (2 days after this filing).
- Latest scheduled real kickoff: 2027-01-10.

This means 2026 is currently the only real season with **zero** possible contamination — not
one game's real result exists anywhere yet for any decision in this program to have used.

## The reservation

**The entire 2026 real regular season is reserved, as of this filing, as Phase 11's untouched
holdout.** Specifically:

- Real weeks 4-18 of the 2026 REG season (the same real structural scope Phase 1 established —
  weeks 1-3 cannot run the full 22-input formula at all, walk-forward, since no current-season
  QB/RB role data exists that early; this is a genuine data-availability fact, not a choice made
  to favor any outcome).
- OL Index's FTN-coverage constraint does **not** block 2026: target_season - 3 = 2023 ≥ 2022,
  so the full, real, unmodified production formula (not the 2024 secondary check's degraded
  path) can run for 2026 once its real data exists.
- The Phase 10-selected model — v35 baseline with HFA-A (no team-specific HFA) applied, exactly
  as specified, nothing else changed — is the model that will be evaluated. No other candidate.

## What happens between now and the actual evaluation

- No 2026 data will be used for any further feature engineering, coefficient estimation,
  calibration fitting, or model-selection decision between now and the single Phase 11
  evaluation run.
- The evaluation itself cannot happen yet — this is a real, honest "pending" status, not a
  fabricated placeholder result. It requires real 2026 games to actually be played.
- When run, it will be run **exactly once**, on the full real weeks-4-18 set then available, with
  no adjustment to the model based on the result and no re-run if the result disappoints — per
  the kickoff document's own explicit requirement.

## Status

**PENDING — reserved, not yet evaluated.** Real evaluation requires real 2026 game results,
starting 2026-09-09. Phases 12 and 13 proceed now since neither requires the holdout to already
be evaluated — only that the selected model is fully specified (Phase 12) and correctly
implemented (Phase 13), with Phase 11's evaluation run against that implementation once real
2026 data exists.
