from __future__ import annotations

from getpass import getpass

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
    return save_password(username, password)
