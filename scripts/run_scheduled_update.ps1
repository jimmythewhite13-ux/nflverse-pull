<#
.SYNOPSIS
    Runs the nflverse_pull.main pipeline (updates the workbook's Section 1 input tables)
    and logs it. Invoked by the "NFLPredictionModel_DailyUpdate" and
    "NFLPredictionModel_SundayUpdate" Windows Scheduled Tasks -- see README.md for the
    schedule and how to inspect/change it.

.NOTES
    Scheduled Tasks run with a minimal environment (no user PATH), so this script rebuilds
    PATH from the machine+user environment variables before calling `uv`, the same way the
    interactive setup in this project does. Emailing a results summary is not part of this
    pipeline -- run nflverse_pull.email_results directly if you want that on demand.
#>

$ErrorActionPreference = "Stop"

$ProjectDir = Split-Path -Parent $PSScriptRoot
$WorkbookPath = "C:\Users\smp_p\Downloads\NFL_Prediction_Model.xlsx"
$LogDir = Join-Path $ProjectDir "logs"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$LogFile = Join-Path $LogDir ("update_{0}.log" -f (Get-Date -Format "yyyyMMdd_HHmmss"))

$env:PATH = [System.Environment]::GetEnvironmentVariable("PATH", "Machine") + ";" +
            [System.Environment]::GetEnvironmentVariable("PATH", "User")

Set-Location $ProjectDir

"=== Run started $(Get-Date) ===" | Tee-Object -FilePath $LogFile -Append
try {
    & uv run python -m nflverse_pull.main $WorkbookPath 2>&1 | Tee-Object -FilePath $LogFile -Append
    "=== Run completed successfully $(Get-Date) ===" | Tee-Object -FilePath $LogFile -Append
} catch {
    "=== Run FAILED $(Get-Date): $_ ===" | Tee-Object -FilePath $LogFile -Append
    throw
}
