"""Audit Log（§50）— 与系统日志分离.

Logs = 系统运行情况；Audit = 谁/为什么/根据什么/执行了什么/用户是否批准.
不可混为一个文件. Audit 记录只追加（append-only JSONL）.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("ua.audit")


class AuditLog:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "audit.jsonl"

    def record(self, *, actor: str, action: str, reason: str,
               based_on: Optional[Dict[str, Any]] = None,
               approved: Optional[bool] = None,
               result: Optional[Dict[str, Any]] = None,
               task_id: Optional[str] = None) -> Dict[str, Any]:
        """Append one audit entry (§50 六要素)."""
        entry = {
            "ts": datetime.now(timezone.utc).isoformat(),
            "actor": actor,
            "action": action,
            "reason": reason,
            "based_on": based_on or {},
            "approved": approved,
            "result": result or {},
            "task_id": task_id,
        }
        with open(self._file, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(entry, ensure_ascii=False) + "\n")
        return entry

    def entries(self, limit: Optional[int] = None) -> List[Dict[str, Any]]:
        if not self._file.exists():
            return []
        out = []
        for line in self._file.read_text("utf-8").splitlines():
            if line.strip():
                try:
                    out.append(json.loads(line))
                except json.JSONDecodeError:
                    continue
        if limit is not None:
            return out[-limit:]
        return out
