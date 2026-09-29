from __future__ import annotations

import subprocess


def toast(title: str, message: str) -> None:
    safe_title = title.replace("'", "''")
    safe_message = message.replace("'", "''")
    script = f"""
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.BalloonTipTitle = '{safe_title}'
$notify.BalloonTipText = '{safe_message}'
$notify.Visible = $true
$notify.ShowBalloonTip(6000)
Start-Sleep -Seconds 7
$notify.Dispose()
"""
    try:
        subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", script],
            check=False,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    except OSError:
        pass
