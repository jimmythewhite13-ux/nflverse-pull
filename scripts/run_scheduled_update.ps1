<#
.SYNOPSIS
    Runs nflverse_pull.update_workbook against the NFL Prediction Model workbook, then
    emails a results summary via nflverse_pull.email_results, and logs both steps.
    Invoked by the "NFLPredictionModel_DailyUpdate" and "NFLPredictionModel_SundayUpdate"
    Windows Scheduled Tasks -- see README.md for the schedule and how to inspect/change it.

.NOTES
    Scheduled Tasks run with a minimal environment (no user PATH), so this script rebuilds
    PATH from the machine+user environment variables before calling `uv`, the same way the
    interactive setup in this project does. The email step needs NFLVERSE_SMTP_FROM_EMAIL
    and NFLVERSE_SMTP_APP_PASSWORD set as User-scope environment variables (see
    src/nflverse_pull/email_results.py) -- if they aren't set, the workbook still updates
    and the email step just logs why it was skipped, rather than failing the whole run.
#>

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
$WorkbookPath = "C:\Users\smp_p\Downloads\NFL_Prediction_Model_2.xlsx"
$LogDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("update_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("PATH", "User")
$env:PYTHONPATH = "src"

Set-Location $ProjectDir

"=== Run started $(Get-Date) ===" | Tee-Object -FilePath $LogFile -Append
try {
    & uv run python -m nflverse_pull.update_workbook $WorkbookPath 2>&1 |
        Tee-Object -FilePath $LogFile -Append
    "=== Workbook update completed successfully $(Get-Date) ===" |
        Tee-Object -FilePath $LogFile -Append
} catch {
    "=== Workbook update FAILED $(Get-Date): $_ ===" | Tee-Object -FilePath $LogFile -Append
    throw
}

try {
    & uv run python -m nflverse_pull.email_results 2>&1 | Tee-Object -FilePath $LogFile -Append
    "=== Email step completed $(Get-Date) ===" | Tee-Object -FilePath $LogFile -Append
} catch {
    # Non-fatal: the workbook is already updated at this point. A missing/expired app
    # password shouldn't make Task Scheduler report the whole run as failed.
    "=== Email step FAILED (workbook was still updated) $(Get-Date): $_ ===" |
        Tee-Object -FilePath $LogFile -Append
}
