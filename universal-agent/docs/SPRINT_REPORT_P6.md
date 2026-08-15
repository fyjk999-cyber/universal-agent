# SPRINT COMPLETED — P6 (Source Health + Resource Governor)

> 日期：2026-08-14 · 测试基线 441 → **447 passed**

## 1. Problems fixed

| # | 问题 | 修复 |
|---|---|---|
| P6.0 | source_health 只有裸 set/get，无状态机 | **SourceHealthTracker**：success_rate/avg_latency/consecutive_failure/last_success/last_failure/parser_success/price_consistency；连续失败 HEALTHY→DEGRADED→UNAVAILABLE，成功回升 |
| P6.1 | 无资源配额（每次全平台深度全扫） | **ResourceGovernor**：api/browser/llm/verification 预算；超限拒绝；**未知资源默认拒绝（fail-closed）** |

## 2. Files changed

```
adapters/health/tracker.py   (新增：SourceHealthTracker)
adapters/health/governor.py  (新增：ResourceGovernor)
adapters/health/__init__.py  (导出)
tests/unit/test_p6_source_health.py (新增 6 项)
```

## 3. Tests passed

**447 passed / 0 failed**

## 4. Known limitations

- tracker 状态机阈值固定（degrade_after=3），未按源差异化
- 未接入 shadow_scan/scanner 调用处（P8 接线）
- governor 预算静态（后续 P12 按 Adaptive Watch 动态调整）

## 5. Next sprint

**P7 — Adaptive Watch**（AdaptiveScheduler 按时间窗口/热度调整频率 + 受 governor 约束）
