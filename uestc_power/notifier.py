from __future__ import annotations

import base64
import subprocess

from .diagnostics import record_event


def toast(title: str, message: str) -> bool:
    safe_title = title.replace("'", "''")
    safe_message = message.replace("'", "''")
    script = f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
$notify = New-Object System.Windows.Forms.NotifyIcon
$notify.Icon = [System.Drawing.SystemIcons]::Information
$notify.BalloonTipTitle = '{safe_title}'
$notify.BalloonTipText = '{safe_message}'
$notify.Visible = $true
$notify.ShowBalloonTip(10000)
Start-Sleep -Seconds 11 
$notify.Dispose()
"""
    try:# 尝试执行通知
        record_event("notification", "attempting", title=title)# 记录尝试发送通知的事件
        encoded_script = base64.b64encode(script.encode("utf-16-le")).decode("ascii")# 将 PowerShell 脚本编码为 Base64，以便在命令行中传递给 PowerShell 解释器
        result = subprocess.run(# 使用 subprocess 模块运行 PowerShell 命令
            ["powershell", "-NoProfile", "-STA", "-WindowStyle", "Hidden", "-EncodedCommand", encoded_script],
            check=False,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=20,# 设置超时时间
        )
        if result.returncode != 0:# 如果 PowerShell 命令返回非零状态码，表示执行失败
            record_event("notification", "failed", "通知进程返回错误", returncode=result.returncode)
            return False
        record_event("notification", "submitted", "已调用系统气泡通知")# 记录通知已提交的事件
        return True
    except (OSError, subprocess.TimeoutExpired) as error:# 捕获 OSError 和超时异常
        record_event("notification", "failed", error_type=type(error).__name__)# 记录通知失败的事件
        return False
