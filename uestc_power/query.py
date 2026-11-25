from __future__ import annotations

import json
import re
from html import unescape
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path

from playwright.sync_api import TimeoutError as PlaywrightTimeoutError
from playwright.sync_api import sync_playwright

from .config import DATA_DIR, HISTORY_PATH, STATE_PATH, PROFILE_DIR, AppConfig, ensure_dirs
from .auth import automatic_login
from .browser import browser_session, launch_browser as _launch_browser
from .diagnostics import record_event
from .notifier import toast


@dataclass
class QueryResult:
    balance: float
    room: str
    raw_text: str
    checked_at: str
    source: str


def interactive_login(config: AppConfig) -> Path:
    ensure_dirs()
    with sync_playwright() as playwright:
        with browser_session(playwright, headless=False) as context:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(config.portal_url, wait_until="domcontentloaded", timeout=60_000)
            print("请在打开的 Microsoft Edge 里完成学校统一认证登录。")
            input("登录完成并能看到门户首页后，回到这里按 Enter 保存会话...")
            if "/authserver/" in page.url:
                raise RuntimeError("尚未完成学校认证，未覆盖已保存的会话。请完成登录后重试。")
            page.locator('.xz-top-user-box .topuser').first.wait_for(state="visible", timeout=25_000)
            context.storage_state(path=str(STATE_PATH))
            record_event("auth", "manual_authenticated", "手动认证已完成并保存")
    return STATE_PATH


def query_electricity(config: AppConfig, show_browser: bool = False) -> QueryResult:
    if not STATE_PATH.exists() and not (PROFILE_DIR / "Default").exists() and not config.auto_login:
        raise RuntimeError("还没有浏览器登录会话，请先运行：python -m uestc_power login")

    record_event("query", "started")
    try:
        with sync_playwright() as playwright, browser_session(
            playwright, headless=not show_browser and config.headless
        ) as context:
            page = context.pages[0] if context.pages else context.new_page()
            record_event("query", "opening_portal")
            page.goto(config.portal_url, wait_until="domcontentloaded", timeout=60_000)
            page.wait_for_function(
                """() => document.querySelector('.xz-top-user-box .topuser') !== null
                    || location.pathname.includes('/authserver/')""",
                timeout=25_000,
            )
            if "/authserver/" in page.url or page.title() == "统一身份认证平台":
                record_event("auth", "session_expired", "会话失效，准备自动续登")
                automatic_login(page, config)
            else:
                record_event("auth", "session_reused", "已复用现有登录状态")
            page.locator('.xz-top-user-box .topuser').first.wait_for(state="visible", timeout=25_000)
            context.storage_state(path=str(STATE_PATH))
            for attempt in range(2):
                record_event("query", "reading_balance", attempt=attempt + 1)
                _try_open_profile_card(page)
                raw_text = _collect_text(page, config)
                try:
                    result = _parse_result(raw_text, config)
                    break
                except RuntimeError as error:
                    if attempt == 0:
                        page.reload(wait_until="domcontentloaded", timeout=60_000)
                        if "/authserver/" in page.url:
                            raise RuntimeError("登录会话已失效，请运行 python -m uestc_power login。") from None
                        page.locator('.xz-top-user-box .topuser').first.wait_for(state="visible", timeout=25_000)
                        continue
                    debug_paths = _save_debug_snapshot(page, raw_text)
                    raise RuntimeError(f"{error}\n已保存调试快照：{debug_paths}") from error
            context.storage_state(path=str(STATE_PATH))
    except Exception as error:
        record_event("query", "failed", error_type=type(error).__name__)
        raise

    _append_history(result)
    record_event("query", "succeeded", room=result.room, balance=result.balance)
    _notify_if_needed(result, config)
    return result


def _try_open_profile_card(page) -> None:
    if _page_has_balance_text(page):
        return
    selectors = [
        ".xz-top-user-box .topuser",
        ".topuser-name",
        "[class*=header] [class*=user]",
        "[class*=header] [class*=avatar]",
        "[class*=top] [class*=user]",
        "[class*=top] [class*=avatar]",
        ".user",
        ".avatar",
        "[class*=user]",
        "[class*=avatar]",
    ]
    for selector in selectors:
        try:
            element = page.locator(selector).first
            if element.count() == 0:
                continue
            element.hover(timeout=2000)
            for attempt in range(15):
                page.wait_for_timeout(1000)
                if _page_has_balance_text(page):
                    return
            if selector == ".xz-top-user-box .topuser":
                return
        except PlaywrightTimeoutError:
            continue
        except Exception:
            continue

    viewport = page.viewport_size or {"width": 1366, "height": 768}
    hover_points = [
        (viewport["width"] - 160, 70),
        (viewport["width"] - 220, 70),
        (viewport["width"] - 120, 60),
    ]
    for x, y in hover_points:
        try:
            page.mouse.move(x, y)
            page.wait_for_timeout(1200)
            if _page_has_balance_text(page):
                return
        except Exception:
            continue


def _page_has_balance_text(page) -> bool:
    try:
        text = page.locator(".us-tc").first.text_content(timeout=2000) or ""
        return re.search(r"剩余电费[:：]?\s*[¥￥]?\s*\d+(?:\.\d+)?", text) is not None
    except Exception:
        return False


def _collect_text(page, config: AppConfig) -> str:
    chunks: list[str] = []
    for selector in config.custom_selectors.values():
        try:
            text = page.locator(selector).first.inner_text(timeout=2000)
            if text:
                chunks.append(text)
        except Exception:
            pass
    try:
        chunks.append(page.locator("body").inner_text(timeout=5000))
    except Exception:
        chunks.append(page.content())
    try:
        chunks.append(_html_to_text(page.content()))
    except Exception:
        pass
    return "\n".join(chunks)


def _html_to_text(html: str) -> str:
    html = re.sub(r"<(script|style)\b[^>]*>.*?</\1>", " ", html, flags=re.I | re.S)
    html = re.sub(r"<br\s*/?>", "\n", html, flags=re.I)
    html = re.sub(r"</(div|p|span|li|td|th|tr|section|article)>", "\n", html, flags=re.I)
    html = re.sub(r"<[^>]+>", " ", html)
    return unescape(re.sub(r"[ \t\r\f\v]+", " ", html))


def _parse_result(raw_text: str, config: AppConfig) -> QueryResult:
    normalized = re.sub(r"[ \t\r]+", " ", raw_text)
    room = config.room_label
    balance: float | None = None

    for pattern in config.text_patterns:
        match = re.search(pattern, normalized, flags=re.I | re.S)
        if not match:
            continue
        groups = match.groupdict()
        if groups.get("room") and not room:
            room = groups["room"]
        if groups.get("balance"):
            balance = float(groups["balance"])
            break

    if balance is None:
        if re.search(r"剩余电费[:：]?\s*[¥￥]?\s*--", normalized):
            raise RuntimeError("已登录，但学校门户返回的电费余额为 --，未取得有效余额；请稍后重试或手动打开个人卡片确认。")
        raise RuntimeError(
            "已登录，但没有从页面识别到有效的“剩余电费”。可在 config.json 调整 text_patterns/custom_selectors。"
        )

    return QueryResult(
        balance=balance,
        room=room or "未知寝室",
        raw_text=raw_text,
        checked_at=datetime.now().isoformat(timespec="seconds"),
        source=config.portal_url,
    )


def _save_debug_snapshot(page, raw_text: str) -> str:
    ensure_dirs()
    text_path = DATA_DIR / "debug_last_text.txt"
    html_path = DATA_DIR / "debug_last_page.html"
    screenshot_path = DATA_DIR / "debug_last_page.png"
    text_path.write_text(raw_text, encoding="utf-8")
    try:
        html_path.write_text(page.content(), encoding="utf-8")
    except Exception:
        pass
    try:
        page.screenshot(path=str(screenshot_path), full_page=True)
    except Exception:
        pass
    return f"{text_path}, {html_path}, {screenshot_path}"


def _append_history(result: QueryResult) -> None:
    ensure_dirs()
    with HISTORY_PATH.open("a", encoding="utf-8") as file:
        file.write(json.dumps(asdict(result), ensure_ascii=False) + "\n")


def _notify_if_needed(result: QueryResult, config: AppConfig) -> None:
    if config.low_balance_threshold is not None and result.balance <= config.low_balance_threshold:
        if config.notify_on_low_balance:
            toast("宿舍电费提醒", f"{result.room} 剩余电费 ¥{result.balance:.2f}，低于阈值 ¥{config.low_balance_threshold:.2f}")
        return
    if config.notify_on_success:
        toast("宿舍电费查询完成", f"{result.room} 剩余电费 ¥{result.balance:.2f}")
