$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$LogDirectory = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$LogPath = Join-Path $LogDirectory "last_run.log"
"[$(Get-Date -Format o)] Query started" | Set-Content -LiteralPath $LogPath -Encoding UTF8
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding

if (Test-Path ".\.venv\Scripts\python.exe") {
  $Python = ".\.venv\Scripts\python.exe"
} else {
  $Python = "python"
}

try {
  "Python: $Python" | Out-File -LiteralPath $LogPath -Append -Encoding UTF8
  $ErrorActionPreference = "Continue"
  & $Python -u -m uestc_power query --json 2>&1 | Out-File -LiteralPath $LogPath -Append -Encoding UTF8
  $QueryExitCode = $LASTEXITCODE
  $ErrorActionPreference = "Stop"
  "[$(Get-Date -Format o)] Exit code: $QueryExitCode" | Out-File -LiteralPath $LogPath -Append -Encoding UTF8
  exit $QueryExitCode
} catch {
  $_ | Out-String | Out-File -LiteralPath $LogPath -Append -Encoding UTF8
  "[$(Get-Date -Format o)] Startup failed" | Out-File -LiteralPath $LogPath -Append -Encoding UTF8
  exit 1
}
