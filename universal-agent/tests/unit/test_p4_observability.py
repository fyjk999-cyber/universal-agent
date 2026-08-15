"""P4 — Observability：metrics + traces + structured logs + audit 指标。

指令要求的指标（至少）：
scan_duration / source_latency / source_success_rate / candidate_count /
entity_resolution_rate / verification_rate / browser_calls / api_calls /
llm_tokens / estimated_cost / notification_count / retry_count /
lease_conflict_count / event_delivery_failure / action_block_count

验收：
1. MetricsRegistry 记录/增量/读取这些指标
2. Tracer 生成 trace_id，span 可嵌套（贯穿一次 scan）
3. StructuredLog 输出 JSON 行日志
4. Audit 已存在（指标合并验证）
"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_metrics_registry_increment_and_read(tmp_path: Path) -> None:
    from universal_agent.observability.metrics import MetricsRegistry
    m = MetricsRegistry(Path(tmp_path) / "metrics.json")
    m.increment("browser_calls")
    m.increment("browser_calls")
    m.increment("api_calls", delta=3)
    m.set("scan_duration", 12.5)
    assert m.get("browser_calls") == 2
    assert m.get("api_calls") == 3
    assert m.get("scan_duration") == 12.5


def test_metrics_persist_across_restart(tmp_path: Path) -> None:
    from universal_agent.observability.metrics import MetricsRegistry
    path = Path(tmp_path) / "metrics.json"
    m1 = MetricsRegistry(path)
    m1.increment("candidate_count", delta=42)
    m2 = MetricsRegistry(path)  # 重启
    assert m2.get("candidate_count") == 42


def test_all_required_metric_keys_exist(tmp_path: Path) -> None:
    from universal_agent.observability.metrics import REQUIRED_METRICS
    from universal_agent.observability.metrics import MetricsRegistry
    m = MetricsRegistry(Path(tmp_path) / "m.json")
    for k in REQUIRED_METRICS:
        m.increment(k, delta=1)  # 全部可记录
        assert m.get(k) == 1, f"metric missing or wrong: {k}"


def test_tracer_span_and_trace_id(tmp_path: Path) -> None:
    from universal_agent.observability.traces import Tracer
    t = Tracer(Path(tmp_path) / "traces.jsonl")
    with t.span("scan", task_id="t1") as span:
        span.tag("source", "bing")
        span.set_metric("candidate_count", 30)
    traces = t.all_traces()
    assert len(traces) == 1
    tr = traces[0]
    assert tr["name"] == "scan"
    assert tr["task_id"] == "t1"
    assert tr["metrics"]["candidate_count"] == 30
    assert "duration_ms" in tr or "duration_s" in tr


def test_trace_id_flows_into_event(tmp_path: Path) -> None:
    """trace_id 贯穿：Tracer → EventEnvelope。"""
    from universal_agent.events.envelope import EventEnvelope
    from universal_agent.events.types import EventType
    from universal_agent.observability.traces import Tracer
    t = Tracer(Path(tmp_path) / "traces.jsonl")
    with t.span("scan", task_id="t1") as span:
        evt = EventEnvelope(event_type=EventType.SCAN_COMPLETED,
                            trace_id=span.trace_id, task_id="t1", source="test")
        assert evt.trace_id == span.trace_id


def test_structured_log_json_lines(tmp_path: Path) -> None:
    import json as _json
    from universal_agent.observability.logs import StructuredLog
    log = StructuredLog(Path(tmp_path) / "app.jsonl")
    log.info("scan done", task_id="t1", source="bing", candidates=30)
    lines = (Path(tmp_path) / "app.jsonl").read_text().strip().splitlines()
    assert len(lines) == 1
    obj = _json.loads(lines[0])
    assert obj["event"] == "scan done"
    assert obj["task_id"] == "t1"
    assert obj["candidates"] == 30


def test_audit_metric_keys(tmp_path: Path) -> None:
    """Audit 记录六要素（actor/action/reason/based_on/approved/result）。"""
    from universal_agent.observability.audit import AuditLog
    a = AuditLog(Path(tmp_path) / "audit")
    a.record(actor="user", action="approve", reason="price ok",
             based_on={"price": 3659}, approved=True, task_id="t1")
    entries = a.entries()
    assert len(entries) == 1
    for k in ("ts", "actor", "action", "reason", "based_on", "approved", "result"):
        assert k in entries[0]
