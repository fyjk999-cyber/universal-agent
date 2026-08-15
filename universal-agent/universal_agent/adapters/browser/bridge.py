"""BrowserSessionBridge — 人机协同官方会话桥（FR-060-062 蓝图 + RULE-007 默认拒绝）。

背景（借自本地"旅程智选"项目的 chrome-bridge 设计，2026-07 验证）：
- 12306/航司官网普遍有验证码/登录墙，SPAC §33 禁止绕过反爬或代填验证码。
- 合规路径 = 用户在**自己的 Chrome** 里保持登录态，本桥只负责在**白名单官方域名**
  上打开页面，绝不读取 Cookie / 密码 / 表单 / 网页内容，也不处理支付。

本模块 = 服务端一侧的审批闸门：
- `request_open(url)`：默认拒绝——URL 必须 https + 白名单域名，否则直接 DENIED；
  合法则生成 PENDING_APPROVAL 请求。
- `decide_approval(request_id, approved)`：用户显式批准后返回 OPEN_OFFICIAL 指令。
- 全部动作写审计日志（可持久化到 SQLite，RULE-010 可追溯）。

配套：`chrome_bridge/` 目录内的 MV3 扩展（用户手动安装，一次性）。
"""
from __future__ import annotations

import logging
import time
from typing import Callable, Dict, List, Optional
from urllib.parse import urlparse

from ...domains.flight.airports import official_airline_hosts

log = logging.getLogger("ua.adapters.browser")

#: 官方登录/订单查询等附属子域（与白名单主机同源，均为 HTTPS 官方页面）
EXTRA_OFFICIAL_HOSTS: List[str] = [
    "ffp.airchina.com.cn",   # 国航凤凰知音会员登录
    "et.airchina.com.cn",    # 国航订单查询
    "skypearl.csair.com",    # 南航明珠会员
    "extra.csair.com",       # 南航客票验证
]


def default_allowed_hosts() -> List[str]:
    """默认白名单：航司名录官方购票域名 + 官方附属子域（去重排序）。"""
    hosts = set(official_airline_hosts()) | set(EXTRA_OFFICIAL_HOSTS)
    return sorted(h for h in hosts if h)


class BrowserSessionBridge:
    """官方会话打开审批闸门（默认拒绝；每次打开需用户显式批准）。"""

    STATUS_PENDING = "PENDING_APPROVAL"
    STATUS_APPROVED = "APPROVED"
    STATUS_DENIED = "DENIED"
    STATUS_EXPIRED = "EXPIRED"

    def __init__(self, allowed_hosts: Optional[List[str]] = None,
                 approval_ttl_seconds: int = 300,
                 on_approved: Optional[Callable[[Dict], None]] = None) -> None:
        self.allowed_hosts: set = set(allowed_hosts if allowed_hosts is not None
                                      else default_allowed_hosts())
        self.approval_ttl_seconds = approval_ttl_seconds
        self._pending: Dict[str, Dict] = {}
        self._audit: List[Dict] = []
        self._on_approved = on_approved  # host send_notification 风格回调（可选）

    # ------------------------------------------------------------------ 查询
    def allowed_hosts_list(self) -> List[str]:
        return sorted(self.allowed_hosts)

    def pending_requests(self) -> List[Dict]:
        now = time.time()
        out = []
        for req in self._pending.values():
            expired = (now - req["created_at"]) > self.approval_ttl_seconds
            if expired and req["status"] == self.STATUS_PENDING:
                req["status"] = self.STATUS_EXPIRED
            out.append(dict(req))
        return out

    def status(self) -> Dict:
        pending = [r for r in self._pending.values()
                   if r["status"] == self.STATUS_PENDING]
        return {
            "allowed_host_count": len(self.allowed_hosts),
            "pending": len(pending),
            "audit_count": len(self._audit),
            "approval_ttl_seconds": self.approval_ttl_seconds,
        }

    # ------------------------------------------------------------------ 闸门
    def request_open(self, url: str) -> Dict:
        """默认拒绝：URL 必须 https + 白名单域名，否则 DENIED；合法 → PENDING。"""
        parsed = self._validate(url)
        if parsed is None:
            reason = (f"拒绝打开「{url}」：仅允许 https 白名单官方域名，"
                      f"且禁止携带凭据/查询外链（default-deny, RULE-007）")
            self._audit.append({"ts": time.time(), "url": url,
                                "result": "DENIED", "reason": reason})
            return {"ok": False, "status": self.STATUS_DENIED, "reason": reason}

        request_id = f"br-{int(time.time() * 1000)}-{len(self._audit)}"
        req = {
            "request_id": request_id,
            "url": parsed.geturl(),
            "host": parsed.hostname,
            "status": self.STATUS_PENDING,
            "created_at": time.time(),
        }
        self._pending[request_id] = req
        self._audit.append({"ts": time.time(), "url": req["url"],
                            "result": "PENDING", "request_id": request_id})
        log.info("browser open request %s for %s (pending approval)", request_id, req["host"])
        return {"ok": True, "status": self.STATUS_PENDING, **req}

    def decide_approval(self, request_id: str, approved: bool) -> Dict:
        """用户显式批准/拒绝（FR-056 approval 语义）。"""
        req = self._pending.get(request_id)
        if req is None:
            return {"ok": False, "status": "UNKNOWN_REQUEST",
                    "reason": f"无此请求 {request_id}（可能已过期/不存在）"}
        if req["status"] != self.STATUS_PENDING:
            return {"ok": False, "status": req["status"],
                    "reason": f"请求已处理（{req['status']}），不可重复审批"}

        if not approved:
            req["status"] = self.STATUS_DENIED
            self._audit.append({"ts": time.time(), "request_id": request_id,
                                "url": req["url"], "result": "DENIED_BY_USER"})
            return {"ok": False, "status": self.STATUS_DENIED,
                    "reason": "用户拒绝打开官方页面"}

        # 批准时二次校验（URL 可能被篡改）
        parsed = self._validate(req["url"])
        if parsed is None:
            req["status"] = self.STATUS_DENIED
            return {"ok": False, "status": self.STATUS_DENIED,
                    "reason": "批准时校验失败：URL 不在白名单（fail-closed）"}
        req["status"] = self.STATUS_APPROVED
        self._audit.append({"ts": time.time(), "request_id": request_id,
                            "url": req["url"], "result": "APPROVED_BY_USER"})
        instruction = {
            "action": "OPEN_OFFICIAL",
            "url": req["url"],
            "host": req["host"],
            "status": self.STATUS_APPROVED,
        }
        if self._on_approved is not None:
            try:
                self._on_approved({"event_type": "BROWSER_OPEN_APPROVED",
                                   "request_id": request_id,
                                   "url": req["url"], "host": req["host"]})
            except Exception as exc:  # noqa: BLE001 — 回调失败不影响审批结果
                log.warning("on_approved callback failed: %s", exc)
        return {"ok": True, **instruction}

    def audit_log(self, limit: int = 50) -> List[Dict]:
        return list(reversed(self._audit[-limit:]))

    # ------------------------------------------------------------------ util
    def _validate(self, url: str) -> Optional[urlparse]:
        """https + 白名单主机 + 无凭据嵌入 → 返回解析结果，否则 None。"""
        if not isinstance(url, str) or not url:
            return None
        try:
            parsed = urlparse(url)
        except ValueError:
            return None
        if parsed.scheme != "https" or not parsed.hostname:
            return None
        if parsed.username or parsed.password:
            return None  # 禁止 URL 内嵌凭据
        if parsed.hostname not in self.allowed_hosts:
            return None
        return parsed


def browser_bridge_manifest():
    from universal_agent.core.contracts import SkillManifest
    return SkillManifest(
        skill_id="browser.official_session_bridge",
        version="0.1.0",
        domains=["flight", "railway", "hotel"],
        capabilities={"search": False, "detail": False, "availability": False,
                      "price_verify": False, "prepare_order": False,
                      "execute_order": False,
                      "open_official_page": "approval_required"},
        transport=["browser-extension"],
        risk={"execution": "user_approved_open_only"},
        description="人机协同官方会话桥：白名单域名默认拒绝，用户批准后在本机 Chrome 打开",
    )
