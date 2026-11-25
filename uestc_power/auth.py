from __future__ import annotations

import re
from getpass import getpass
from urllib.parse import urljoin, urlsplit

from .config import AppConfig, save_config
from .diagnostics import record_event

SERVICE_NAME = "uestc-electricity-monitor"


def save_username(config: AppConfig, username: str) -> None:
    config.auth_username = username
    save_config(config)


def save_password(username: str, password: str) -> bool:
    try:
        import keyring

        keyring.set_password(SERVICE_NAME, username, password)
        return True
    except Exception:
        return False


def load_password(username: str) -> str | None:
    try:
        import keyring

        return keyring.get_password(SERVICE_NAME, username)
    except Exception:
        return None


def prompt_and_save_credentials(config: AppConfig, username: str | None) -> bool:
    username = username or input("统一认证用户名/学号：").strip()
    password = getpass("统一认证密码（不会明文写入 config.json）：")
    save_username(config, username)
    saved = save_password(username, password)
    if saved:
        config.auto_login = True
        save_config(config)
    return saved


class LoginRequiredError(RuntimeError):
    pass


def _has_verification(page) -> bool:# 检查页面是否存在验证码或二次认证的输入框
    return page.locator(
        'input[name="captcha"]:visible, input[name="dynamicCode"]:visible, '
        'input[autocomplete="one-time-code"]:visible, .geetest_panel:visible, .yidun_panel:visible'
    ).count() > 0


def _select_account_login(page) -> None:
    if page.locator('input[type="password"]:visible').count():
        return
    options = page.locator('a:visible,button:visible,[role="button"]:visible').filter(
        has_text=re.compile(r"^\s*(账号登录|帐号登录|密码登录)\s*$")
    )
    options.first.wait_for(state="visible", timeout=10_000)
    options.first.click(timeout=5000)
    page.locator('input[type="password"]:visible').first.wait_for(state="visible", timeout=10_000)
    record_event("auth", "password_mode", "已从扫码页切换到账号登录")


def automatic_login(page, config: AppConfig) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    manual_message = "请运行 python -m uestc_power login，手动完成统一认证后再查询。"
    if not config.auto_login:
        record_event("auth", "manual_required", "自动登录未开启")
        raise LoginRequiredError(f"登录会话已失效。{manual_message}")
    login_url = urlsplit(page.url)
    if login_url.scheme != "https" or login_url.hostname != "idas.uestc.edu.cn":
        record_event("auth", "blocked_origin", "认证页面域名校验失败")
        raise LoginRequiredError(f"当前不是学校可信的统一认证页面，未填写凭据。{manual_message}")
    submitted = False
    try:
        _select_account_login(page)
        form = page.locator('form:visible:has(input[type="password"]:visible)').first
        form.wait_for(state="visible", timeout=10_000)
        action_url = urlsplit(urljoin(page.url, form.get_attribute("action") or page.url))
        if action_url.scheme != "https" or action_url.hostname != login_url.hostname:
            record_event("auth", "blocked_origin", "认证表单域名校验失败")
            raise LoginRequiredError(f"登录表单地址异常，未填写凭据。{manual_message}")
        if _has_verification(page):
            record_event("auth", "verification_required", "学校要求人工验证，未提交密码")
            raise LoginRequiredError(f"学校要求验证码，需要人工验证。{manual_message}")
        if not config.auth_username:
            record_event("auth", "credentials_missing", "尚未保存用户名")
            raise LoginRequiredError("未保存认证用户名，请先运行 python -m uestc_power auth save。")
        password = load_password(config.auth_username)
        if not password:
            record_event("auth", "credentials_missing", "当前 Windows 用户无法读取已保存的密码")
            raise LoginRequiredError("无法从系统密钥环取得密码，请先运行 python -m uestc_power auth save。")
        form.locator('input[name="username"]:visible').fill(config.auth_username)
        page.wait_for_timeout(800)
        if _has_verification(page):
            record_event("auth", "verification_required", "输入账号后学校要求人工验证")
            raise LoginRequiredError(f"学校要求验证码，需要人工验证。{manual_message}")
        form.locator('input[type="password"]:visible').fill(password)
        remember = form.locator('input[name="rememberMe"]:visible')
        if remember.count():
            try:
                remember.first.check(timeout=1500)
            except PlaywrightTimeoutError:
                record_event("auth", "remember_unavailable", "无法勾选记住登录，继续正常认证")
        record_event("auth", "submitting", "通过学校网页提交一次账号密码认证")
        submitted = True
        page.locator('#login_submit:visible').first.click(timeout=5000)
        page.wait_for_url(
            lambda url: urlsplit(url).hostname == urlsplit(config.portal_url).hostname
            and urlsplit(url).path.startswith("/page"),
            timeout=25_000,
            wait_until="domcontentloaded",
        )
        record_event("auth", "authenticated", "已返回学校门户")
    except PlaywrightTimeoutError:
        if _has_verification(page):
            reason = "学校要求验证码或二次认证"
            status = "verification_required"
        elif re.search(r"密码错误|密码不正确|用户名或密码|账号或密码错误|账号已锁定|密码已过期", page.locator("body").inner_text(timeout=3000)):
            reason = "学校拒绝了账号密码，请更新已保存的认证信息"
            status = "rejected"
        else:
            reason = "学校登录未在时限内完成" if submitted else "新版账号登录表单尚未就绪"
            status = "timeout" if submitted else "layout_changed"
        record_event("auth", status, reason)
        raise LoginRequiredError(
            f"{reason}；本次不再重试密码。{manual_message}"
        ) from None
