# nflverse-pull

Pulls NFL game results from [nflverse](https://github.com/nflverse/nflverse-data) and reshapes
them into the exact `Team | Season | Off PPG | Def PPG` format that the **YoY Baseline Engine**
tab (Section 1) of the NFL Prediction Model workbook expects.

## Setup

```bash
uv sync
```

This installs `nfl_data_py` + `pandas` (runtime) and `pytest` + `ruff` (dev), per `pyproject.toml`.

## Usage

```bash
uv run python -m nflverse_pull.pull
```

Produces `team_season_ppg.csv` in the current directory with 2023–2025 data for all 32 teams.
Pass different years by editing the `main()` call at the bottom of `src/nflverse_pull/pull.py`,
or import and call it yourself:

```python
from nflverse_pull.pull import main
main(years=[2022, 2023, 2024, 2025], output_path="team_season_ppg_4yr.csv")
```

Then either:
1. Open the CSV and paste its rows over the sample placeholder rows in the workbook's
   **YoY Baseline Engine → Section 1** table (same column order), or
2. Upload the CSV back to Claude to have it wired into the workbook directly.

## Development

```bash
uv run pytest      # unit tests -- fully offline, no network required
uv run ruff check  # lint
```

The test suite (`tests/test_pull.py`) only exercises `transform_to_team_season()`, the pure
reshaping logic, against small fake DataFrames -- it never calls `fetch_schedules()`, so it
needs no internet access and won't hit nflverse's servers on every CI run.

## Wiring data into the workbook

`nflverse_pull.main` is the single entry point for the pipeline: it pulls fresh PPG
(`pull.py`) and efficiency metrics (`efficiency.py`), and writes them directly into the
workbook's Section 1 input tables (`YoY Baseline Engine` and `Advanced Efficiency
Metrics`) via `update_workbook.py`. Every formula downstream of those two tables
recalculates itself the next time the workbook is opened in Excel.

```bash
uv run python -m nflverse_pull.main "C:\path\to\NFL_Prediction_Model.xlsx"
```

Emailing a results summary is not part of this pipeline -- it's available on demand, not
required. Run `uv run python -m nflverse_pull.email_results` directly if you want that
(see the "Optional: emailed results" section below for setup).

`pull.py` / `.efficiency` also run standalone if you only want a CSV, not a workbook write
(see Usage above).

## Automated scheduled updates

Two Windows Scheduled Tasks run `scripts/run_scheduled_update.ps1`, which calls
`nflverse_pull.main` above and logs the result:

| Task | Schedule |
|---|---|
| `NFLPredictionModel_DailyUpdate` | Every day, 6:00 AM (Pacific) |
| `NFLPredictionModel_SundayUpdate` | Sundays, 9:00 AM (Pacific) |

Inspect or change them with `schtasks /Query /TN "NFLPredictionModel_DailyUpdate" /V` or
via Task Scheduler's GUI. Each run's output is logged to `logs/update_<timestamp>.log`
(gitignored).

## Optional: emailed results

`nflverse_pull.email_results` isn't part of the scheduled/`main.py` pipeline -- run it
yourself, whenever you want a results summary emailed:

```bash
uv run python -m nflverse_pull.email_results
```

It needs a Gmail App Password, set once as a User-scope environment variable -- **run this
yourself**, in your own PowerShell prompt (replace the placeholders; requires 2-Step
Verification enabled on the Google account, then Google Account -> Security -> App
Passwords):

```powershell
[Environment]::SetEnvironmentVariable("NFLVERSE_SMTP_FROM_EMAIL", "you@gmail.com", "User")
[Environment]::SetEnvironmentVariable("NFLVERSE_SMTP_APP_PASSWORD", "xxxxxxxxxxxxxxxx", "User")
```

## Project layout

```
.claude/settings.json                  Claude Code permissions (WebFetch allowlist + uv run pytest/ruff)
pyproject.toml                          uv project + dependency + ruff/pytest config
src/nflverse_pull/pull.py               fetch_schedules() [network] + transform_to_team_season() [pure] + main()
src/nflverse_pull/efficiency.py         fetch_pbp() [network] + compute_raw_efficiency()/compute_league_stats()/
                                         compute_weighted_efficiency() [pure] + main()
src/nflverse_pull/update_workbook.py    writes pull.py + efficiency.py output into the workbook's placeholder tables
src/nflverse_pull/email_results.py      emails a combined PPG + efficiency report via Gmail SMTP
src/nflverse_pull/main.py               single pipeline entry point: calls update_workbook.py
scripts/run_scheduled_update.ps1        calls nflverse_pull.main; entry point for the two Windows Scheduled Tasks
tests/                                   offline unit tests for every pure/transform function above
```

## Note on `.claude/settings.json`

The allowlist covers `uv sync`, `uv run pytest`/`ruff`, and `uv run python -m nflverse_pull.*`
for all five modules (`pull`, `efficiency`, `update_workbook`, `email_results`, `main`), plus
WebFetch for github.com / raw.githubusercontent.com / nflreadr.nflverse.com -- so none of the
commands in this README should prompt for approval.
