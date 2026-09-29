# UESTC 宿舍电费自动查询小工具

这是一个 Windows 本地 Python 小工具，用浏览器会话访问 `https://online.uestc.edu.cn/page/`，从门户页面识别“剩余电费”，并支持每日定时查询、登录后自启动查询、配置修改和认证信息接口。

## 构建流程简述

1. 用 Playwright 调用本机 Microsoft Edge 打开学校门户，首次手动完成统一认证，并把浏览器会话保存到 `data/browser_state.json`。
2. 每次查询复用已保存会话，进入门户首页，优先悬停右上角用户名/头像打开个人卡片，并同时解析可见文本与隐藏弹窗 HTML 中的“寝室”和“剩余电费”。
3. 查询结果追加写入 `data/history.jsonl`，同时通过 Windows 通知弹窗提示余额。
4. 每日查询时间保存在 `data/config.json`，用 `schedule set --time HH:mm` 修改。
5. 每日定时通过 Windows 任务计划程序实现；自启动优先写入当前用户 Startup 启动文件夹，失败时自动改用当前用户 `HKCU Run` 注册表启动项。
6. 认证信息接口预留为 `auth save`；推荐实际使用 `login` 保存浏览器会话，因为学校统一认证可能有验证码/二次验证。

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

Microsoft Edge 打开后，手动登录学校门户。确认能看到首页和个人信息卡片后，回到终端按 Enter，会话会保存到 `data/browser_state.json`。

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

## 自启动开关

登录 Windows 后自动查询一次：

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

如果安装并可用 `keyring`，密码会写入系统密钥环；否则只保存用户名。学校门户有验证码或 SSO 跳转时，仍建议使用 `login` 保存浏览器会话。

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
- `data/config.json`：用户配置。
- `data/history.jsonl`：历史查询记录。
- `logs/last_run.log`：计划任务最近一次运行日志。

## 注意

- 这个工具只用于查询你自己的宿舍电费，不会绕过学校认证。
- 如果统一认证会话过期，重新运行 `python -m uestc_power login`。
- 如果每日定时的 `schedule enable` 被 `schtasks` 拒绝，可以暂时只使用 `autostart enable`；它走当前用户启动文件夹或 `HKCU Run` 注册表。
