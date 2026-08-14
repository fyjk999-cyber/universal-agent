"""Host Contract tests (§45): both adapters implement HostProtocol faithfully."""
from __future__ import annotations

import inspect

from universal_agent.hosts.deepseek_harness import HarnessHostAdapter
from universal_agent.hosts.jarvis import MockJarvisHostAdapter
from universal_agent.hosts.protocol import HostProtocol

REQUIRED_METHODS = [
    "create_task", "update_task", "pause_task", "resume_task", "cancel_task",
    "run_task_once", "list_tasks", "get_task", "send_notification",
    "request_approval", "get_host_user_context", "publish_event",
]


def test_host_protocol_declares_all_methods():
    for m in REQUIRED_METHODS:
        assert hasattr(HostProtocol, m), f"HostProtocol missing {m}"
        fn = getattr(HostProtocol, m)
        assert getattr(fn, "__isabstractmethod__", False), f"{m} not abstract"


def test_harness_adapter_implements_protocol():
    assert issubclass(HarnessHostAdapter, HostProtocol)
    for m in REQUIRED_METHODS:
        assert callable(getattr(HarnessHostAdapter, m)), f"harness missing {m}"


def test_jarvis_adapter_implements_protocol():
    assert issubclass(MockJarvisHostAdapter, HostProtocol)
    for m in REQUIRED_METHODS:
        assert callable(getattr(MockJarvisHostAdapter, m)), f"jarvis missing {m}"


def test_jarvis_reserved_capabilities_declared():
    expected = {
        "voice_intent", "desktop_notification", "mobile_notification",
        "approval_request", "task_status", "memory_query", "watch_query",
        "action_status", "agent_health",
    }
    assert expected <= set(MockJarvisHostAdapter.CAPABILITIES)
