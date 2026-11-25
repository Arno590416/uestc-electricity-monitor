# UESTC 宿舍电费自动查询小工具

这是一个 Windows 本地 Python 小工具，用浏览器会话访问 `https://online.uestc.edu.cn/page/`，从门户页面识别“剩余电费”，并支持每日定时查询、登录后自启动查询、配置修改和认证信息接口。

## 构建流程简述

1. 用 Playwright 调用本机 Microsoft Edge，使用 `data/edge_profile/` 中的程序专用用户目录保留登录状态，同时保存 `data/browser_state.json` 会话快照；旧版会话首次使用时自动迁移。
2. 每次查询复用已保存会话，进入门户首页，优先悬停右上角用户名/头像打开个人卡片，并同时解析可见文本与隐藏弹窗 HTML 中的“寝室”和“剩余电费”。
3. 查询结果追加写入 `data/history.jsonl`，同时通过 Windows 通知弹窗提示余额。
4. 每日查询时间保存在 `data/config.json`，用 `schedule set --time HH:mm` 修改。
5. 每日定时通过 Windows 任务计划程序实现；自启动优先写入当前用户 Startup 启动文件夹，失败时自动改用当前用户 `HKCU Run` 注册表启动项。
6. 默认使用 `login` 保存浏览器会话；执行 `auth save` 成功保存凭据后，会在会话失效时自动尝试一次账号密码登录。验证码/二次验证仍需人工完成。

## 安装

在本目录打开 PowerShell：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python -m uestc_power init
```

这个版本优先调用你电脑已有的 Microsoft Edge，不需要执行 `python -m playwright install chromium`。

如果你的 PowerShell 不允许激活虚拟环境，可以先执行：

```powershell
Set-ExecutionPolicy -Scope CurrentUser RemoteSigned
```

## 首次登录

```powershell
python -m uestc_power login
```

Microsoft Edge 打开后，手动登录学校门户。确认能看到首页和个人信息卡片后，回到终端按 Enter，会话会保存到专用用户目录及 `data/browser_state.json`。如果仍在认证页面，程序不会覆盖原有会话。登录和查询不能同时运行，以免浏览器用户目录冲突。

## 立即查询一次

```powershell
python -m uestc_power query
```

如果页面解析失败，显示浏览器调试：

```powershell
python -m uestc_power query --show-browser
```

如果仍失败，程序会保存调试快照到：

- `data/debug_last_text.txt`
- `data/debug_last_page.html`
- `data/debug_last_page.png`

## 修改每日查询时间

```powershell
python -m uestc_power schedule set --time 08:30
python -m uestc_power schedule enable
```

关闭每日查询：

```powershell
python -m uestc_power schedule disable
```

查看状态：

```powershell
python -m uestc_power schedule status
```

每日任务需要单独执行 `schedule enable` 注册，仅修改时间不会创建任务。启用后，任务在当前用户已登录时每天运行；如果电脑睡眠或关闭导致错过计划时间，会在恢复可运行状态后由 Windows 补执行，可能有调度延迟。允许使用电池时运行，不会主动唤醒电脑。修改时间后需再次执行 `schedule enable` 更新任务。

## 自启动开关

登录 Windows 后自动查询一次：

自启动只在登录时执行，从睡眠或合盖状态恢复不会触发；每天自动查询请另外启用每日任务。

```powershell
python -m uestc_power autostart enable
```

这个命令不再使用 `schtasks`。它会优先在当前用户启动文件夹创建 `UESTC-Dorm-Electricity-Monitor.cmd`；如果启动文件夹也拒绝写入，会自动改写当前用户注册表 `HKCU\Software\Microsoft\Windows\CurrentVersion\Run`。

关闭：

```powershell
python -m uestc_power autostart disable
```

查看状态：

```powershell
python -m uestc_power autostart status
```

## 认证信息接口

```powershell
python -m uestc_power auth save --username 你的学号
```

如果安装并可用 `keyring`，密码会写入系统密钥环，同时启用 `auto_login`。密码不会写入配置、日志或 GitHub。后续查询优先复用浏览器会话，失效后只在 `https://idas.uestc.edu.cn` 的学校认证表单中尝试一次账号密码登录；登录成功会更新本地会话。

新版认证页默认显示微信扫码时，脚本会先切换到“账号登录”，再定位可见的账号密码表单，由学校网页自身完成密码处理与提交。学校提供“记住登录”选项时会尝试勾选。专用浏览器目录可以减少重复登录，但不能延长学校规定的会话有效期，也不能保证学校以后更新时永远不需要适配。

首次升级会自动导入原来的会话文件；请在与你的每日任务相同的 Windows 用户下运行程序。不要把 `data/edge_profile/` 上传或复制给别人，它包含认证状态。换电脑时需重新登录并保存认证信息。

遇到验证码、短信验证、二次认证或密码错误，自动登录会停止，需运行 `python -m uestc_power login` 手动完成认证。程序不会反复尝试密码或绕过验证。如果密钥环不可用，则只保存用户名，不启用自动登录。

关闭自动登录（保留已保存的密码）：

```powershell
python -m uestc_power config set auto_login false
```

查询失败时会发出通知，并在自动运行的 `logs/last_run.log` 中记录原因。可以用 `config set notify_on_error false` 关闭失败通知。门户返回 `寝室: -- / 剩余电费: ¥--` 时，表示当前没有拿到有效余额，不会将占位符当成查询结果。

`logs/events.jsonl` 以追加方式记录每次运行的会话复用、自动登录、余额读取和通知调用结果，不记录账号密码或 Cookie。`auth/authenticated` 表示自动认证成功，`auth/verification_required` 表示需要人工验证。`notification/submitted` 仅表示通知进程调用成功，不等于用户已看到或已阅读；`notification/failed` 会记录进程失败或超时。此版本仍使用 Windows 气泡通知，不保证在通知中心保留。

## 可改配置

查看：

```powershell
python -m uestc_power config show
```

常用修改：

```powershell
python -m uestc_power config set low_balance_threshold 20
python -m uestc_power config set notify_on_success true
python -m uestc_power config set room_label 621
```

如果学校页面改版，优先改 `data/config.json` 里的 `text_patterns` 或 `custom_selectors`。

## 文件说明

- `uestc_power/query.py`：打开门户并解析剩余电费。
- `uestc_power/config.py`：配置路径和默认值。
- `uestc_power/scheduler.py`：每日任务计划、启动文件夹和当前用户注册表自启动开关。
- `uestc_power/auth.py`：认证信息保存接口。
- `uestc_power/browser.py`：专用 Edge 用户目录、旧会话迁移和并发保护。
- `uestc_power/diagnostics.py`：运行阶段事件日志。
- `data/config.json`：用户配置。
- `data/history.jsonl`：历史查询记录。
- `logs/last_run.log`：计划任务最近一次运行日志。
- `logs/events.jsonl`：追加保存的登录、查询和通知诊断记录。

## 注意

- 这个工具只用于查询你自己的宿舍电费，不会绕过学校认证。
- 如果统一认证会话过期，重新运行 `python -m uestc_power login`。
- 自启动日志 `logs/last_run.log` 会记录开始时间、查询输出或错误、退出码。`Exit code: 0` 表示成功，非零表示失败；出现登录会话失效提示时需重新登录。
- 如果每日定时的 `schedule enable` 被 `schtasks` 拒绝，可以暂时只使用 `autostart enable`；它走当前用户启动文件夹或 `HKCU Run` 注册表。
