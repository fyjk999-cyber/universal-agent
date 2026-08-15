"""Human Approval Inbox (§41 + FR-032) — 统一展示/审批入口.

可以同时展示: 机票购买 / Job申请 / 淘宝订单 / 验证码 / 身份声明.
由 Harness 当前展示，Jarvis 未来接管.
P23（FR-032 / RULE-003）：支持 SQLite 后端（repo 参数）；未提供时保留 JSON 兼容。
"""
from __future__ import annotations

import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("ua.actions.approval")

APPROVAL_TYPES = {"purchase", "job_application", "order", "captcha", "identity"}


class ApprovalInbox:
    """审批箱：request（PENDING 持久化）→ decide（APPROVED/REJECTED）。

    - `repo` 提供时（SqliteApprovalRepository）→ 持久化到 SQLite（RULE-003）
    - 否则回退 JSON 文件（兼容既有测试）
    """

    def __init__(self, data_dir: Optional[Path] = None, repo=None) -> None:
        self.repo = repo
        self.data_dir = Path(data_dir) if data_dir is not None else None
        if self.data_dir is not None:
            self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = (self.data_dir / "approvals.json") if self.data_dir is not None else None
        self._items: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self.repo is not None:
            # SQLite 后端：加载 PENDING（decided 通过 get() 惰性读取）
            for item in self.repo.pending():
                self._items[item["approval_id"]] = item
            return
        if self._file is not None and self._file.exists():
            try:
                self._items = json.loads(self._file.read_text("utf-8"))
            except Exception:  # noqa: BLE001
                log.warning("approvals.json corrupt; starting empty")

    def _persist(self, item: Dict[str, Any]) -> None:
        if self.repo is not None:
            self.repo.request(item)  # upsert
            return
        if self._file is not None:
            self._file.write_text(json.dumps(self._items, ensure_ascii=False, indent=2),
                                  "utf-8")

    def request(self, *, approval_type: str, title: str,
                payload: Optional[Dict[str, Any]] = None,
                task_id: Optional[str] = None) -> Dict[str, Any]:
        """Create an approval request. Never auto-approve (§56)."""
        if approval_type not in APPROVAL_TYPES:
            raise ValueError(f"unknown approval type: {approval_type}")
        item = {
            "approval_id": f"ap_{uuid.uuid4().hex[:12]}",
            "type": approval_type,
            "title": title,
            "payload": payload or {},
            "task_id": task_id,
            "status": "PENDING",
            "decision": None,
            "created_at": datetime.now(timezone.utc).isoformat(),
            "decided_at": None,
        }
        self._items[item["approval_id"]] = item
        self._persist(item)
        return item

    def decide(self, approval_id: str, approved: bool,
               by: str = "human") -> Dict[str, Any]:
        item = self.get(approval_id)
        if item is None:
            raise KeyError(f"approval not found: {approval_id}")
        if item["status"] != "PENDING":
            raise ValueError("approval already decided")
        item["status"] = "APPROVED" if approved else "REJECTED"
        item["decision"] = approved
        item["decided_by"] = by
        item["decided_at"] = datetime.now(timezone.utc).isoformat()
        self._persist(item)
        return item

    def pending(self) -> List[Dict[str, Any]]:
        return [v for v in self._items.values() if v["status"] == "PENDING"]

    def find_by_payload(self, key: str, value: Any,
                        status: Optional[str] = None) -> Optional[Dict[str, Any]]:
        """按 payload 字段查找审批记录（用于 executor 判断 intent 是否已批准）。"""
        for v in self._items.values():
            if v.get("payload", {}).get(key) == value:
                if status is None or v["status"] == status:
                    return v
        return None

    def get(self, approval_id: str) -> Optional[Dict[str, Any]]:
        item = self._items.get(approval_id)
        if item is None and self.repo is not None:
            item = self.repo.find(approval_id)
            if item is not None:
                self._items[approval_id] = item
        return item

    def list_all(self) -> List[Dict[str, Any]]:
        return list(self._items.values())
