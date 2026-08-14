"""定时调度守护（§15 + P0.1/P0.2 + P0.9-1 Retry 真正接入）.

P0.9-1 模型：
  WatchTask
    ├── Baseline Schedule  → next_scan_at
    └── Retry Schedule     → next_retry_at（FAILED_RETRYABLE 时有效）

- RunGuard：同一 task 同时只能一个 RUNNING ScanRun（防 baseline+retry 双启动）
- Retry 由 next_retry_at 驱动（backoff 到期才重试），失败后 next_scan_at 推进
  → 不会每个 tick 都触发
- Retry 链跨重启保持（retry_of_run_id / parent_run_id）
- 临时失败：Watch 保持 WATCHING；仅致命错误改变 Watch 生命周期
"""
from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Awaitable, Callable, Dict, Optional

from universal_agent.core.contracts import ScanRun, ScanRunStatus, WatchTask
from universal_agent.core.state_machine import alive_states
from universal_agent.coordinator.checkpoint import Checkpoint
from universal_agent.coordinator.scheduler.runguard import RunningTaskGuard
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
    """周期驱动所有 Active Watch 任务；Retry 由 next_retry_at 驱动。"""

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
        self.guard = RunningTaskGuard()
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
        # 1) Retry 优先（P0.9-1：next_retry_at 到期的 run）
        await self._retry_failed_runs(now)
        # 2) baseline due tasks
        for task_id in self.registry.due_tasks_utc(now):
            task = self.registry.get(task_id)
            if task is None:
                continue
            # 该 task 有 pending retry 时，retry 优先，跳过 baseline 重复执行
            if self._has_pending_retry(task.id):
                log.info("task %s 有 pending retry，跳过 baseline 触发", task.id)
                continue
            if not self.guard.try_acquire(task.id):
                continue  # 已 RUNNING，防双启动
            try:
                await self._run_task(task)
            finally:
                self.guard.release(task.id)
        # 3) misfire 补跑（RUN_ONCE 默认）
        if self.misfire_policy != "SKIP":
            await self._catch_up_missed(now)

    def _has_pending_retry(self, task_id: str) -> bool:
        """该 task 是否有待重试的 FAILED_RETRYABLE run（尚未成功恢复）。"""
        if self.scan_runs is None:
            return False
        latest = self.scan_runs.latest_for(task_id)
        return latest is not None and latest.status == ScanRunStatus.FAILED_RETRYABLE

    async def _retry_failed_runs(self, now=None) -> None:
        """P0.9-1: 只重试 next_retry_at <= now 的 run（backoff 到期）。"""
        from datetime import datetime, timezone
        if now is None:
            now = datetime.now(timezone.utc)
        if self.scan_runs is None:
            return
        for run in self.scan_runs.retryable():
            task = self.registry.get(run.task_id)
            if task is None or task.state not in alive_states():
                continue
            # RunGuard：防与 baseline/misfire 双启动
            if not self.guard.try_acquire(run.task_id):
                continue
            try:
                await self._run_retry(task, run)
            finally:
                self.guard.release(run.task_id)

    async def _run_retry(self, task: WatchTask, parent_run: ScanRun) -> None:
        """执行一次 retry（创建新 ScanRun，继承 retry chain）。"""
        if self.scan_runs is None:
            return
        run = self.scan_runs.start_retry(task.id, parent_run.run_id)
        log.info("重试任务 %s (run %s, retry #%s)",
                 task.id, run.run_id, run.retry_count)
        if self.checkpoint is not None:
            self.checkpoint.mark_task_started(task.id, cycle=f"retry-{run.retry_count}")
        try:
            if self.runner is not None:
                await self.runner(task)
            self.scan_runs.finish(run.run_id, ScanRunStatus.SUCCESS)
            # retry 成功 → 清除 retry 状态，恢复正常 baseline
            self._advance(task)
            log.info("任务 %s retry #%s 成功，恢复 baseline 调度", task.id, run.retry_count)
        except Exception as exc:  # noqa: BLE001
            if is_fatal(exc):
                self.scan_runs.finish(run.run_id, ScanRunStatus.FAILED_FATAL,
                                      error_type=classify_error(exc), error_message=str(exc))
                self._mark_watch_failed(task, str(exc))
            else:
                self.scan_runs.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE,
                                      error_type=classify_error(exc), error_message=str(exc))
                log.info("任务 %s retry #%s 仍失败，backoff 后重试", task.id, run.retry_count)
        finally:
            if self.checkpoint is not None:
                self.checkpoint.mark_task_done(task.id)

    async def _catch_up_missed(self, now) -> None:
        from universal_agent.coordinator.scheduler import BaselineScheduler, MisfirePolicy
        sch = BaselineScheduler()
        for task in self.registry.active_watches():
            if task.next_scan_at is not None and task.next_scan_at > now:
                continue
            if self._has_pending_retry(task.id):
                continue  # retry 优先
            if not self.guard.try_acquire(task.id):
                continue
            try:
                policy = MisfirePolicy(self.misfire_policy)
                missed = sch.missed_run(task, now, policy, max_catch_up=1)
                if missed is not None:
                    log.info("misfire 补跑任务 %s (scheduled %s)", task.id, missed.scheduled_at)
                    await self._run_task(task, is_misfire=True)
            finally:
                self.guard.release(task.id)

    async def _run_task(self, task: WatchTask, is_misfire: bool = False) -> None:
        """P0.9-1: 失败时也推进 next_scan_at（防止每 tick 重复触发），
        由 retry 调度单独控制重试时机。"""
        run = None
        if self.scan_runs is not None:
            run = self.scan_runs.start(task.id, attempt=task.scan_count + 1)
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
                    self._mark_watch_failed(task, str(exc))
                else:
                    self.scan_runs.finish(run.run_id, ScanRunStatus.FAILED_RETRYABLE,
                                          error_type=classify_error(exc), error_message=str(exc))
                    # 临时失败：Watch 保持 WATCHING
                    # P0.9-1: 推进 next_scan_at 到下一个 baseline（retry 由 next_retry_at 驱动）
                    log.info("任务 %s 临时失败（可重试），Watch 保持 WATCHING", task.id)
            else:
                self._mark_watch_failed(task, str(exc))
        finally:
            # P0.9-1: 失败时也推进 next_scan_at（避免每 tick 重触发，
            # retry 时机完全由 next_retry_at 控制）；失败不计 scan_count
            if run is not None and run.status == ScanRunStatus.FAILED_RETRYABLE:
                self._advance(task, count_scan=False)
            if self.checkpoint is not None:
                self.checkpoint.mark_task_done(task.id)

    @staticmethod
    def _mark_watch_failed(task: WatchTask, reason: str) -> None:
        from universal_agent.core.contracts import WatchState
        task.state = WatchState.FAILED
        task.version += 1
        task.history.append({"event": "FAILED", "reason": reason})

    def _advance(self, task: WatchTask, count_scan: bool = True) -> None:
        """推进 next_scan_at（使用 task IANA 时区）。"""
        from universal_agent.coordinator.scheduler import BaselineScheduler
        if count_scan:
            task.scan_count += 1
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
