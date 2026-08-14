"""ScanRunRepository — 独立运行状态存储（P0.2）。

WatchTask 生命周期与 ScanRun 分离：平台临时失败只记录到 ScanRun，
绝不把 Watch 置 FAILED。JSON 持久化（P1 迁 SQLite）。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from ...core.contracts import ScanRun, ScanRunStatus, is_retryable, new_id, utc_now
from ...core.contracts.scanrun import RETRY_BACKOFF

log = logging.getLogger("ua.scanruns")


class ScanRunRepository:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "scan_runs.json"
        self._runs: Dict[str, ScanRun] = {}
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                raw = json.loads(self._file.read_text("utf-8"))
                self._runs = {k: ScanRun.model_validate(v) for k, v in raw.items()}
            except Exception:  # noqa: BLE001
                log.warning("scan_runs.json corrupt; starting empty")

    def _save(self) -> None:
        self._file.write_text(
            json.dumps({k: v.model_dump(mode="json") for k, v in self._runs.items()},
                       ensure_ascii=False, indent=2), "utf-8")

    def start(self, task_id: str, trace_id: Optional[str] = None,
              attempt: int = 1) -> ScanRun:
        run = ScanRun(run_id=new_id("run"), task_id=task_id,
                      status=ScanRunStatus.RUNNING, attempt=attempt,
                      trace_id=trace_id)
        self._runs[run.run_id] = run
        self._save()
        return run

    def start_retry(self, task_id: str, parent_run_id: str,
                    trace_id: Optional[str] = None) -> ScanRun:
        """P0.9-1: 创建重试 run，继承 parent 的 retry chain（跨重启恢复）。"""
        parent = self._runs.get(parent_run_id)
        retry_count = 1
        if parent is not None:
            retry_count = parent.retry_count + 1
        run = ScanRun(
            run_id=new_id("run"), task_id=task_id,
            status=ScanRunStatus.RUNNING, attempt=parent.attempt + 1 if parent else 2,
            retry_count=retry_count,
            retry_of_run_id=parent_run_id,
            parent_run_id=parent.parent_run_id or parent_run_id if parent else parent_run_id,
            trace_id=trace_id)
        self._runs[run.run_id] = run
        self._save()
        return run

    def finish(self, run_id: str, status: ScanRunStatus,
               error_type: Optional[str] = None,
               error_message: Optional[str] = None) -> ScanRun:
        run = self._runs.get(run_id)
        if run is None:
            raise KeyError(f"scan run not found: {run_id}")
        run.status = status
        run.finished_at = utc_now()
        run.error_type = error_type
        run.error_message = error_message
        if status == ScanRunStatus.FAILED_RETRYABLE:
            run.retry_count += 1
            idx = min(run.retry_count - 1, len(RETRY_BACKOFF) - 1)
            delay = RETRY_BACKOFF[idx]
            from datetime import timedelta
            run.next_retry_at = utc_now() + timedelta(seconds=delay)
        self._save()
        return run

    def retryable(self) -> List[ScanRun]:
        """待重试的 run（FAILED_RETRYABLE 且 next_retry_at <= now）。"""
        now = utc_now()
        out = []
        for r in self._runs.values():
            if r.status == ScanRunStatus.FAILED_RETRYABLE and r.next_retry_at is not None:
                if r.next_retry_at <= now:
                    out.append(r)
        return out

    def latest_for(self, task_id: str) -> Optional[ScanRun]:
        for r in sorted(self._runs.values(), key=lambda x: x.started_at, reverse=True):
            if r.task_id == task_id:
                return r
        return None

    def list_all(self) -> List[ScanRun]:
        return list(self._runs.values())


def classify_error(exc: Exception) -> str:
    """把异常归类为可重试/致命类型（P0.2 规则）。"""
    name = type(exc).__name__
    msg = str(exc).lower()
    if name in ("SourceUnavailable", "TimeoutError", "ConnectionError"):
        return "source_unavailable"
    if "rate" in msg or "429" in msg:
        return "rate_limit"
    if "browser" in msg or "crash" in msg:
        return "browser_crash"
    if "schema" in msg or "validation" in msg or "invalid task" in msg:
        return "fatal_validation"
    return "temporary_error"  # 默认临时性，可重试


def is_fatal(exc: Exception) -> bool:
    """致命错误：invalid task / schema corruption / fatal policy violation。"""
    return classify_error(exc) == "fatal_validation"
