from __future__ import annotations

import os
import subprocess
from pathlib import Path

from .config import RUNNER_SCRIPT, TASK_NAME, AppConfig


STARTUP_FILE_NAME = "UESTC-Dorm-Electricity-Monitor.cmd"
RUN_REGISTRY_KEY = r"HKCU\Software\Microsoft\Windows\CurrentVersion\Run"
RUN_REGISTRY_VALUE = "UESTC-Dorm-Electricity-Monitor"


def write_runner_script() -> None:
    RUNNER_SCRIPT.parent.mkdir(parents=True, exist_ok=True)
    content = """$ErrorActionPreference = "Stop"
$ProjectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $ProjectRoot

if (Test-Path ".\\.venv\\Scripts\\python.exe") {
  $Python = ".\\.venv\\Scripts\\python.exe"
} else {
  $Python = "python"
}

& $Python -m uestc_power query --json *> ".\\logs\\last_run.log"
"""
    RUNNER_SCRIPT.write_text(content, encoding="utf-8")


def enable_daily_schedule(config: AppConfig) -> None:
    write_runner_script()
    _run_schtasks(
        [
            "/Create",
            "/TN",
            TASK_NAME,
            "/SC",
            "DAILY",
            "/ST",
            config.schedule_time,
            "/TR",
            _powershell_runner(RUNNER_SCRIPT),
            "/F",
        ]
    )


def disable_daily_schedule() -> None:
    _run_schtasks(["/Delete", "/TN", TASK_NAME, "/F"], allow_fail=True)


def enable_autostart() -> str:
    write_runner_script()
    startup_file = _startup_file_path()
    command = _hidden_powershell_runner(RUNNER_SCRIPT)
    try:
        startup_file.parent.mkdir(parents=True, exist_ok=True)
        startup_file.write_text(f"@echo off\r\n{command}\r\n", encoding="utf-8")
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
