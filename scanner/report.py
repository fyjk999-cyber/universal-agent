"""Markdown 报告通用组件（任务无关）。

任务只需提供结构化数据，report.py 负责写盘：
  - write_report(task_name, data_dir, md_text) -> Path
  - 同时写 <ts>.md 与 *_latest.md（保留最近一份，方便随时查看）。
"""
from __future__ import annotations

import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Optional

log = logging.getLogger("scanner.report")


def sanitize_filename(ts: str) -> str:
    return re.sub(r"[^\w\-.]+", "_", ts)


def write_report(task_name: str, data_dir: Path, md_text: str, ts: Optional[str] = None) -> Path:
    """写入一次报告；返回时间戳报告路径。"""
    ts = ts or datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    report_dir = data_dir / "reports" / task_name
    report_dir.mkdir(parents=True, exist_ok=True)
    stamped = report_dir / f"{sanitize_filename(ts)}.md"
    stamped.write_text(md_text, encoding="utf-8")
    latest = data_dir / "reports" / f"{task_name}_latest.md"
    latest.write_text(md_text, encoding="utf-8")
    log.info("报告已写入: %s (latest: %s)", stamped, latest)
    return stamped


def read_latest(task_name: str, data_dir: Path) -> Optional[str]:
    latest = data_dir / "reports" / f"{task_name}_latest.md"
    if latest.exists():
        return latest.read_text(encoding="utf-8")
    return None
