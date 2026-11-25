from __future__ import annotations

import json
import sys
from datetime import datetime

from .config import LOG_DIR, ensure_dirs


def record_event(stage: str, status: str, detail: str = "", **fields) -> None:
    entry = {"time": datetime.now().isoformat(timespec="seconds"), "stage": stage, "status": status}
    if detail:
        entry["detail"] = detail
    entry.update(fields)
    try:
        ensure_dirs()
        with (LOG_DIR / "events.jsonl").open("a", encoding="utf-8") as event_file:
            event_file.write(json.dumps(entry, ensure_ascii=False) + "\n")
    except OSError:
        print("无法写入运行事件日志，请检查 logs 目录权限或磁盘空间。", file=sys.stderr)
