# Universal Agent — Roadmap

> 版本路线（§27 重新定义）· 当前：**P7 Adaptive Watch 完成 → P8 Flight Live**

## 版本规划

| 版本 | 阶段 | 内容 | 状态 |
|---|---|---|---|
| v0.3 | Architecture / Shadow Runtime | 8 Phase 骨架 + 239 测试 | ✅ 完成 |
| **v0.4** | **P0 Correctness Hardening** | 时区/misfire/ScanRun/Slippage/Compensation/Idempotency/fail-closed/entity | ✅ 完成（SPRINT A + A.1，376 tests） |
| v0.5 | SQLite + Single Source of Truth | Repository Protocol + Runtime Unification（P1.1：RunLease/Host 命令边界/服务装配） | ✅ 完成（P1 + P1.1，401 tests） |
| v0.6 | Reliable Events + Persistent Watch | SQLite EventStore + Outbox + Dispatcher + Retry + DLQ | ✅ 完成（P2，409 tests） |
| v0.7 | Memory + Notification + Observability | 8 Memory 子域（P3）+ Metrics/Traces/Logs（P4） | ✅ 完成（436 tests） |
| v0.8 | Real Flight Multi-Source | Skyscanner + OTA + Airline Official（SkillProtocol 已就绪） | 待 P6-P8 |
| v0.9 | Hotel + Travel Bundle Live | Hotel 真源 + 总效用 | 待 P12 |
| v0.10 | CareerPilot Live | Job 真源 + Answer Memory | 待 P13 |
| v0.11 | Security + Controlled Prepare | CredentialVault 等 | 待 P14 |
| v0.12 | Railway | 新 Domain | 待 P15 |
| v0.13 | Ecommerce | 新 Domain | 待 P15 |
| v0.14 | Jarvis Integration Preview | Host Swap 实战 | 待 P16 |
| v1.0 | Stable Runtime | 长期 Watch 稳定 | 最终 |

## 当前 Sprint：SPRINT 0 + SPRINT A（P0）

| # | 项 | 状态 |
|---|---|---|
| 0 | 能力审计（CAPABILITY_MATRIX） | ✅ |
| A.1 | Scheduler 时区修复 + misfire | 🔲 |
| A.2 | Task 与 ScanRun 状态分离 | 🔲 |
| A.3 | Slippage Guard（approved vs actual） | 🔲 |
| A.4 | Compensation 成功路径修复 | 🔲 |
| A.5 | Idempotency reserve/finalize/reconcile | 🔲 |
| A.6 | Skyscanner fail-closed（DataCompleteness） | 🔲 |
| A.7 | Flight Entity Resolution（strong/weak） | 🔲 |
| A.8 | P0 回归测试硬化 | 🔲 |

## 禁止项（当前阶段）

- 禁止新增 Domain（Railway/Ecommerce/Food 不启动）
- 禁止接 Ctrip/Fliggy/Tongcheng
- 禁止接真实自动执行
- 每项必须先写失败测试（RED）再修复（GREEN）
