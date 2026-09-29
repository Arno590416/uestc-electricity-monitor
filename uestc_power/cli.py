from __future__ import annotations

import argparse
import json
import sys
from dataclasses import asdict

from .auth import prompt_and_save_credentials
from .config import TASK_NAME, load_config, save_config, update_config_value
from .scheduler import (
    autostart_status,
    disable_autostart,
    disable_daily_schedule,
    enable_autostart,
    enable_daily_schedule,
    task_status,
)


def main() -> None:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if hasattr(sys.stderr, "reconfigure"):
        sys.stderr.reconfigure(encoding="utf-8")

    parser = argparse.ArgumentParser(prog="uestc-power", description="UESTC 宿舍剩余电费自动查询工具")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("init", help="生成默认配置")

    login_parser = subparsers.add_parser("login", help="打开浏览器登录并保存会话")
    login_parser.add_argument("--url", help="覆盖门户地址")

    auth_parser = subparsers.add_parser("auth", help="保存/更改认证信息接口")
    auth_subparsers = auth_parser.add_subparsers(dest="auth_command", required=True)
    auth_save_parser = auth_subparsers.add_parser("save", help="保存用户名和密码到系统密钥环")
    auth_save_parser.add_argument("--username")

    query_parser = subparsers.add_parser("query", help="立即查询一次剩余电费")
    query_parser.add_argument("--show-browser", action="store_true", help="显示浏览器窗口，便于调试")
    query_parser.add_argument("--json", action="store_true", help="输出 JSON")

    config_parser = subparsers.add_parser("config", help="查看或修改配置")
    config_subparsers = config_parser.add_subparsers(dest="config_command", required=True)
    config_subparsers.add_parser("show", help="显示当前配置")
    config_set_parser = config_subparsers.add_parser("set", help="设置配置项")
    config_set_parser.add_argument("key")
    config_set_parser.add_argument("value", nargs="?", default="")

    schedule_parser = subparsers.add_parser("schedule", help="每日定时查询开关")
    schedule_subparsers = schedule_parser.add_subparsers(dest="schedule_command", required=True)
    schedule_set_parser = schedule_subparsers.add_parser("set", help="设置每日查询时间，例如 08:30")
    schedule_set_parser.add_argument("--time", required=True)
    schedule_subparsers.add_parser("enable", help="启用每日定时查询")
    schedule_subparsers.add_parser("disable", help="关闭每日定时查询")
    schedule_subparsers.add_parser("status", help="查看每日定时查询状态")

    autostart_parser = subparsers.add_parser("autostart", help="开机/登录后自动查询开关")
    autostart_subparsers = autostart_parser.add_subparsers(dest="autostart_command", required=True)
    autostart_subparsers.add_parser("enable", help="启用登录后自动查询")
    autostart_subparsers.add_parser("disable", help="关闭登录后自动查询")
    autostart_subparsers.add_parser("status", help="查看自启动状态")

    args = parser.parse_args()
    config = load_config()

    if args.command == "init":
        save_config(config)
        print("已生成默认配置。")
        return

    if args.command == "login":
        from .query import interactive_login

        if args.url:
            config.portal_url = args.url
            save_config(config)
        state_path = interactive_login(config)
        print(f"登录会话已保存：{state_path}")
        return

    if args.command == "auth":
        ok = prompt_and_save_credentials(config, args.username)
        if ok:
            print("认证信息已保存到系统密钥环/keyring。")
        else:
            print("已保存用户名；密码未保存。建议安装 keyring 或使用 login 保存浏览器会话。")
        return

    if args.command == "query":
        from .query import query_electricity

        result = query_electricity(config, show_browser=args.show_browser)
        if args.json:
            print(json.dumps(asdict(result), ensure_ascii=False, indent=2))
        else:
            print(f"{result.checked_at}｜{result.room}｜剩余电费：¥{result.balance:.2f}")
        return

    if args.command == "config":
        if args.config_command == "show":
            print(json.dumps(asdict(config), ensure_ascii=False, indent=2))
        elif args.config_command == "set":
            updated = update_config_value(args.key, args.value)
            print(f"已更新 {args.key} = {getattr(updated, args.key)!r}")
        return

    if args.command == "schedule":
        if args.schedule_command == "set":
            updated = update_config_value("schedule_time", args.time)
            print(f"每日查询时间已设为 {updated.schedule_time}")
        elif args.schedule_command == "enable":
            enable_daily_schedule(config)
            print("已启用每日定时查询。")
        elif args.schedule_command == "disable":
            disable_daily_schedule()
            print("已关闭每日定时查询。")
        elif args.schedule_command == "status":
            print(task_status(TASK_NAME))
        return

    if args.command == "autostart":
        if args.autostart_command == "enable":
            location = enable_autostart()
            print(f"已启用登录后自动查询：{location}")
        elif args.autostart_command == "disable":
            disable_autostart()
            print("已关闭登录后自动查询。")
        elif args.autostart_command == "status":
            print(autostart_status())
