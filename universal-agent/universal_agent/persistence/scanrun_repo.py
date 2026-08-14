"""ScanRunRepository SQLite 实现（P1.3）— 独立运行状态 + 真实重试。"""
from __future__ import annotations

import json
from datetime import timedelta
from typing import List, Optional

from ..core.contracts import ScanRun, ScanRunStatus, is_retryable, new_id, utc_now
from ..core.contracts.scanrun import RETRY_BACKOFF
from .protocol import ScanRunRepository as ScanRunRepoProtocol
from .sqlite import Database


class SqliteScanRunRepository(ScanRunRepoProtocol):
    def __init__(self, db: Database) -> None:
        self.db = db

    def start(self, task_id: str, trace_id: Optional[str] = None,
              attempt: int = 1) -> ScanRun:
        run = ScanRun(run_id=new_id("run"), task_id=task_id,
                      status=ScanRunStatus.RUNNING, attempt=attempt,
                      trace_id=trace_id)
        self.db.execute(
            "INSERT INTO scan_runs (run_id, task_id, data) VALUES (?,?,?)",
            (run.run_id, run.task_id,
             json.dumps(run.model_dump(mode="json"), ensure_ascii=False)))
        return run

    def finish(self, run_id: str, status, error_type: Optional[str] = None,
               error_message: Optional[str] = None) -> ScanRun:
        run = self.get(run_id)
        if run is None:
            raise KeyError(f"scan run not found: {run_id}")
        run.status = ScanRunStatus(status)
        run.finished_at = utc_now()
        run.error_type = error_type
        run.error_message = error_message
        if run.status == ScanRunStatus.FAILED_RETRYABLE:
            run.retry_count += 1
            idx = min(run.retry_count - 1, len(RETRY_BACKOFF) - 1)
            run.next_retry_at = utc_now() + timedelta(seconds=RETRY_BACKOFF[idx])
        self.db.execute("UPDATE scan_runs SET data=? WHERE run_id=?",
                        (json.dumps(run.model_dump(mode="json"), ensure_ascii=False),
                         run_id))
        return run

    def get(self, run_id: str) -> Optional[ScanRun]:
        row = self.db.query_one("SELECT data FROM scan_runs WHERE run_id=?", (run_id,))
        if row is None:
            return None
        return ScanRun.model_validate(json.loads(row["data"]))

    def retryable(self) -> List[ScanRun]:
        """待重试 run（FAILED_RETRYABLE 且 next_retry_at <= now）。"""
        now = utc_now()
        out = []
        for run in self.list_all():
            if run.status == ScanRunStatus.FAILED_RETRYABLE and run.next_retry_at is not None:
                if run.next_retry_at <= now:
                    out.append(run)
        return out

    def latest_for(self, task_id: str) -> Optional[ScanRun]:
        runs = [r for r in self.list_all() if r.task_id == task_id]
        if not runs:
            return None
        return max(runs, key=lambda r: r.started_at)

    def list_all(self) -> List[ScanRun]:
        rows = self.db.query_all("SELECT data FROM scan_runs")
        return [ScanRun.model_validate(json.loads(r["data"])) for r in rows]
