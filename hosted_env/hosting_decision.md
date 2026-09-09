# Hosted Environment — Hosting Decision (Track 1, Part D)

Real, current (2026) pricing, cross-verified against two independent sources rather than
recalled from memory. Evaluated specifically against this project's real use case: one real
user today, low traffic, a small Postgres instance + a small FastAPI service, real possibility
of more users later — not a generic platform comparison.

## Real, current pricing

| Platform | Compute (small API) | Managed Postgres | Free tier |
|---|---|---|---|
| **Render** | Starter $7/mo (always-on), Standard $25/mo | Basic ~$6/mo compute + $0.30/GB storage | Yes — 750 free instance-hours/mo, but spins down after 15 min idle |
| **Railway** | Hobby $5/mo + usage (vCPU/RAM/egress) | One-click, usage-based, no separate base fee | None |
| **Fly.io** | Per-second billed Machines, no flat base tier | Separate managed product, **$38/mo minimum**, single region | None |

## Real reasoning for this specific use case

**Fly.io is a poor fit here, not just a different option.** Its entire value proposition is
global edge deployment across regions — genuinely not needed for one user in one place. Its
real managed Postgres minimum ($38/mo) is roughly 4-6x the other two options' realistic total
cost for a small database, for a capability (multi-region) this project doesn't use.

**Railway has the best real developer experience** (one-click Postgres, zero config) but no
free tier — real cost from day one, and usage-based billing makes budgeting slightly less
predictable at hobby scale, though genuinely cheap in practice for this size of workload.

**Render is the recommended choice.** Real reasoning:
- A genuine free tier exists to validate the whole stack at zero cost before committing spend —
  directly useful given Track 2 hasn't even started yet.
- The free tier's 15-minute spin-down (a real UX cost — cold starts on a PWA) is a real, known,
  cheap-to-fix limitation: moving to Starter ($7/mo) removes it entirely, a low-stakes upgrade
  path rather than a re-architecture.
- Realistic total cost at this project's actual scale: Starter ($7/mo) + Basic Postgres
  (~$6-10/mo depending on storage) ≈ **$13-17/mo** — cheaper than Fly.io's Postgres alone, and
  comparable to Railway's likely real usage-based total.
- Standard, unmodified Postgres + a standard Docker/buildpack-deployed FastAPI service — nothing
  Render-proprietary the schema or API code would need reworking to leave.

## Real migration-risk note

Lock-in risk is low across all three regardless of which is picked: `schema.sql` is
vendor-neutral standard SQL (verified via a real, standalone Postgres parser — no
platform-specific extensions), and a standard FastAPI service moves between any of these three
platforms via a normal `pg_dump`/redeploy, not a rewrite. The one real thing to avoid, on any
platform: don't lean on that platform's own proprietary internal networking or config format in
ways that would be awkward to replicate elsewhere — a plain `DATABASE_URL` environment variable
and standard Docker/buildpack deployment keeps this project portable regardless of which is
chosen now.

## Sources

- [Railway vs Fly.io (2026): Pricing & Platform Comparison](https://render.com/articles/railway-vs-fly-io)
- [Render vs Railway vs Fly.io: Pricing Compared (2026) — DEV Community](https://dev.to/pavel-hostim/render-vs-railway-vs-flyio-pricing-compared-2026-2e5p)
