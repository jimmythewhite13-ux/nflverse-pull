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

## Project layout

```
.claude/settings.json        Claude Code permissions (WebFetch allowlist + uv run pytest/ruff)
pyproject.toml                uv project + dependency + ruff/pytest config
src/nflverse_pull/pull.py     fetch_schedules() [network] + transform_to_team_season() [pure] + main()
tests/test_pull.py            offline unit tests for the transform logic
```

## Note on `.claude/settings.json`

The current allowlist covers `uv run pytest` and `uv run ruff` only, plus WebFetch for
github.com / raw.githubusercontent.com / nflreadr.nflverse.com (useful if you ask Claude Code to
consult nflverse docs directly). Running the actual pull (`uv sync`, `uv run python -m ...`) will
still prompt for approval under this config. Add these two entries if you want the full pull to
run without prompts too:

```json
"Bash(uv sync:*)",
"Bash(uv run python -m nflverse_pull.pull:*)"
```
