from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any


APP_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = APP_DIR / "data"
LOG_DIR = APP_DIR / "logs"
CONFIG_PATH = DATA_DIR / "config.json"
STATE_PATH = DATA_DIR / "browser_state.json"
HISTORY_PATH = DATA_DIR / "history.jsonl"
RUNNER_SCRIPT = APP_DIR / "scripts" / "run_query.ps1"
TASK_NAME = "UESTC-Dorm-Electricity-Monitor"
AUTOSTART_TASK_NAME = "UESTC-Dorm-Electricity-Monitor-Autostart"


@dataclass
class AppConfig:
    portal_url: str = "https://online.uestc.edu.cn/page/"
    schedule_time: str = "08:30"
    headless: bool = True
    room_label: str = ""
    low_balance_threshold: float | None = 20.0
    notify_on_success: bool = True
    notify_on_low_balance: bool = True
    text_patterns: list[str] = field(
        default_factory=lambda: [
            r"寝室[:：]?\s*(?P<room>[\w\-一-龥]+)\s*剩余电费[:：]?\s*[¥￥]?\s*(?P<balance>\d+(?:\.\d+)?)",
            r"剩余电费[:：]?\s*[¥￥]?\s*(?P<balance>\d+(?:\.\d+)?)",
        ]
    )
    custom_selectors: dict[str, str] = field(default_factory=dict)
    auth_username: str = ""


def ensure_dirs() -> None:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    LOG_DIR.mkdir(parents=True, exist_ok=True)


def load_config() -> AppConfig:
    ensure_dirs()
    if not CONFIG_PATH.exists():
        save_config(AppConfig())
    raw = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    defaults = asdict(AppConfig())
    defaults.update(raw)
    return AppConfig(**defaults)


def save_config(config: AppConfig) -> None:
    ensure_dirs()
    CONFIG_PATH.write_text(
        json.dumps(asdict(config), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def update_config_value(key: str, value: Any) -> AppConfig:
    config = load_config()
    if not hasattr(config, key):
        raise KeyError(f"未知配置项：{key}")
    current = getattr(config, key)
    if isinstance(current, bool):
        value = str(value).strip().lower() in {"1", "true", "yes", "on", "开启"}
    elif isinstance(current, float) or key == "low_balance_threshold":
        value = None if str(value).strip().lower() in {"none", "null", ""} else float(value)
    setattr(config, key, value)
    save_config(config)
    return config
