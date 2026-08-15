# Known Limitations

> 更新：**2026-08-14**（v1.0 FINAL VERIFICATION ACCEPTED 后重写）
> 声明：**基于实际代码审计**（`universal_agent/` 源码 + 测试 + FINAL_VERIFICATION_REPORT.md，非 README 声明）。
> 复核基线：**514 tests / 0 failed**（2026-08-14 复核通过）。
> 原则：已实现的不写成未实现，未实现的不写成已实现；剩余缺口全部如实列出并按 Severity 分级。

## ✅ 已解决（v1.0 前）

以下旧问题已被 SPRINT A / A.1 / P0~P22 修复并测试锁定：

| # | 旧问题 | 修复（Sprint） |
|---|---|---|
| 1 | Scheduler 忽略 task timezone；due 用 `"09:00"<="21:00"` 字符串比较 | IANA `ZoneInfo` + `due_tasks_utc` datetime 比较（A / A.1） |
| 2 | 无 misfire 处理 | `MisfirePolicy`（SKIP / RUN_ONCE / CATCH_UP_LIMITED，默认 RUN_ONCE）（A） |
| 3 | 平台临时失败 → Watch 永久 FAILED | `ScanRun` 独立状态 FAILED_RETRYABLE + backoff（1m/5m/15m/1h），Watch 保持 WATCHING（A / P1） |
| 4 | retry 不真正由 next_retry_at 驱动（每 tick 重复触发） | retry chain 跨重启 + RunGuard 防 baseline/retry 双启动（A.1） |
| 5 | Slippage 自比较 `(confirmed, confirmed)` | `SlippageGuard(approved, actual)` + approved_* 快照 + material change → BLOCK（A） |
| 6 | 成功路径调用 compensation | 成功 → FINALIZE，绝不补偿；仅 FAIL/UNKNOWN 补偿（A） |
| 7 | Idempotency 仅后置 register | reserve→commit→finalize 状态机 + reconcile（crash 后 UNKNOWN → 查平台防双订单）（A / A.1） |
| 8 | Skyscanner 硬编码 stops=0 获直飞加分（fail-open） | fail-closed：stops=-1 + `DataCompleteness` + 中性分（A / A.1：duration-only 恒 PARTIAL） |
| 9 | Flight Entity Resolution 缺字段错误合并 | strong/weak key + `ResolutionConfidence`（MATCH 才 merge）（A / A.1：round-trip 双方向非空才 Strong） |
| 10 | PARTIAL 结果可进 Final Top5 / 触发购买 | `RankEligibility` Gate：PARTIAL → PRELIMINARY，不进 Final Top5 / 无购买建议 / 不进 ActionPlan（A.1） |
| 11 | 审批过期/offer/quote/材料变化未校验 | Approval Snapshot 校验 → REAPPROVAL_REQUIRED（A.1） |
| 12 | 双 L3/L4 执行路径（安全缺口） | 唯一路径 `TransactionExecutor`；ControlledExecutor 降为 deprecated wrapper（A.1） |
| 13 | JSON dual state（task_registry.json / scan_runs） | SQLite 唯一 Runtime Truth（P1 / P1.1） |
| 14 | HarnessHostAdapter 保存 Task 真相（双份） | TaskCoordinator 命令模式：Host 只发 Command，StateMachine 校验（P1） |
| 15 | 多进程同 Task 双运行 | RunLease（DB 互斥，run_leases 表）（P1.1） |
| 16 | Transaction external-call 结果歧义 | UNKNOWN → reconcile 三分支（CONFIRMED / NOT_FOUND / UNKNOWN）（P1.1） |
| 17 | 事件仅进程内，无可靠持久投递 | SQLite EventStore + Transactional Outbox + Dispatcher + Retry + DLQ（P2） |
| 18 | Memory 8 子域空占位 | MemoryDomains 类型化访问器 + scope/confidence/expired（P3） |
| 19 | 无 metrics / traces / structured logs | MetricsRegistry + Tracer + StructuredLog（P4） |
| 20 | Skill 方法无标准接口 | SkillProtocol（search/detail/verify/availability/prepare_action/health_check，**无 execute**）+ CapabilityResolver（P5） |
| 21 | Source Health 裸 set/get，无状态机 | SourceHealthTracker（HEALTHY→DEGRADED→UNAVAILABLE）+ ResourceGovernor fail-closed（P6） |
| 22 | AdaptiveScheduler 为 NoOp 骨架 | RuleAdaptiveScheduler（时间窗口频率 + HOT 加速受 governor 约束）（P7） |
| 23 | Flight 无 Live 闭环 | Skyscanner SkillProtocol 垂直闭环（Search→Normalize→Candidate→Score→Top5→Opportunity→Notification）（P8） |
| 24 | Hotel 无政策归一化 | HotelPolicy（breakfast/cancellation/tax/occupancy，未知=UNKNOWN）（P9） |
| 25 | Bundle 简单 cheapest+cheapest | 总效用优化（约束下非贪心）（P10） |
| 26 | Opportunity 无 availability / trend | availability（HIGH/MEDIUM/LOW/UNKNOWN）+ trend estimate（is_estimate=true）（P11） |
| 27 | 无偏好学习 / 不可解释 / 不可逆 | PreferenceLearner：versioned / explainable / reversible，不碰 Policy（P12） |
| 28 | Job 无通用接口、无 human-only 边界 | JobSkillProtocol + is_human_only（personality/identity/法律敏感禁代答）（P13） |
| 29 | 无凭据存储 / 无权限管理 | CredentialVault（明文不落盘）+ PermissionManager（默认拒绝）（P14） |
| 30 | L2 PREPARE 未验证三类场景 | flight/jobs/ecommerce 全通过（到确认页/提交前/Checkout 前，No Commit）（P15） |
| 31 | 安全控制链未全链验证 | KillSwitch / Idempotency 防双 / Slippage / Compensation / Audit 全链验证（P16） |
| 32 | Railway/Ecommerce/Food 空占位 | Raw 契约 + normalize + entity_key（复用 Core，零 Core 修改）（P17–19） |
| 33 | Jarvis 未端到端 | Host Swap 全链路（状态跨 Host 保留，Core 零修改）（P20） |
| 34 | 无 CI / 依赖不可复现 | GitHub Actions（3.11+3.12）+ pyproject 依赖组（dev/browser/flight-live/hotel-live/jobs-live）（P21/22） |
| 35 | NotificationDedup 内存态，重启遗忘 | dedup fingerprint + cooldown 持久化（P0.8）+ notifications 表（P1） |
| 36 | `due_tasks(string)` 生产路径残留 | 删除，生产路径全用 `due_tasks_utc`（A.1） |

## ⚠️ 当前已知限制（未解决，v1.0 后仍存在）

> 按 Severity 分级；P0 = 必修（安全/正确性），P1 = 高，P2 = 中，P3 = 低。
> v1.0 验收确认**无未披露 P0/P1**；下表为已披露的剩余缺口。

### P0（无未披露项）

v1.0 验收（28 项 Final Acceptance Criteria）+ 2026-08-15 代码审计：**无未披露 P0**。

### P1（高优先级，已披露）

| 限制 | 对应 FR | 影响 |
|---|---|---|
| **DeepSeek Harness 生产集成未完成**：`run_task_once()` 仍返回 `{"status": "not_implemented"}`；`send_notification` 仅写日志；`request_approval` 固定返回 pending | FR-030 / FR-031 / FR-032 | Harness 侧无法真正执行单次扫描 / 真实通知 / 真实审批流转（CHAPTER 2 = PARTIAL；已由 FINAL_VERIFICATION_REPORT 2026-08-15 审计补充披露） |
| **DSH Bridge 硬编码路径**：`dsh/uabrg-plugin.js` 硬编码 `/Users/huhongjie/...`，未接 `UA_ROOT/UA_PYTHON/UA_DATA_DIR/UA_CONFIG`，换机器需改代码 | FR-033 | 不可移植；违反 FR-033「禁止 silent fallback 到开发者机器路径」 |
| **第二/第三 Flight Live Source 未接**：Skyscanner 是唯一 Flight Live 源；Ctrip/Fliggy/Tongcheng 无 Live adapter | FR-074 | 无跨平台交叉验证；单源故障无备份（CHAPTER 4 = PARTIAL） |
| **CredentialVault 为 dev 混淆，非生产级**：base64+XOR、固定 dev key，明文仅受轻量混淆保护 | FR-191 / FR-192 | 生产部署应接 macOS Keychain / Windows Credential Manager；当前不满足 FR-191/192（CHAPTER 8 = PARTIAL） |
| **Hotel 无真实 Live Source**：HotelScanCoordinator + 政策归一化已实现，但仅 replay 数据，无真实 Hotel adapter | FR-082 | 无法与真实平台对照验证；不满足 CH 4.4 |
| **通用 Adapter 层为空占位**：`adapters/{http,api,browser}/` 仅 `__init__.py`，无 HTTP/API/Browser Adapter 实现 | FR-060 / FR-061 / FR-062 | 新源接入只能靠手写 adapter；Browser 深度（登录态/验证）未覆盖（CHAPTER 3 = PARTIAL） |
| **Jobs 无真实 Live Source**：官方 Careers / LinkedIn / SEEK 仅 `JobSkillProtocol` 契约，无真实适配器 | FR-100 / FR-101 | Jobs 管线可用但无真实数据（CHAPTER 6 = PARTIAL） |

### P2（中优先级）

| 限制 | 对应 FR | 影响 |
|---|---|---|
| **Skyscanner search 为 duration-only PARTIAL**：搜索页无完整航段，stops=-1；detail/verify/availability 为安全占位（未接真实详情页） | FR-073 / FR-052 / FR-053 | 合规 fail-closed，但 Top 推荐永远缺 STRUCTURED 数据；详情页补齐后（v1.2 #13）可升级 |
| **Railway / Ecommerce / Food 仅完成域骨架**：Raw 契约 + normalize + entity_key 已实现，Constraint/Score/Skill/Source/Verify/Watch/Notification 未做 | FR-110~117 等 | 域存在但无 Live 能力（CHAPTER 7 = PARTIAL） |
| **Mobile Adapter 为空占位**：连第一阶段要求的 Protocol/Contract 都未定义 | FR-063 | 移动端接入无从谈起（CH 3.4 未开始） |
| **Notification priority/channel 未完整**：dedup 有 cooldown，但无 LOW/NORMAL/HIGH/URGENT 分级、无 Harness/Desktop/Mobile/Webhook/Jarvis 通道抽象 | FR-162 / FR-163 | 通知分级与多通道无法实现 |
| **Outbox Dispatcher 为拉模式，未接 daemon 后台循环**：dispatch_once/run_forever 已实现，但 WatchDaemon 未自动驱动；RunLease 无 heartbeat 后台线程（renew 由调用方负责） | FR-021 / FR-014 | 事件投递/租约续期依赖调用方主动触发 |
| **Tier3 官方源为骨架**：`adapters/official/registry.py` 仅注册器 + 健康检查，无真实航司适配器（合规：不登录/不购买/不绕过验证码） | FR-052（Tier3） | 官方渠道交叉验证不可用 |
| **Jobs 提交被 ActionGateway 拒绝**（IRREVERSIBLE）：`build_application_plan` 为 L1 且 IRREVERSIBLE，提交类操作被网关拦下 | FR-102 / FR-173 | 应用提交为设计边界，但在 L3/L4 稳定前无真实提交通道 |
| **PreferenceLearner 固定用户 u1**：多用户隔离未验证 | FR-150 / FR-152 | 多用户场景偏好会串 |

### P3（低优先级）

| 限制 | 对应 FR | 影响 |
|---|---|---|
| Metrics 未全链路自动埋点（scanner/daemon/action 处需手动 increment） | Observability（§31） | 指标覆盖依赖人工接入 |
| Traces 无父子 span 关联图（仅 trace_id 分组）；无 OpenTelemetry 导出 | Observability（§31） | 深链路排查能力有限（按计划轻量自研） |
| SourceHealthTracker 阈值固定（degrade_after=3），未按源差异化 | FR-055 | 不同源健康恢复速度不可调 |
| HOT Watch 判定来自 meta 静态标记，未由 Opportunity Engine 动态标记 | FR-140 相关 | 加速需人工标记 |
| PreferenceLearner 学习规则简单（±0.05），无趋势加权 | FR-152 | 学习精度有限（v1.3+ 计划） |

## 🧱 设计边界（非缺陷，勿当缺陷修复）

- **真实支付 / 自动执行默认 DENY**：所有高风险操作 DEFAULT = DENY（RULE-008）；只有 Policy + Approval + 有效 Quote Snapshot + Slippage Check + Idempotency + Executor 全部满足才允许（FR-173）。这是安全设计，不是缺口。
- **Tier3 官方源为合规骨架**：只做公开价格查询页验证；不登录、不购买、不绕过验证码（SPAC §33 Non-Goals）。
- **LLM 不进核心确定性链**：Filter/Dedup/Normalize/Entity/Constraint/Score/Rank/Change Detection/Policy 全部程序化（RULE-005）；LLM 只辅助 Intent Parsing / Semantic Reasoning / Explanation / Summary / Preference Extraction。
- **Jobs 提交流程 Human 兜底**：personality/psychology/identity/truthfulness 声明类题目默认 Human-only（FR-104），系统不代答。
- **SQLite 优先，无 PostgreSQL**：第一阶段按计划 SQLite + WAL；Repository Protocol 保留替换。
- **无 Kafka/Redis/OpenTelemetry**：EventBusProtocol / 轻量自研 observability 保留替换，不引入重依赖。
- **Observation ≠ Evidence ≠ Decision**：Decision 必须引用 supporting_evidence[]（RULE-006 / FR-132），禁止「LLM 认为价格是 X」直接成为事实。

---

## 附录：v1.0 剩余缺口 → 下一阶段

所有 P1 缺口（CHAPTER 2 FR-030~033、FR-074 多源、FR-191/192 生产凭据、FR-082 Hotel Live、FR-060~062 Adapter、FR-100/101 Jobs Live）已列入 [`ROADMAP.md`](ROADMAP.md)「下一阶段路线（v1.1+）」并给出优先级；由 `MISSING_FEATURE_REPORT.md` 持续跟踪。
