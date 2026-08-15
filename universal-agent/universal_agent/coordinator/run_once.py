"""run_once — FR-030 单次扫描执行（Host `run_task_once()` 的 Core 侧实现）。

与 `WatchDaemon._run_task` 同语义：执行一次扫描并记录 ScanRun
（SUCCESS / FAILED_RETRYABLE / FAILED_FATAL），供 Host 适配器调用。
"""
from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable, Dict, Optional

from universal_agent.core.contracts import ScanRunStatus, WatchTask
from universal_agent.coordinator.task_registry.scanruns import classify_error, is_fatal

#: 扫描执行器（与 WatchDaemon.ScanRunner 同构）：task → 结果摘要
ScanRunner = Callable[[WatchTask], Awaitable[Dict]]


async def run_once_async(task: WatchTask, runner: ScanRunner,
                         scan_runs=None, task_repo=None) -> Dict[str, Any]:
    """执行一次扫描并记录 ScanRun（异步；供 daemon/事件循环内使用）。

    失败语义与 daemon 一致：可重试错误 → FAILED_RETRYABLE（Watch 保持有效），
    致命错误 → FAILED_FATAL。异常向上抛出，由调用方决定如何处理。
    成功后与 WatchDaemon._advance 同语义推进调度（scan_count/last_scan_at/
    next_scan_at，基于 task IANA 时区），经 task_repo 持久化。
    """
    run = None
    if scan_runs is not None:
        run = scan_runs.start(task.id, attempt=task.scan_count + 1)
    try:
        result = await runner(task)
    except Exception as exc:  # noqa: BLE001 — 与 daemon._run_task 一致
        if run is not None:
            status = (ScanRunStatus.FAILED_FATAL if is_fatal(exc)
                      else ScanRunStatus.FAILED_RETRYABLE)
            scan_runs.finish(run.run_id, status,
                             error_type=classify_error(exc), error_message=str(exc))
        raise
    if run is not None:
        scan_runs.finish(run.run_id, ScanRunStatus.SUCCESS)
    # 推进调度（与 WatchDaemon._advance 一致；经 Core 代码，非 Host 直改）
    _advance(task, task_repo=task_repo)
    return {"task_id": task.id, "status": "completed", "result": result}


def _advance(task: WatchTask, task_repo=None) -> None:
    """推进 next_scan_at（task IANA 时区）；成功扫描计入 scan_count。"""
    from datetime import datetime, timezone
    from universal_agent.coordinator.scheduler import BaselineScheduler

    task.scan_count += 1
    task.last_scan_at = datetime.now(timezone.utc)
    run = BaselineScheduler().next_run(task)
    task.next_scan_at = run.at if run else None
    if task_repo is not None:
        task_repo.update(task)


def run_once(task: WatchTask, runner: ScanRunner, scan_runs=None,
             task_repo=None) -> Dict[str, Any]:
    """同步入口（Host 协议层用）。

    若调用方已在事件循环内（如 DSH 异步上下文），请使用 `run_once_async`。
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return asyncio.run(run_once_async(task, runner, scan_runs, task_repo))
    raise RuntimeError(
        "run_once() called from a running event loop; use run_once_async() instead")
