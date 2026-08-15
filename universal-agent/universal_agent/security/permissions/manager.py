"""PermissionManager（P14）— 用户/角色权限检查。

默认拒绝（fail-closed）：未 grant 的操作一律拒绝。
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict, List, Optional, Set


class PermissionManager:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "permissions.json"
        self._perms: Dict[str, Set[str]] = {}
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                raw = json.loads(self._file.read_text("utf-8"))
                self._perms = {k: set(v) for k, v in raw.items()}
            except Exception:  # noqa: BLE001
                self._perms = {}

    def _save(self) -> None:
        self._file.write_text(
            json.dumps({k: sorted(v) for k, v in self._perms.items()}, indent=2),
            "utf-8")

    def grant(self, principal: str, permission: str) -> None:
        self._perms.setdefault(principal, set()).add(permission)
        self._save()

    def revoke(self, principal: str, permission: str) -> None:
        if principal in self._perms:
            self._perms[principal].discard(permission)
            self._save()

    def check(self, principal: str, permission: str) -> bool:
        """默认拒绝：未授权 → False。"""
        return permission in self._perms.get(principal, set())
