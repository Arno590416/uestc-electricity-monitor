from __future__ import annotations

import os
import base64
import subprocess
from datetime import datetime
from pathlib import Path

from .config import RUNNER_SCRIPT, TASK_NAME, AppConfig


STARTUP_FILE_NAME = "UESTC-Dorm-Electricity-Monitor.cmd"
RUN_REGISTRY_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
RUN_REGISTRY_VALUE = "UESTC-Dorm-Electricity-Monitor"


def write_runner_script() -> None:
    RUNNER_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    content = """$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location -LiteralPath $ProjectRoot
$LogDirectory = Join-Path $ProjectRoot "logs"
New-Item -ItemType Directory -Path $LogDirectory -Force | Out-Null
$LogPath = Join-Path $LogDirectory "last_run.log"
"[$(Get-Date -Format o)] Query started" | Set-Content -LiteralPath $LogPath -Encoding UTF8
$env:PYTHONIOENCODING = "utf-8"
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding

if (Test-Path ".\\.venv\\Scripts\\python.exe") {
  $Python = ".\\.venv\\Scripts\\python.exe"
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
"""
    RUNNER_SCRIPT.write_text(content, encoding="utf-8")


def enable_daily_schedule(config: AppConfig) -> None:
    try:
        schedule_time = datetime.strptime(config.schedule_time, "%H:%M").strftime("%H:%M")
    except ValueError:
        raise ValueError("每日查询时间必须是有效的 HH:mm，例如 08:30。") from None
    write_runner_script()
    arguments = _hidden_powershell_runner(RUNNER_SCRIPT).removeprefix("powershell ").replace("'", "''")
    task_name = TASK_NAME.replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding
$executable = Join-Path $env:SystemRoot 'System32\\WindowsPowerShell\\v1.0\\powershell.exe'
$action = New-ScheduledTaskAction -Execute $executable -Argument '{arguments}'
$trigger = New-ScheduledTaskTrigger -Daily -At '{schedule_time}'
$settings = New-ScheduledTaskSettingsSet -StartWhenAvailable -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -MultipleInstances IgnoreNew -ExecutionTimeLimit (New-TimeSpan -Minutes 5)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName '{task_name}' -Action $action -Trigger $trigger -Settings $settings -Principal $principal -Force | Out-Null
"""
    encoded_script = base64.b64encode(script.encode("utf-16-le")).decode("ascii")
    result = subprocess.run(
        ["powershell", "-NoProfile", "-EncodedCommand", encoded_script],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        encoding="utf-8",
        errors="replace",
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(f"注册每日任务失败：{result.stderr or result.stdout}")


def disable_daily_schedule() -> None:
    _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"], allow_fail=True)


def enable_autostart() -> str:
    write_runner_script()
    startup_file = _startup_file_path()
    command = _hidden_powershell_runner(RUNNER_SCRIPT)
    try:
        startup_file.parent.mkdir(parents=True, exist_ok=True)
        #startup_file.write_text(f"@echo off\r\n{command}\r\n", encoding="utf-8")
        startup_file.write_text(f"@echo off\r\nchcp 65001 >nul\r\n{command}\r\n", encoding="utf-8")
        return f"启动文件夹：{startup_file}"
    except PermissionError:
        _enable_registry_autostart(command)
        return f"注册表当前用户启动项：{RUN_REGISTRY_KEY}\\{RUN_REGISTRY_VALUE}"


def disable_autostart() -> None:
    startup_file = _startup_file_path()
    if startup_file.exists():
        startup_file.unlink()
    _disable_registry_autostart()


def task_status(task_name: str) -> str:
    result = _run_schtasks(["/Query", "/TN", task_name], allow_fail=True, capture=True)
    return result.stdout.strip() if result.returncode == 0 else "未启用"


def autostart_status() -> str:
    startup_file = _startup_file_path()
    if startup_file.exists():
        return f"已启用：{startup_file}"
    registry_result = _query_registry_autostart()
    if registry_result:
        return f"已启用：{registry_result}"
    return "未启用"


def _startup_file_path() -> Path:
    appdata = os.environ.get("APPDATA")
    if not appdata:
        raise RuntimeError("无法定位 APPDATA，不能写入当前用户启动文件夹。")
    return Path(appdata) / "Microsoft" / "Windows" / "Start Menu" / "Programs" / "Startup" / STARTUP_FILE_NAME


def _powershell_runner(script_path: Path) -> str:
    return f'powershell -NoProfile -ExecutionPolicy Bypass -File "{script_path}"'


def _hidden_powershell_runner(script_path: Path) -> str:
    return f'powershell -NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File "{script_path}"'


def _enable_registry_autostart(command: str) -> None:
    result = subprocess.run(
        ["reg", "add", RUN_REGISTRY_KEY, "/v", RUN_REGISTRY_VALUE, "/t", "REG_SZ", "/d", command, "/f"],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr or result.stdout or "写入当前用户启动注册表失败"
        raise RuntimeError(message)


def _disable_registry_autostart() -> None:
    subprocess.run(
        ["reg", "delete", RUN_REGISTRY_KEY, "/v", RUN_REGISTRY_VALUE, "/f"],
        text=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )


def _query_registry_autostart() -> str | None:
    result = subprocess.run(
        ["reg", "query", RUN_REGISTRY_KEY, "/v", RUN_REGISTRY_VALUE],
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        check=False,
    )
    if result.returncode != 0:
        return None
    return f"{RUN_REGISTRY_KEY}\\{RUN_REGISTRY_VALUE}"


def _run_schtasks(args: list[str], allow_fail: bool = False, capture: bool = False):
    result = subprocess.run(
        ["schtasks", *args],
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
        check=False,
    )
    if result.returncode != 0 and not allow_fail:
        message = result.stderr or result.stdout or "schtasks 执行失败"
        raise RuntimeError(message)
    return result
