"""AppiumSkill（P-MOBILE）— iPhone 控制 Skill（SkillProtocol 实现）。

能力映射（IRON RULE 3：Skill = 平台能力，Domain 不知道 Appium）：
  search          → 扫描已安装 app（软件信息）
  detail          → 单 app 信息
  availability    → app 是否已装 / 可启动
  verify          → 操作后验证（如 app 是否已启动）
  health_check    → WDA 健康
  prepare_action  → L2 控制操作边界（launch/tap 等，不 commit 破坏性动作）

高危 execute_action 不在本 Skill（只经 ActionGateway → Policy → Approval）。
"""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

from ...registry.skills.protocol import SkillProtocol
from .transport import MobileTransport

log = logging.getLogger("ua.mobile.skill")


class AppiumSkill(SkillProtocol):
    skill_id: str = "appium.iphone"
    domains: List[str] = ["mobile", "iphone"]

    def __init__(self, transport: Optional[MobileTransport] = None,
                 wda_url: str = "http://127.0.0.1:8100",
                 udid: Optional[str] = None) -> None:
        self.transport = transport or MobileTransport(wda_url=wda_url, udid=udid)
        self._session: Optional[str] = None

    # ---- 会话管理（懒连接） ----
    def _ensure_session(self) -> Optional[str]:
        if self._session:
            return self._session
        sid = self.transport.create_session()
        if sid:
            self._session = sid
        return sid

    def close(self) -> None:
        if self._session:
            self.transport.delete_session(self._session)
            self._session = None

    # ---- SkillProtocol ----
    def search(self, query: Dict[str, Any]) -> List[Dict[str, Any]]:
        """扫描已安装 app（软件信息）。

        query: {"query": "installed_apps"} 或 {}。
        优先 WDA mobile: 扩展；不支持时降级为空（fail-closed）。
        """
        sid = self._ensure_session()
        if not sid:
            return []
        apps = self.transport.list_apps(sid)
        # 归一化输出
        out = []
        for a in apps:
            if isinstance(a, str):
                out.append({"bundleId": a})
            elif isinstance(a, dict):
                out.append({
                    "bundleId": a.get("bundleId") or a.get("bundle_id") or a.get("id", ""),
                    "name": a.get("name", ""),
                    "version": a.get("version", a.get("shortVersion", "")),
                })
        return out

    def detail(self, item_key: str) -> Dict[str, Any]:
        """单 app 信息（bundleId → 详情）。"""
        sid = self._ensure_session()
        apps = self.transport.list_apps(sid) if sid else []
        for a in apps:
            bid = a.get("bundleId") if isinstance(a, dict) else a
            if bid == item_key:
                return {"bundleId": item_key, **a} if isinstance(a, dict) \
                    else {"bundleId": item_key}
        return {"bundleId": item_key, "installed": False,
                "status": "NOT_FOUND"}

    def availability(self, item_key: str) -> Dict[str, Any]:
        """app 是否已装/可启动。"""
        info = self.detail(item_key)
        installed = info.get("installed", True) and info.get("status") != "NOT_FOUND"
        return {"bundleId": item_key, "installed": installed,
                "status": "AVAILABLE" if installed else "NOT_INSTALLED"}

    def verify(self, item_key: str) -> Dict[str, Any]:
        """验证：查询 app 是否在前台/运行。WDA 无直接查询时返回 UNVERIFIED。"""
        return {"bundleId": item_key, "verified": False, "status": "UNVERIFIED",
                "note": "queryAppState via WDA not implemented (P-MOBILE L1)"}

    def health_check(self) -> Dict[str, Any]:
        """WDA 健康。"""
        st = self.transport.status()
        if st.get("status") == "HEALTHY":
            return {"skill_id": self.skill_id, "status": "HEALTHY",
                    "wda_version": (st.get("build") or {}).get("version"),
                    "os": (st.get("os") or {}).get("name"),
                    "os_version": (st.get("os") or {}).get("version")}
        return {"skill_id": self.skill_id, "status": "UNREACHABLE",
                "detail": "WDA not reachable"}

    def prepare_action(self, item_key: str, params: Dict[str, Any]) -> Dict[str, Any]:
        """L2 控制操作边界：launch 等只到「已就绪」，不 commit 破坏性动作。

        返回 PREPARED（可执行）或 PENDING_APPROVAL（需审批）。
        """
        action = params.get("action", "")
        if action in ("launch", "tap", "input"):
            return {"bundleId": item_key, "action": action,
                    "status": "PREPARED",
                    "note": "control action ready; execute via ActionGateway"}
        return {"bundleId": item_key, "action": action,
                "status": "NOT_READY", "reason": f"unsupported action: {action}"}
