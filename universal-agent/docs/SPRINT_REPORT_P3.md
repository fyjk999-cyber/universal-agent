# SPRINT COMPLETED — P3 (Memory Completion)

> 日期：2026-08-14 · 测试基线 409 → **429 passed**

## 1. Problems fixed

| # | 问题 | 修复 |
|---|---|---|
| P3.0 | MemoryRecord 缺 user_id/profile_id/confidence | 契约补 3 字段（用户/档案隔离 + 置信度） |
| P3.1 | 8 子域只有占位目录，业务代码要手写 kind 字符串 | **MemoryDomains** 类型化访问器：intent/preference/decision/observation/answer/task_state/policy/execution_history 各成方法 |
| P3.2 | query 不支持 kind 过滤 | `SqliteMemoryRepository.query` 按 kind + expired 过滤 |
| P3.3 | Memory 未接入统一服务 | `RepositorySet.memory` 并入 UniversalAgentService |

## 2. Files changed

```
core/contracts/memory.py         (MemoryRecord + user_id/profile_id/confidence)
memory/sqlite_store.py           (put/get 支持新字段 + user_id 匹配)
memory/domains.py                (新增：MemoryDomains 8 子域访问器)
memory/__init__.py               (导出 MemoryDomains)
persistence/repos.py             (query 按 kind + expired 过滤)
service.py                       (RepositorySet.memory 接入)
tests/unit/test_p3_memory.py         (新增 11 项)
tests/unit/test_p3_memory_domains.py (新增 9 项)
```

## 3. Tests added

20 项：新字段存取 / 8 子域 roundtrip（intent/preference/decision/observation/answer/task_state/policy/execution_history）/ expired 过滤 / query kind 过滤 / 子域 query。

## 4. Tests passed

**429 passed / 0 failed**

## 5. Known limitations

- Observation 子域仍走 ObservationStore（P1 遗留），MemoryDomains.set_observation 是便捷封装
- 无 SQL 级过滤（query 全表扫描后内存过滤；数据量大时需 P4 优化）
- Policy 子域暂无 immutable 强制（Preference Learning 不应改 policy——P12 强制）

## 6. Next sprint

**P4 — Observability**（structured logs + metrics + traces + audit 指标清单）
