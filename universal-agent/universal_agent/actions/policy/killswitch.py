"""Kill Switch（§66）— 全局急停。

一旦触发，所有真实执行动作立即拒绝，直到人工显式解除。
设计为进程内单例 + 文件持久化（重启后仍保持 killed 状态）。
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

log = logging.getLogger("ua.actions.killswitch")


class KillSwitch:
    def __init__(self, state_path: Optional[Path] = None) -> None:
        self.state_path = state_path
        self._killed = False
        self._reason = ""
        self._killed_at: Optional[str] = None
        if state_path is not None and state_path.exists():
            try:
                data = json.loads(state_path.read_text("utf-8"))
                self._killed = data.get("killed", False)
                self._reason = data.get("reason", "")
                self._killed_at = data.get("killed_at")
            except Exception:  # noqa: BLE001
                pass

    def _persist(self) -> None:
        if self.state_path is None:
            return
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        self.state_path.write_text(json.dumps({
            "killed": self._killed, "reason": self._reason,
            "killed_at": self._killed_at,
        }), "utf-8")

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
