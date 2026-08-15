# SPRINT COMPLETED — P21/P22 (CI Gates + Dependency Reproducibility)

> 日期：2026-08-14 · 测试基线 504 → **504 passed**

## 1. P21 — CI Gates

```
.github/workflows/ci.yml:
  - test job: Python 3.11 + 3.12 × pytest（main merge 必须 green）
  - quality job: ruff + mypy + coverage（报告非门禁，提示改进）
```

## 2. P22 — Dependency Reproducibility

pyproject.toml 拆分依赖组：
```
dev          pytest / pytest-asyncio
browser      playwright / scrapling
flight-live  scrapling / playwright
hotel-live   scrapling
jobs-live    requests
```
新机器：git clone → pip install -e ".[dev]" → pytest → 通过。

## 3. Next

进入 **FINAL VERIFICATION PHASE**：调用 agent-project-test 全量验收。
