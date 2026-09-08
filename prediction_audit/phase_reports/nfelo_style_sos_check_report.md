# nfelo-style Market-Derived SOS — Real Correlation Screen

**What this is**: a cheap, narrow correlation check on one candidate signal, per your explicit
scope — NOT a new SOS feature build, NOT a Phase 4 re-run (already complete, 8 variants, all
REJECTED). NOT graduated through Phase 9's criteria based on this alone.

## Real data source

Each team's real, verified **2025 preseason win-total line** — the point number a sportsbook
posted before the season (e.g., Buffalo Bills 12.5, Cleveland Browns 5.5) — fetched
reproducibly from the Wayback Machine's real 2025-09-01 snapshot of VegasInsider's win-totals
page (captured 8 days before that season's real Week 1 kickoff, a genuine preseason projection).
All 32 real teams, extracted programmatically from the archived page's raw HTML, not
transcribed by hand.

**Real, honest limitation on the price-adjustment step**: genuine two-sided Over/Under pricing
for this market was not recoverable. Checked three ways: VegasInsider's raw HTML (confirmed
directly, not assumed — only the Over-side price exists anywhere in the page's data model, the
"+" icon is an affiliate deeplink out, not a toggle), SportsbookReview (one-sided editorial
picks only, never a full two-sided table), and DraftKings' own archived page (a real navigation
category for "Wins" exists, but the actual odds table is client-rendered via API calls that
never survived static archiving — confirmed by inspecting the archived page's real text content,
which contains only articles, no odds). This means the proxy uses the **raw posted line**, not a
de-vigged/price-adjusted value — flagged as a real, identified next step, not silently faked.
No de-vig sample calculation is shown for this reason, per your own "report honestly, don't
fabricate" instruction.

## The proxy, precisely

For each team: the average real preseason win-total line of that team's own 17 real 2025
opponents (a fixed, per-team value for the whole season, since a preseason line doesn't update
in-season — no walk-forward complexity needed for this specific input).

## Real, computed correlation coefficients (n=224 real 2025 games, 0.6 concern threshold)

| Existing metric | r |
|---|--:|
| Base Team Quality | **+0.110** |
| Expected Win Total (model's own real SUM-of-win-probability) | **-0.068** |
| EPA/Play (Off) | **-0.150** |
| Success Rate (Off) | **-0.245** |
| NY/A (Off) | **-0.184** |

**None exceed the 0.6 concern threshold.** All five are well under it — the highest magnitude is
0.245 (Success Rate).

## Real, honest read

This confirms the structural distinction held up empirically, not just by construction: a
signal built from real preseason MARKET pricing correlates genuinely weakly with every real
team-PERFORMANCE metric already in the model, including the model's own Expected Win Total
(itself a real, in-season-informed aggregate of the model's own win probabilities) and Base
Team Quality (the model's dominant real contributor). This is a materially different profile
from every one of Phase 4's 8 already-rejected variants, several of which exceeded 0.6 against
these same real metrics.

**What this does NOT establish**: low correlation is necessary, not sufficient. Per your own
explicit instruction, no backtest was run — this signal has zero real evidence yet that it
would improve out-of-sample predictions, only that it isn't redundant with what's already there.
A real Phase-4-style backtest is the honest next step if this is worth pursuing further, and
building the price-adjustment step properly (real two-sided pricing, likely requiring a paid
odds-data provider rather than free scraping) would need to happen before any such candidate
could reach Phase 9's graduation criteria.

## What was NOT done, per your explicit "what not to do"

- No SOS feature built, wired into any tab, or graduated.
- No full nfelo recursive schedule-solver attempted (not justified — this first-pass proxy is
  the real deliverable).
- Low correlation was not treated as validation of anything beyond "not obviously redundant."
