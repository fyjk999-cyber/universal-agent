"""定时调度守护（§15 + P0.1/P0.2）— IANA 时区 + misfire + ScanRun 分离。

- due 判定：datetime 比较（due_tasks_utc）
- misfire：RUN_ONCE 默认补跑；SKIP / CATCH_UP_LIMITED 可选
- ScanRun 独立状态：平台临时失败 → FAILED_RETRYABLE + backoff，
  绝不把 WatchTask 置 FAILED（仅致命错误改变 Watch 生命周期）
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, Optional

from universal_agent.core.contracts import ScanRunStatus, WatchTask
from universal_agent.core.state_machine import alive_states
from universal_agent.coordinator.checkpoint import Checkpoint
from universal_agent.coordinator.task_registry import TaskRegistry
from universal_agent.coordinator.task_registry.scanruns import (
    ScanRunRepository,
    classify_error,
    is_fatal,
)
from universal_agent.events import EventBusProtocol, InProcessEventBus

log = logging.getLogger("ua.scheduler.daemon")

#: 扫描执行器：task → 扫描结果摘要（宿主/域无关）
ScanRunner = Callable[[WatchTask], Awaitable[Dict]]


class WatchDaemon:
    """周期驱动所有 Active Watch 任务；Watch 生命周期与 ScanRun 分离。"""

    def __init__(self, registry: TaskRegistry, bus: Optional[EventBusProtocol] = None,
                 checkpoint: Optional[Checkpoint] = None,
                 scan_runs: Optional[ScanRunRepository] = None,
                 tick_seconds: int = 60,
                 runner: Optional[ScanRunner] = None,
                 misfire_policy: str = "RUN_ONCE") -> None:
        self.registry = registry
        self.bus = bus or InProcessEventBus()
        self.checkpoint = checkpoint
        self.scan_runs = scan_runs
        self.tick_seconds = tick_seconds
        self.runner = runner
        self.misfire_policy = misfire_policy
        self._running = False

    async def run_forever(self) -> None:
        self._running = True
        log.info("WatchDaemon 启动，tick=%ss misfire=%s", self.tick_seconds, self.misfire_policy)
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
        # P0.1: datetime 比较判定到期
        for task_id in self.registry.due_tasks_utc(now):
            task = self.registry.get(task_id)
            if task is not None:
                await self._run_task(task)
        # misfire 补跑（RUN_ONCE 默认）
        if self.misfire_policy != "SKIP":
            await self._catch_up_missed(now)
        # P1.3: ScanRun backoff 到期重试（真实重试循环）
        await self._retry_failed_runs()

    async def _retry_failed_runs(self) -> None:
        """对 FAILED_RETRYABLE 且 next_retry_at 已到的 run 重试（backoff 已过）。"""
        if self.scan_runs is None:
            return
        for run in self.scan_runs.retryable():
            task = self.registry.get(run.task_id)
            if task is None or task.state not in alive_states():
                continue  # 任务已取消/过期 → 不再重试
            log.info("重试任务 %s (run %s, attempt %s)",
                     run.task_id, run.run_id, run.retry_count + 1)
            await self._run_task(task, is_retry=True)

    async def _catch_up_missed(self, now) -> None:
        from universal_agent.coordinator.scheduler import BaselineScheduler, MisfirePolicy
        sch = BaselineScheduler()
        for task in self.registry.active_watches():
            if task.next_scan_at is not None and task.next_scan_at > now:
                continue  # 已安排未来运行
            policy = MisfirePolicy(self.misfire_policy)
            missed = sch.missed_run(task, now, policy, max_catch_up=1)
            if missed is not None:
                log.info("misfire 补跑任务 %s (scheduled %s)", task.id, missed.scheduled_at)
                await self._run_task(task, is_misfire=True)

    async def _run_task(self, task: WatchTask, is_misfire: bool = False,
                        is_retry: bool = False) -> None:
        # ---- ScanRun 独立状态（P0.2 / P1.3 重试）----
        run = None
        if self.scan_runs is not None:
            attempt = task.scan_count + 1
            if is_retry:
                last = self.scan_runs.latest_for(task.id)
                attempt = (last.retry_count + 1) if last else attempt
            run = self.scan_runs.start(task.id, attempt=attempt)
        if self.checkpoint is not None:
            self.checkpoint.mark_task_started(task.id, cycle=str(task.scan_count + 1))
        try:
            if self.runner is not None:
                result = await self.runner(task)
                log.info("任务 %s 完成: %s", task.id, result)
            else:
                log.warning("任务 %s 无 runner，仅推进调度", task.id)
            if run is not None:
                self.scan_runs.finish(run.run_id, ScanRunStatus.SUCCESS)
            self._advance(task)
        except Exception as exc:  # noqa: BLE001
            log.error("任务 %s 执行失败: %s", task.id, exc)
            if run is not None:
                if is_fatal(exc):
                    self.scan_runs.finish(run.run_id, ScanRunStatus.FAILED_FATAL,
                                          error_type=classify_error(exc), error_message=str(exc))
                    # 致命错误才改变 Watch 生命周期
                    self._mark_watch_failed(task, str(exc))
                else:
                    self.scan_runs.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE,
                                          error_type=classify_error(exc), error_message=str(exc))
                    # 临时失败：Watch 保持 WATCHING，等待 backoff 重试
                    log.info("任务 %s 临时失败（可重试），Watch 保持 WATCHING", task.id)
            else:
                self._mark_watch_failed(task, str(exc))
        finally:
            if self.checkpoint is not None:
                self.checkpoint.mark_task_done(task.id)

    @staticmethod
    def _mark_watch_failed(task: WatchTask, reason: str) -> None:
        from universal_agent.core.contracts import WatchState
        task.state = WatchState.FAILED
        task.version += 1
        task.history.append({"event": "FAILED", "reason": reason})

    def _advance(self, task: WatchTask) -> None:
        """推进 next_scan_at（使用 task IANA 时区，P0.1）。"""
        from universal_agent.coordinator.scheduler import BaselineScheduler
        task.scan_count += 1
        task.last_scan_at = None  # 由调度器在 misfire 判定时用真实时间
        from datetime import datetime, timezone
        task.last_scan_at = datetime.now(timezone.utc)
        run = BaselineScheduler().next_run(task)
        task.next_scan_at = run.at if run else None
        self.registry.update(task)


async def load_watch_daemon(tasks_dir: Path, data_dir: Path,
                            runner: Optional[ScanRunner] = None,
                            tick_seconds: int = 60,
                            misfire_policy: str = "RUN_ONCE") -> WatchDaemon:
    """从 tasks/*.yaml 加载所有 watch 任务并组装守护进程。"""
    from universal_agent.coordinator.task_registry import load_watch_task
    registry = TaskRegistry(data_dir / "registry")
    checkpoint = Checkpoint(data_dir / "checkpoint.json")
    scan_runs = ScanRunRepository(data_dir / "scan_runs")

    for yaml_path in sorted(Path(tasks_dir).glob("*.yaml")):
        if yaml_path.name.startswith("_"):
            continue
        task = load_watch_task(yaml_path)
        existing = registry.get(task.id)
        if existing is None:
            registry.create(task)
            log.info("加载任务 %s", task.id)

    daemon = WatchDaemon(registry=registry, checkpoint=checkpoint,
                         scan_runs=scan_runs, tick_seconds=tick_seconds,
                         runner=runner, misfire_policy=misfire_policy)
    return daemon
