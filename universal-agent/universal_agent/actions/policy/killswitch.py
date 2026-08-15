"""Kill Switch（§66）— 全局急停。

一旦触发，所有真实执行动作立即拒绝，直到人工显式解除。
设计为进程内单例 + 持久化（重启后仍保持 killed 状态）。
P23（RULE-003）：支持 SQLite 后端（repo 参数）；未提供时保留 JSON 兼容。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("ua.actions.killswitch")

#: 持久化键
_STATE_KEY = "state"


class KillSwitch:
    def __init__(self, state_path: Optional[Path] = None, repo=None) -> None:
        self.state_path = state_path
        self.repo = repo  # SqliteKvRepository(table="killswitch")；RULE-003
        self._killed = False
        self._reason = ""
        self._killed_at: Optional[str] = None
        self._load()

    def _load(self) -> None:
        data: Optional[dict] = None
        if self.repo is not None:
            data = self.repo.get(_STATE_KEY)
        elif self.state_path is not None and self.state_path.exists():
            try:
                data = json.loads(self.state_path.read_text("utf-8"))
            except Exception:  # noqa: BLE001
                data = None
        if data:
            self._killed = data.get("killed", False)
            self._reason = data.get("reason", "")
            self._killed_at = data.get("killed_at")

    def _persist(self) -> None:
        payload = {"killed": self._killed, "reason": self._reason,
                   "killed_at": self._killed_at}
        if self.repo is not None:
            self.repo.put(_STATE_KEY, payload)
            return
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps(payload), "utf-8")

    def kill(self, reason: str) -> None:
        """触发急停（人工/审计事件调用）。"""
        self._killed = True
        self._reason = reason
        self._killed_at = datetime.now(timezone.utc).isoformat()
        log.critical("KILL SWITCH TRIPPED: %s", reason)
        self._persist()

    def disarm(self) -> None:
        """解除急停（必须人工显式执行）。"""
        self._killed = False
        self._reason = ""
        self._killed_at = None
        self._persist()

    def is_killed(self) -> bool:
        return self._killed

    def status(self) -> dict:
        return {"killed": self._killed, "reason": self._reason,
                "killed_at": self._killed_at}

    def assert_alive(self) -> None:
        """执行前调用；急停状态下任何执行动作抛 KillSwitchTripped。"""
        if self._killed:
            raise KillSwitchTripped(
                f"kill switch active: {self._reason or 'manual trip'}")


class KillSwitchTripped(RuntimeError):
    pass
