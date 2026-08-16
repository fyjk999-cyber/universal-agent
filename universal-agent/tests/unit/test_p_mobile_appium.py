"""P-MOBILE — AppiumSkill（iPhone 控制）：SkillProtocol 实现 + MobileTransport 抽象。

验收：
1. MobileTransport：WDA HTTP 通信（status/session/source/screenshot/apps），标准库实现
2. AppiumSkill 实现 SkillProtocol 6 方法
3. search → 扫描已安装 app 列表
4. detail → 单 app 信息（bundleId/状态）
5. availability → app 是否已装/可启动
6. health_check → WDA 健康状态
7. prepare_action → L2 不 commit（控制操作只到「可执行」边界）
8. WDA 不可达 → fail-closed（不崩，返回明确状态）
"""
from __future__ import annotations

from pathlib import Path

import pytest

from universal_agent.registry.skills.protocol import SkillProtocol
from universal_agent.adapters.mobile.transport import MobileTransport


# ===================== 假 WDA 服务（测试用） =====================
class _FakeWDAHandler:
    """模拟 WDA 的 HTTP 响应（用 http.server 起本地假服务）。"""

    def __init__(self) -> None:
        self.sessions: dict = {}
        self._seq = 0

    def handle(self, path: str, method: str, body: dict | None) -> dict:
        if path == "/status" and method == "GET":
            return {"value": {"build": {"version": "16.2.0"},
                              "os": {"name": "iOS", "version": "18.6"},
                              "device": "iphone"}}
        if path == "/session" and method == "POST":
            self._seq += 1
            sid = f"FAKE-{self._seq}"
            self.sessions[sid] = {}
            return {"value": {"sessionId": sid}}
        if path.endswith("/appium/device/apps"):
            return {"value": getattr(self, "installed_apps", [])}
        if path.startswith("/session/") and path.endswith("/source"):
            return {"value": '<XCUIElementTypeApplication name="TestApp" label="TestApp"/>'}
        if path.startswith("/session/") and path.endswith("/screenshot"):
            return {"value": "aGVsbG8="}  # base64 "hello"
        if path.startswith("/session/") and method == "DELETE":
            return {"value": None}
        return {"value": {}, "error": "not found"}


@pytest.fixture()
def fake_wda() -> tuple[str, _FakeWDAHandler]:
    """起一个本地假 WDA 服务，返回 (base_url, handler)。"""
    import http.server
    import json
    import threading

    handler_inst = _FakeWDAHandler()

    class Handler(http.server.BaseHTTPRequestHandler):
        def _reply(self, code: int, obj: dict) -> None:
            data = json.dumps(obj).encode()
            self.send_response(code)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def do_GET(self):  # noqa: N802
            self._reply(200, handler_inst.handle(self.path, "GET", None))

        def do_POST(self):  # noqa: N802
            ln = int(self.headers.get("Content-Length", 0))
            body = json.loads(self.rfile.read(ln)) if ln else None
            self._reply(200, handler_inst.handle(self.path, "POST", body))

        def do_DELETE(self):  # noqa: N802
            self._reply(200, handler_inst.handle(self.path, "DELETE", None))

        def log_message(self, *a):  # noqa: N802
            pass

    server = http.server.HTTPServer(("127.0.0.1", 0), Handler)
    port = server.server_address[1]
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    yield f"http://127.0.0.1:{port}", handler_inst
    server.shutdown()


# ===================== MobileTransport =====================
def test_transport_status(fake_wda) -> None:
    """transport 能读 WDA /status。"""
    from universal_agent.adapters.mobile.transport import MobileTransport
    url, _ = fake_wda
    t = MobileTransport(wda_url=url, udid="sim-1")
    st = t.status()
    assert st.get("os", {}).get("name") == "iOS"


def test_transport_session_and_source(fake_wda) -> None:
    """transport 建会话 + 读屏幕层级。"""
    from universal_agent.adapters.mobile.transport import MobileTransport
    url, _ = fake_wda
    t = MobileTransport(wda_url=url, udid="sim-1")
    sid = t.create_session()
    assert sid and sid.startswith("FAKE-")
    src = t.page_source(sid)
    assert "TestApp" in src
    t.delete_session(sid)


def test_transport_unreachable_fails_closed() -> None:
    """WDA 不可达 → 明确失败，不崩。"""
    from universal_agent.adapters.mobile.transport import MobileTransport
    t = MobileTransport(wda_url="http://127.0.0.1:1", udid="x")  # 无服务
    st = t.status()
    assert st.get("status") in ("UNREACHABLE", "ERROR")
    assert t.create_session() is None


# ===================== AppiumSkill（SkillProtocol） =====================
def test_skill_implements_protocol(fake_wda) -> None:
    """AppiumSkill 实现 SkillProtocol。"""
    from universal_agent.adapters.mobile.skill import AppiumSkill
    from universal_agent.adapters.mobile.transport import MobileTransport
    url, _ = fake_wda
    s = AppiumSkill(transport=MobileTransport(wda_url=url))
    assert isinstance(s, SkillProtocol)


def test_health_check(fake_wda) -> None:
    """health_check 反映 WDA 状态。"""
    from universal_agent.adapters.mobile.skill import AppiumSkill
    from universal_agent.adapters.mobile.transport import MobileTransport
    url, _ = fake_wda
    s = AppiumSkill(transport=MobileTransport(wda_url=url))
    h = s.health_check()
    assert h.get("status") in ("HEALTHY", "DEGRADED", "UNREACHABLE")


def test_search_returns_app_list(fake_wda) -> None:
    """search → app 列表（扫描软件信息）。"""
    from universal_agent.adapters.mobile.skill import AppiumSkill
    url, handler = fake_wda
    # 注入假 app 列表
    handler.installed_apps = [
        {"bundleId": "com.silver.jarvis.companion", "name": "JARVIS", "version": "1.0"},
        {"bundleId": "com.apple.mobilesafari", "name": "Safari", "version": "18.6"},
    ]
    s = AppiumSkill(transport=MobileTransport(wda_url=url))
    apps = s.search({"query": "installed_apps"})
    assert isinstance(apps, list)
    assert any(a.get("bundleId") == "com.silver.jarvis.companion" for a in apps)


def test_detail_returns_app_info(fake_wda) -> None:
    """detail → 单 app 信息。"""
    from universal_agent.adapters.mobile.skill import AppiumSkill
    url, _ = fake_wda
    s = AppiumSkill(transport=MobileTransport(wda_url=url))
    info = s.detail("com.silver.jarvis.companion")
    assert isinstance(info, dict)


def test_availability_unknown(fake_wda) -> None:
    """availability → 状态（已装/未装/未知）。"""
    from universal_agent.adapters.mobile.skill import AppiumSkill
    url, _ = fake_wda
    s = AppiumSkill(transport=MobileTransport(wda_url=url))
    a = s.availability("com.unknown.app")
    assert isinstance(a, dict)
    assert "installed" in a or "status" in a


def test_prepare_action_no_commit(fake_wda) -> None:
    """prepare_action → L2 不 commit（控制操作边界）。"""
    from universal_agent.adapters.mobile.skill import AppiumSkill
    url, _ = fake_wda
    s = AppiumSkill(transport=MobileTransport(wda_url=url))
    r = s.prepare_action("com.silver.jarvis.companion", {"action": "launch"})
    assert r.get("status") in ("NOT_READY", "PREPARED", "PENDING_APPROVAL")


def test_verify_returns_result(fake_wda) -> None:
    """verify → 操作后验证。"""
    from universal_agent.adapters.mobile.skill import AppiumSkill
    url, _ = fake_wda
    s = AppiumSkill(transport=MobileTransport(wda_url=url))
    v = s.verify("com.silver.jarvis.companion")
    assert isinstance(v, dict)
