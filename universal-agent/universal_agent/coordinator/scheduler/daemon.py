"""定时调度守护（§15 Baseline Scheduler 驱动）— 无第三方依赖.

用 asyncio 循环驱动已有 BaselineScheduler + WatchManager：
  - 每分钟检查一次 due_tasks
  - 到期任务 → 执行真实扫描（Flight/Hotel/Jobs 协调器）
  - 扫描后 mark_scanned（推进 next_scan_at）
  - 支持进程重启恢复（TaskRegistry/Checkpoint JSON 持久化 §60）

设计：host-agnostic —— 不依赖任何宿主（Harness/Jarvis），只通过
注入的 scan 执行器与宿主解耦。接入 DSH 时由宿主 Adapter 提供执行器。
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, Optional

from universal_agent.core.contracts import WatchTask
from universal_agent.coordinator.checkpoint import Checkpoint
from universal_agent.coordinator.task_registry import TaskRegistry
from universal_agent.events import EventBusProtocol, InProcessEventBus

log = logging.getLogger("ua.scheduler.daemon")

#: 扫描执行器：task → 扫描结果摘要（宿主/域无关）
ScanRunner = Callable[[WatchTask], Awaitable[Dict]]


class WatchDaemon:
    """周期驱动所有 Active Watch 任务的守护进程。

    每 tick（默认 60s）检查 due_tasks；到期则通过 runner 执行扫描。
    失败的任务标记 FAILED（可重试），不崩溃整体（§48）。
    """

    def __init__(self, registry: TaskRegistry, bus: Optional[EventBusProtocol] = None,
                 checkpoint: Optional[Checkpoint] = None,
                 tick_seconds: int = 60,
                 runner: Optional[ScanRunner] = None) -> None:
        self.registry = registry
        self.bus = bus or InProcessEventBus()
        self.checkpoint = checkpoint
        self.tick_seconds = tick_seconds
        self.runner = runner
        self._running = False

    async def run_forever(self) -> None:
        """主循环：tick → 检查到期任务 → 执行。Ctrl+C 安全退出。"""
        self._running = True
        log.info("WatchDaemon 启动，tick=%ss", self.tick_seconds)
        while self._running:
            try:
                await self._tick()
            except Exception as exc:  # noqa: BLE001 — 循环绝不崩溃
                log.exception("tick failed: %s", exc)
            await asyncio.sleep(self.tick_seconds)

    async def stop(self) -> None:
        self._running = False

    async def _tick(self) -> None:
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        due = self.registry.due_tasks(now.strftime("%H:%M"))
        for task in due:
            await self._run_task(task)

    async def _run_task(self, task: WatchTask) -> None:
        log.info("执行到期任务 %s (state=%s)", task.id, task.state.value)
        if self.checkpoint is not None:
            self.checkpoint.mark_task_started(task.id, cycle=str(task.scan_count + 1))
        try:
            if self.runner is not None:
                result = await self.runner(task)
                log.info("任务 %s 完成: %s", task.id, result)
            else:
                log.warning("任务 %s 无 runner，仅推进调度", task.id)
            self.registry.update(task)
            self._advance(task)
        except Exception as exc:  # noqa: BLE001 — 单任务失败不中断（§48）
            log.error("任务 %s 执行失败: %s", task.id, exc)
            from universal_agent.core.contracts import WatchState
            task.state = WatchState.FAILED
            task.version += 1
            self.registry.update(task)
        finally:
            if self.checkpoint is not None:
                self.checkpoint.mark_task_done(task.id)

    def _advance(self, task: WatchTask) -> None:
        """推进 next_scan_at 到下一个基线时间（§15）。"""
        from universal_agent.coordinator.scheduler import BaselineScheduler
        task.scan_count += 1
        run = BaselineScheduler().next_run(task)
        task.next_scan_at = run.at if run else None
        self.registry.update(task)


async def load_watch_daemon(tasks_dir: Path, data_dir: Path,
                            runner: Optional[ScanRunner] = None,
                            tick_seconds: int = 60) -> WatchDaemon:
    """从 tasks/*.yaml 加载所有 watch 任务并组装守护进程。"""
    from universal_agent.coordinator.task_registry import load_watch_task
    registry = TaskRegistry(data_dir / "registry")
    checkpoint = Checkpoint(data_dir / "checkpoint.json")

    for yaml_path in sorted(Path(tasks_dir).glob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue
        task = load_watch_task(yaml_path)
        existing = registry.get(task.id)
        if existing is None:
            registry.create(task)
            log.info("加载任务 %s", task.id)

    daemon = WatchDaemon(registry=registry, checkpoint=checkpoint,
                         tick_seconds=tick_seconds, runner=runner)
    return daemon
