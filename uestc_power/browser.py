from __future__ import annotations

import json
import os
from contextlib import contextmanager
from pathlib import Path

from .config import PROFILE_DIR, STATE_PATH, ensure_dirs
from .diagnostics import record_event


def _find_edge_path() -> Path | None:
    for environment_name in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA"):
        root = os.environ.get(environment_name)
        if root:
            candidate = Path(root) / "Microsoft" / "Edge" / "Application" / "msedge.exe"
            if candidate.exists():
                return candidate
    return None


def _browser_options(headless: bool) -> dict:
    options = {"headless": headless}
    executable = _find_edge_path()
    if executable:
        options["executable_path"] = str(executable)
    else:
        options["channel"] = "msedge"
    return options


def launch_browser(playwright, headless: bool):
    return playwright.chromium.launch(**_browser_options(headless))


@contextmanager
def browser_session(playwright, headless: bool):
    import msvcrt

    ensure_dirs()
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    with (PROFILE_DIR / "session.lock").open("a+b") as lock_file:
        if lock_file.tell() == 0:
            lock_file.write(b"0")
            lock_file.flush()
        lock_file.seek(0)
        try:
            msvcrt.locking(lock_file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            raise RuntimeError("另一个登录或查询正在使用专用 Edge 会话，请等待它结束后重试。") from None
        context = None
        try:
            first_launch = not (PROFILE_DIR / "Default").exists()
            context = playwright.chromium.launch_persistent_context(
                str(PROFILE_DIR), **_browser_options(headless)
            )
            if first_launch and STATE_PATH.exists():
                state = json.loads(STATE_PATH.read_text(encoding="utf-8"))
                context.add_cookies(state.get("cookies", []))
                origins = json.dumps(state.get("origins", []), ensure_ascii=True)
                context.add_init_script(
                    "for (const item of " + origins + ") {"
                    "if (location.origin === item.origin) {"
                    "for (const entry of item.localStorage || []) {"
                    "localStorage.setItem(entry.name, entry.value);}}}"
                )
                record_event("session", "imported", "已迁移原浏览器会话")
            record_event("session", "opened", "使用程序专用 Edge 用户目录")
            yield context
        finally:
            try:
                if context is not None:
                    context.close()
            finally:
                lock_file.seek(0)
                msvcrt.locking(lock_file.fileno(), msvcrt.LK_UNLCK, 1)
