"""BrowserSessionBridge 测试 — 白名单默认拒绝 + 审批流（RULE-007/FR-060-062）。

验证：非白名单 URL 直接 DENIED；合法 URL 需 PENDING→用户批准；批准时二次校验；
审计日志可追溯；无凭据嵌入。
"""
from __future__ import annotations

import pytest

from universal_agent.adapters.browser.bridge import (
    BrowserSessionBridge,
    EXTRA_OFFICIAL_HOSTS,
    default_allowed_hosts,
)


class TestAllowlist:
    def test_default_allowlist_has_official_hosts(self):
        hosts = default_allowed_hosts()
        assert "www.airchina.com.cn" in hosts
        assert "www.csair.com" in hosts
        assert "www.ceair.com" in hosts
        assert "ffp.airchina.com.cn" in hosts  # 官方会员登录子域
        assert len(hosts) > 10

    def test_extra_hosts_are_official_subdomains(self):
        for h in EXTRA_OFFICIAL_HOSTS:
            assert h.endswith(("airchina.com.cn", "csair.com"))


class TestDefaultDeny:
    def test_http_rejected(self):
        bridge = BrowserSessionBridge()
        r = bridge.request_open("http://www.airchina.com.cn/")
        assert r["ok"] is False and r["status"] == "DENIED"

    def test_non_allowlisted_host_rejected(self):
        bridge = BrowserSessionBridge()
        r = bridge.request_open("https://evil.example.com/steal")
        assert r["ok"] is False and r["status"] == "DENIED"

    def test_credentials_in_url_rejected(self):
        bridge = BrowserSessionBridge()
        r = bridge.request_open("https://user:pass@www.airchina.com.cn/")
        assert r["ok"] is False

    def test_garbage_rejected(self):
        bridge = BrowserSessionBridge()
        assert bridge.request_open("not a url")["ok"] is False
        assert bridge.request_open("")["ok"] is False

    def test_custom_allowlist(self):
        bridge = BrowserSessionBridge(allowed_hosts=["shop.example.com"])
        assert bridge.request_open("https://shop.example.com/")["ok"] is True
        assert bridge.request_open("https://www.airchina.com.cn/")["ok"] is False


class TestApprovalFlow:
    def test_pending_then_approve(self):
        bridge = BrowserSessionBridge(allowed_hosts=["www.airchina.com.cn"])
        r = bridge.request_open("https://www.airchina.com.cn/zh-CN/")
        assert r["ok"] is True and r["status"] == "PENDING_APPROVAL"
        rid = r["request_id"]
        a = bridge.decide_approval(rid, approved=True)
        assert a["ok"] is True
        assert a["action"] == "OPEN_OFFICIAL"
        assert a["host"] == "www.airchina.com.cn"

    def test_user_deny(self):
        bridge = BrowserSessionBridge(allowed_hosts=["www.csair.com"])
        r = bridge.request_open("https://www.csair.com/")
        a = bridge.decide_approval(r["request_id"], approved=False)
        assert a["ok"] is False and a["status"] == "DENIED"

    def test_unknown_request(self):
        bridge = BrowserSessionBridge()
        assert bridge.decide_approval("nope", True)["status"] == "UNKNOWN_REQUEST"

    def test_double_approval_rejected(self):
        bridge = BrowserSessionBridge(allowed_hosts=["www.ceair.com"])
        r = bridge.request_open("https://www.ceair.com/")
        rid = r["request_id"]
        assert bridge.decide_approval(rid, True)["ok"] is True
        again = bridge.decide_approval(rid, True)
        assert again["ok"] is False
        assert "不可重复" in again["reason"]

    def test_approval_revalidates_url(self):
        """批准时 URL 若已不在白名单 → fail-closed 拒绝。"""
        bridge = BrowserSessionBridge(allowed_hosts=["www.airchina.com.cn"])
        r = bridge.request_open("https://www.airchina.com.cn/")
        bridge.allowed_hosts.discard("www.airchina.com.cn")
        a = bridge.decide_approval(r["request_id"], True)
        assert a["ok"] is False and a["status"] == "DENIED"

    def test_audit_log_traceable(self):
        bridge = BrowserSessionBridge(allowed_hosts=["www.airchina.com.cn"])
        bridge.request_open("https://evil.example.com/")
        bridge.request_open("https://www.airchina.com.cn/")
        log = bridge.audit_log()
        assert len(log) >= 2
        assert any("DENIED" in str(e["result"]) for e in log)
        assert any("PENDING" in str(e["result"]) for e in log)

    def test_on_approved_callback(self):
        events = []
        bridge = BrowserSessionBridge(allowed_hosts=["www.airchina.com.cn"],
                                      on_approved=events.append)
        r = bridge.request_open("https://www.airchina.com.cn/")
        bridge.decide_approval(r["request_id"], True)
        assert len(events) == 1
        assert events[0]["event_type"] == "BROWSER_OPEN_APPROVED"

    def test_status_counts(self):
        bridge = BrowserSessionBridge(allowed_hosts=["www.airchina.com.cn"])
        assert bridge.status()["allowed_host_count"] == 1
        bridge.request_open("https://www.airchina.com.cn/")
        assert bridge.status()["pending"] == 1
