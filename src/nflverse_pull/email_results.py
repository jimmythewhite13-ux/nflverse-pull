"""
Emails a summary of the latest nflverse pull (Off/Def PPG + efficiency metrics, all 32
teams, pooled across seasons) as a CSV attachment via Gmail SMTP. Used by
scripts/run_scheduled_update.ps1 after each automated workbook update.

Requires two environment variables, set once on this machine (User scope) -- this module
never stores, prints, or otherwise handles the password itself, only reads it from the
environment at send time:

    NFLVERSE_SMTP_FROM_EMAIL     the Gmail address sending the report
    NFLVERSE_SMTP_APP_PASSWORD   a 16-character Gmail App Password for that address
                                  (Google Account -> Security -> 2-Step Verification ->
                                  App Passwords -- requires 2-Step Verification to be on;
                                  a regular account password will NOT work here)

Set them yourself, once, in a PowerShell prompt (replace the placeholders):

    [Environment]::SetEnvironmentVariable("NFLVERSE_SMTP_FROM_EMAIL", "you@gmail.com", "User")
    [Environment]::SetEnvironmentVariable("NFLVERSE_SMTP_APP_PASSWORD", "xxxxxxxxxxxxxxxx", "User")

New PowerShell windows (and Scheduled Tasks, which start a fresh process) pick up User-scope
environment variables automatically -- no restart needed beyond opening a new window/task run.
"""
from __future__ import annotations

import os
import smtplib
from email.message import EmailMessage

import pandas as pd

from nflverse_pull.efficiency import compute_raw_efficiency, compute_weighted_efficiency, fetch_pbp
from nflverse_pull.pull import fetch_schedules, transform_to_team_season

TO_EMAIL = "jimmythewhite13@gmail.com"
SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 465

EFFICIENCY_RAW_COLS = ["epa_off", "epa_def", "success_off", "success_def", "nya_off", "nya_def"]


def combine_ppg_and_efficiency(
    ppg: pd.DataFrame, raw_eff: pd.DataFrame, weighted_eff: pd.DataFrame
) -> pd.DataFrame:
    """
    Pure function. Merges pull.transform_to_team_season()'s pooled per-team PPG output
    with efficiency.py's raw and weighted outputs into one row per team -- the same shape
    as the report CSV emailed after each scheduled run.
    """
    ppg_by_team = ppg.drop(columns=["Season"]) if "Season" in ppg.columns else ppg
    eff = weighted_eff[["Team", "Weighted Efficiency Adjustment", "PROE"]].merge(
        raw_eff[["Team", *EFFICIENCY_RAW_COLS]], on="Team"
    )
    return ppg_by_team.merge(eff, on="Team").sort_values("Team").reset_index(drop=True)


def build_report_csv(years: list[int] | None = None) -> tuple[str, pd.DataFrame]:
    """Pulls fresh nflverse data and returns (csv_text, combined_dataframe)."""
    years = years or [2023, 2024, 2025]

    sched = fetch_schedules(years)
    combined_sched = sched.copy()
    combined_sched["season"] = f"{years[0]}-{years[-1]} combined"
    ppg = transform_to_team_season(combined_sched)

    pbp = fetch_pbp(years)
    raw = compute_raw_efficiency(pbp)
    weighted = compute_weighted_efficiency(raw)

    out = combine_ppg_and_efficiency(ppg, raw, weighted)
    return out.to_csv(index=False), out


def send_report_email(csv_text: str, row_count: int) -> None:
    """Sends the report via Gmail SMTP. Raises RuntimeError if credentials aren't set."""
    from_email = os.environ.get("NFLVERSE_SMTP_FROM_EMAIL")
    app_password = os.environ.get("NFLVERSE_SMTP_APP_PASSWORD")
    if not from_email or not app_password:
        raise RuntimeError(
            "NFLVERSE_SMTP_FROM_EMAIL and NFLVERSE_SMTP_APP_PASSWORD must both be set as "
            "User-scope environment variables to send the automated report email -- see "
            "this module's docstring for the one-time setup command."
        )

    msg = EmailMessage()
    msg["Subject"] = "NFL Prediction Model -- Automated Data Refresh"
    msg["From"] = from_email
    msg["To"] = TO_EMAIL
    msg.set_content(
        f"Automated refresh complete: {row_count} teams updated (2023-2025 pooled).\n\n"
        "Off/Def PPG, Weighted Efficiency Adjustment, PROE, and raw EPA/Success Rate/NY-A "
        "are attached as team_full_ratings.csv. The workbook itself has also been updated "
        "in place on this machine."
    )
    msg.add_attachment(
        csv_text.encode("utf-8"), maintype="text", subtype="csv", filename="team_full_ratings.csv"
    )

    with smtplib.SMTP_SSL(SMTP_HOST, SMTP_PORT) as server:
        server.login(from_email, app_password)
        server.send_message(msg)


def main() -> None:
    csv_text, out = build_report_csv()
    send_report_email(csv_text, len(out))
    print(f"Emailed report for {len(out)} teams to {TO_EMAIL}.")


if __name__ == "__main__":
    main()
