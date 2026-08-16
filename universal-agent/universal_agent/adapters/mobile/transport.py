"""MobileTransport（P-MOBILE）— WDA HTTP 通信抽象。

职责：只做「怎么和设备通信」（IRON RULE 3：Adapter = 通信机制）。
   - WDA 本地/网络 HTTP（标准库 urllib，零第三方依赖）
   - 未来可加 USB 隧道 / TestMu 云传输（同接口）

不关心「控制什么 app 做什么」——那是 Skill 的职责。
"""
from __future__ import annotations

import json
import logging
import time
import urllib.request
from typing import Any, Dict, List, Optional

log = logging.getLogger("ua.mobile.transport")


class MobileTransport:
    """WDA HTTP 客户端。"""

    def __init__(self, wda_url: str = "http://127.0.0.1:8100",
                 udid: Optional[str] = None,
                 timeout: int = 15) -> None:
        self.wda_url = wda_url.rstrip("/")
        self.udid = udid
        self.timeout = timeout
        self._session_id: Optional[str] = None

    # ---- 底层 HTTP ----
    def _call(self, path: str, method: str = "GET",
              body: Optional[Dict[str, Any]] = None) -> Optional[Dict[str, Any]]:
        url = self.wda_url + path
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8", errors="replace"))
        except Exception as exc:  # noqa: BLE001 — 网络层失败统一处理
            log.warning("WDA %s %s 失败: %s", method, path, exc)
            return None

    # ---- WDA 状态 ----
    def status(self) -> Dict[str, Any]:
        """WDA /status。不可达 → {"status": "UNREACHABLE"}。"""
        resp = self._call("/status")
        if resp is None:
            return {"status": "UNREACHABLE"}
        value = resp.get("value", resp)
        if isinstance(value, dict) and "build" in value:
            return {"status": "HEALTHY", **value}
        return {"status": "ERROR", **resp}

    # ---- 会话 ----
    def create_session(self, caps: Optional[Dict[str, Any]] = None) -> Optional[str]:
        """创建 WDA 会话，返回 sessionId；失败 None。"""
        caps = caps or {"platformName": "iOS", "automationName": "XCUITest"}
        resp = self._call("/session", "POST",
                          {"capabilities": {"alwaysMatch": caps}})
        if resp is None:
            return None
        value = resp.get("value", {})
        sid = value.get("sessionId") if isinstance(value, dict) else None
        if sid:
            self._session_id = sid
        return sid

    def delete_session(self, session_id: Optional[str] = None) -> None:
        sid = session_id or self._session_id
        if sid:
            self._call(f"/session/{sid}", "DELETE")
            self._session_id = None

    # ---- 页面/元素 ----
    def page_source(self, session_id: Optional[str] = None) -> str:
        """读取当前屏幕 UI 层级（XML）。"""
        sid = session_id or self._session_id
        if not sid:
            return ""
        resp = self._call(f"/session/{sid}/source")
        if resp is None:
            return ""
        return str(resp.get("value", ""))

    def screenshot(self, session_id: Optional[str] = None) -> Optional[bytes]:
        """截图（base64 → bytes）。"""
        sid = session_id or self._session_id
        if not sid:
            return None
        resp = self._call(f"/session/{sid}/screenshot")
        if resp is None:
            return None
        import base64
        try:
            return base64.b64decode(resp.get("value", ""))
        except Exception:  # noqa: BLE001
            return None

    def active_session(self) -> Optional[str]:
        return self._session_id

    # ---- 已安装 app（WDA mobile: 扩展） ----
    def list_apps(self, session_id: Optional[str] = None) -> List[Dict[str, Any]]:
        """已安装 app 列表。WDA 不支持时返回空（fail-closed）。"""
        sid = session_id or self._session_id
        if not sid:
            return []
        resp = self._call(f"/session/{sid}/appium/device/apps",
                          "GET")
        if resp is None:
            return []
        value = resp.get("value", [])
        return value if isinstance(value, list) else []
