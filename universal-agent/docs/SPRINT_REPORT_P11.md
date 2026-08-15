# SPRINT COMPLETED — P11 (Opportunity Engine 增强)

> 日期：2026-08-14 · 测试基线 468 → **471 passed**

## 1. Problems fixed

| # | 问题 | 修复 |
|---|---|---|
| P11.0 | 无 availability（库存风险）信号 | OpportunityInput.availability（HIGH/MEDIUM/LOW/UNKNOWN）→ 机会分 +8/+4/+0 |
| P11.1 | 无趋势层 | trend 字段传递 momentum/volatility，**is_estimate=true**（预测非事实，不改变历史判定） |

## 2. Files changed

```
core/contracts/scoring.py       (OpportunityScore + availability/trend)
core/opportunity/engine.py      (availability 加分 + trend estimate 传递)
tests/unit/test_p11_opportunity.py (新增 3 项)
```

## 3. Tests passed

**471 passed / 0 failed**

## 4. Next sprint

**P12 — Preference Learning**（从 Decision Memory 学习价格/时间敏感度、平台偏好；versioned/explainable/reversible；不得改 Policy）
