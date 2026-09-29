$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (Test-Path ".\.venv\Scripts\python.exe") {
  $Python = ".\.venv\Scripts\python.exe"
} else {
  $Python = "python"
}

& $Python -m uestc_power query --json *> ".\logs\last_run.log"
