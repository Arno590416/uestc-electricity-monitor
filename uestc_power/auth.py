from __future__ import annotations

from getpass import getpass
from urllib.parse import urljoin, urlsplit

from .config import AppConfig, save_config

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


def automatic_login(page, config: AppConfig) -> None:
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    manual_message = "请运行 python -m uestc_power login，手动完成统一认证后再查询。"
    if not config.auto_login:
        raise RuntimeError(f"登录会话已失效。{manual_message}")
    login_url = urlsplit(page.url)
    if login_url.scheme != "https" or login_url.hostname != "idas.uestc.edu.cn":
        raise RuntimeError(f"当前不是学校可信的统一认证页面，未填写凭据。{manual_message}")
    form = page.locator('form#pwdFromId:visible').first
    try:
        form.wait_for(state="visible", timeout=10_000)
        action_url = urlsplit(urljoin(page.url, form.get_attribute("action") or page.url))
        if action_url.scheme != "https" or action_url.hostname != login_url.hostname:
            raise RuntimeError(f"登录表单地址异常，未填写凭据。{manual_message}")
        captcha = form.locator('input[name="captcha"]:visible')
        if captcha.count():
            raise RuntimeError(f"学校要求验证码，需要人工验证。{manual_message}")
        if not config.auth_username:
            raise RuntimeError("未保存认证用户名，请先运行 python -m uestc_power auth save。")
        password = load_password(config.auth_username)
        if not password:
            raise RuntimeError("无法从系统密钥环取得密码，请先运行 python -m uestc_power auth save。")
        form.locator('input[name="username"]:visible').fill(config.auth_username)
        page.wait_for_timeout(800)
        if captcha.count():
            raise RuntimeError(f"学校要求验证码，需要人工验证。{manual_message}")
        form.locator('input[type="password"]:visible').fill(password)
        page.locator('#login_submit:visible').first.click(timeout=5000)
        page.wait_for_url(
            lambda url: urlsplit(url).hostname == urlsplit(config.portal_url).hostname
            and urlsplit(url).path.startswith("/page"),
            timeout=25_000,
            wait_until="domcontentloaded",
        )
    except PlaywrightTimeoutError:
        raise RuntimeError(
            f"自动登录未完成，可能需要验证码、二次认证或更新密码；本次不再重试。{manual_message}"
        ) from None
