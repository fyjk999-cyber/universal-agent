"""Traces（P4）— 轻量分布式追踪（JSONL 持久化）。

每次 Scan 一个 trace_id 贯穿：Tracer.span() 上下文管理器记录
name/task_id/trace_id/duration + tags + metrics。
"""
from __future__ import annotations

import json
import logging
import time
import uuid
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("ua.observability.traces")


class _Span:
    def __init__(self, tracer: "Tracer", name: str, task_id: Optional[str],
                 run_id: Optional[str], trace_id: str) -> None:
        self.tracer = tracer
        self.name = name
        self.task_id = task_id
        self.run_id = run_id
        self.trace_id = trace_id
        self.tags: Dict[str, Any] = {}
        self.metrics: Dict[str, Any] = {}
        self._start = time.monotonic()

    def tag(self, key: str, value: Any) -> None:
        self.tags[key] = value

    def set_metric(self, key: str, value: Any) -> None:
        self.metrics[key] = value

    def __enter__(self) -> "_Span":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        duration_ms = round((time.monotonic() - self._start) * 1000, 2)
        self.tracer._write({
            "name": self.name,
            "task_id": self.task_id,
            "run_id": self.run_id,
            "trace_id": self.trace_id,
            "duration_ms": duration_ms,
            "tags": self.tags,
            "metrics": self.metrics,
            "error": str(exc) if exc else None,
        })


class Tracer:
    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)

    def new_trace_id(self) -> str:
        return f"trc_{uuid.uuid4().hex[:16]}"

    def span(self, name: str, task_id: Optional[str] = None,
             run_id: Optional[str] = None, trace_id: Optional[str] = None) -> _Span:
        tid = trace_id or self.new_trace_id()
        return _Span(self, name, task_id, run_id, tid)

    def _write(self, record: Dict[str, Any]) -> None:
        with open(self.path, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False, default=str) + "\n")

    def all_traces(self, limit: int = 100) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = self.path.read_text("utf-8").strip().splitlines()
        out = []
        for ln in lines[-limit:]:
            try:
                out.append(json.loads(ln))
            except Exception:  # noqa: BLE001
                continue
        return out
