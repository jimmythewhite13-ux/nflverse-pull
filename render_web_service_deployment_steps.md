# Render Web Service deployment -- real steps for you to run

Real scope: deploy `hosted_env/api/main.py` (the read-only FastAPI service + PWA static files)
as its own, separate Render "Web Service" -- distinct from the already-deployed Postgres
instance (`nflverse_db_pull`). This is the last piece needed for `sunday_live_test_target.md`'s
real screenshot evidence. I can't do this step myself -- it requires your Render dashboard.

## Prerequisite: push to GitHub first

Render deploys from a GitHub repo. Once the pending local commits are pushed (I'll confirm this
separately once the current background reconstruction finishes and it's safe to sync git), this
repo's `main` branch will have everything Render needs: `hosted_env/api/main.py`,
`hosted_env/api/requirements.txt`, `hosted_env/api/static/`.

## Steps (Render dashboard)

1. **New -> Web Service** (not "Static Site" -- this serves a real API, not just static files).
2. **Connect repository**: this repo (`nflverse-pull`), branch `main`.
3. **Root Directory**: leave blank (repo root) -- `main.py` resolves its own static folder by
   absolute path, and the module import string below assumes repo root as the working directory.
4. **Runtime**: Python 3.
5. **Build Command**:
   ```
   pip install -r hosted_env/api/requirements.txt
   ```
6. **Start Command**:
   ```
   uvicorn hosted_env.api.main:app --host 0.0.0.0 --port $PORT
   ```
7. **Instance type**: the free tier is fine for this real test -- read-only API, no background
   jobs, low traffic.
8. **Environment variable** (Environment tab, set directly on this Web Service -- this does NOT
   inherit from the GitHub Actions secret `NFLVERSE_DB_PULL` or your local `.env`, both of which
   live in different places):
   - Key: `DATABASE_URL`
   - Value: if this Web Service ends up in the **same Render region** as the `nflverse_db_pull`
     Postgres instance, use its **Internal Database URL** (faster, doesn't leave Render's
     network) -- find it on the Postgres instance's own dashboard page, "Connections" section.
     Otherwise use the **External Database URL** (same value already in your local `.env`).
9. **Create Web Service** and wait for the first real deploy to finish.
10. Once live, Render gives you a real `https://<something>.onrender.com` URL. Open it in a
    phone or desktop browser -- you should see the real PWA (sport selector, this week's real
    games, model-version banner) pulling from the real, live Postgres data.

## What to send back once deployed

- The real `https://*.onrender.com` URL.
- A real screenshot of it loading on your phone (or any browser) -- this is the actual required
  evidence for `sunday_live_test_target.md`'s "build/test Saturday, confirm Sunday" target.

## Real, honest limitation this will show

Every game right now will show `NOT_PREDICTABLE` (weeks 1-3) or `READY` (weeks 4+, meaning the
workflow allows a prediction once the real gates are met -- not that one exists yet). No game
will show a real prediction number until Phase 11 begins producing real, frozen predictions
(gated at 2026-09-29/~10-01 as already established) -- this is the correct, honest behavior,
not a bug.
