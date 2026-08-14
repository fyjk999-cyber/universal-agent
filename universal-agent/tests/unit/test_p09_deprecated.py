"""P0.9-7 回归测试：生产路径禁止使用字符串比较 due_tasks。"""
from __future__ import annotations

import inspect

from universal_agent.coordinator.scheduler import daemon as daemon_mod
from universal_agent.coordinator.task_registry import registry as reg_mod
from universal_agent.coordinator.watch_manager import manager as wm_mod


class TestNoDeprecatedDueTasks:
    def test_registry_has_no_string_due_tasks(self):
        """TaskRegistry 不再有 due_tasks(now_str) 方法。"""
        assert not hasattr(reg_mod.TaskRegistry, "due_tasks")
        assert hasattr(reg_mod.TaskRegistry, "due_tasks_utc")

    def test_daemon_uses_utc_only(self):
        """WatchDaemon 生产路径只用 due_tasks_utc。"""
        src = inspect.getsource(daemon_mod)
        assert "due_tasks_utc" in src
        assert ".due_tasks(\"" not in src.replace("due_tasks_utc", "")

    def test_watch_manager_uses_utc_only(self):
        src = inspect.getsource(wm_mod)
        assert "due_tasks_utc" in src
        # 不引用字符串版
        assert "registry.due_tasks(" not in src.replace("due_tasks_utc", "")

    def test_cli_scheduler_path_no_string_compare(self):
        """apps/scheduler 与 apps/agent_cli 不调用字符串版。"""
        import pathlib
        apps = pathlib.Path(__file__).resolve().parent.parent.parent / "universal_agent" / "apps"
        for f in ("scheduler.py", "shadow_scan.py", "agent_cli.py"):
            src = (apps / f).read_text("utf-8") if (apps / f).exists() else ""
            assert "due_tasks(\"" not in src
