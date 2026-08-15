# HARNESS_GOAL.md — DeepSeek Harness 托管目标

> 依据 SPAC §0.5 建立 · 更新：2026-08-14
> 角色定位：本文件描述 **DeepSeek Harness（当前 Host）** 上的 Universal Agent 实例要达成什么。
> 最高原则：DeepSeek Harness 只是 CURRENT HOST；Universal Agent 必须是 INDEPENDENT 的（RULE-001/002，ZERO CORE REWRITE 可切换到 Jarvis）。

## 1. 当前运行时状态（SPAC §51）

```
PROJECT_STATUS:      DEVELOPMENT（514 tests 全绿；SPAC 硬性点 P0×6 + P1×15 未达成——2026-08-15 深度审计修正，v1.0 验收结论过高）
CURRENT_CHAPTER:     CHAPTER 2 — DeepSeek Harness Production Integration（P0 收敛起点）
CURRENT_SUBCHAPTER:  2.1 run_task_once 真实实现（待开始）
LAST_TEST_STATUS:    PASS（514 passed / 0 failed）
BLOCKERS:            NONE
NEXT_ACTION:         P0 收敛：FR-030 run_task_once → FR-031 通知 → FR-032 审批 → FR-033 Bridge 可移植 → RULE-003 接线 → CH2 Gate（§36 Acceptance Flow）
GLOBAL_TEST_REQUIRED: TRUE（每次大 Chapter 后全量回归）
```

## 2. Host 层目标（DeepSeek Harness）

在 DeepSeek Harness 中真正可用（不是日志替身）：

1. **FR-030 命令全实现**：`create_task / update_task / pause_task / resume_task / cancel_task / run_task_once / list_tasks / get_task`，`run_task_once()` 无 `not_implemented`。
2. **FR-031 通知真实送达**：`OPPORTUNITY / PRICE_DROP / WATCH_FAILED / APPROVAL_REQUIRED / ACTION_RESULT` 到达 Harness 用户侧，不只写日志。
3. **FR-032 审批真实流转**：ActionIntent → Approval Request → 持久化 → 用户 APPROVED/DENIED → 恢复 Action Pipeline，不固定返回 `pending`。
4. **FR-033 可移植 DSH Bridge**：无硬编码 `/Users/<name>/...`；`UA_ROOT / UA_PYTHON / UA_DATA_DIR / UA_CONFIG`；配置优先级 Plugin Config → Env → Auto Discovery → Explicit Failure；禁止 silent fallback。
5. **FR-034 Harness 重启不丢 Watch**：长期 Scheduler 不依赖临时 Plugin Timer；SQLite + 恢复逻辑兜底。
6. **Acceptance Flow（SPAC §36 CHAPTER 2）**：Harness → Create Watch → Persist → Scan → Opportunity → Notification → Pause → Resume → Restart Harness → Watch Restored → Scan Continues。

## 3. 每次会话恢复协议

1. 读仓库根 `SPAC.md`（Source of Truth）。
2. 读 `universal-agent/docs/ROADMAP.md` + `CAPABILITY_MATRIX.md` + `KNOWN_LIMITATIONS.md` + `FINAL_VERIFICATION_REPORT.md` + 仓库根 `MISSING_FEATURE_REPORT.md` 恢复状态。
3. 核对 `.ai-memory/`（CURRENT_STATE/TODO/DECISIONS/TEST_STATUS/CHANGELOG）与本节 §1 状态一致。
4. 若 `GLOBAL_TEST_REQUIRED=TRUE`：先跑全量回归（`cd universal-agent && ../.venv/bin/python -m pytest -q`），确认 0 failed 再继续开发。
5. 继续 CHAPTER 路线（见 ROADMAP Chapter 完成度）。

## 4. 铁律（对 Harness 自身）

- 不得让 Core 反向依赖 DeepSeek Harness（RULE-001）。
- 不得在 Core 之外建立第二套 Runtime Truth（RULE-003）。
- 不得绕过 ActionGateway / Approval / KillSwitch 执行外部副作用（RULE-007/008，FR-180）。
- 架构变更必须 STOP → 更新 SPAC/DECISIONS → RELOCK（SPAC §52）。
- 禁止为"看起来完成"而完成（SPAC §56）。
