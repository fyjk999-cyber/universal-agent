# PHASE 5 — CareerPilot Migration Test 验收报告

> 日期：2026-08-14 · 环境：Python 3.12 · pytest 9.1.1

---

## PHASE COMPLETED

**Implemented（§64/§65 — Job Domain 接入，Core 零修改）**
- `core/contracts/raw.py` — `RawJob` 契约（title/company/location/job_reference/salary/skills）
- `domains/jobs/`：
  - `knowledge.py` — Job Entity Resolution key（company|title|location|job_reference，§21）+ 技能匹配度 + 薪资中位
  - `normalize.py` — RawJob → Candidate/Offer/Quote/Evidence（薪资作 Quote）
  - `scoring.py` — 确定性评分（匹配度 50% / 薪资 30% / 可信度 20%）
  - `action.py` — **Application ActionPlan**（§36 build-only，IRREVERSIBLE §40）+ **Answer Memory**（§64 TASK scope）
- `coordinator/scanner/job.py` — JobScanCoordinator（复用 Core EventBus/ObservationStore/Registry 健康降级）
- `tests/replay/fixtures/linkedin.json` — Job 回放 fixture

**Tests（+12）— CareerPilot Migration Test（§64/§65 正式验收）**
| 测试类 | 内容 |
|---|---|
| TestJobNormalize (3) | entity key / 归一化到 Core 契约 / 确定性评分 |
| TestJobWatch (2) | **Job Watch 复用 Core 状态机 + WatchManager** |
| TestJobScan (2) | Job 扫描管线（事件链）/ 源失败降级 |
| TestApplicationActionPlan (2) | build-only（无 execute）/** Gateway 拒绝 IRREVERSIBLE Job 提交** |
| TestAnswerMemory (1) | Answer 存 TASK scope 并可取回 |
| TestZeroCoreChanges (2) | **Core 模块 import 未修改 + Core 不 import jobs 域（RULE 3 隔离）** |

**端到端实测（fixture 回放）**
```text
1. Job Watch: WATCHING        (Core WatchManager 处理 Job task)
2. Job 扫描: 3 职位 → Top3: AI Engineer@DeepMind / ML@Alibaba / Backend@ByteDance
3. Gateway 拒绝 Job 提交（§40 IRREVERSIBLE，V1 正确拦截）
4. Answer Memory: answer | scope: TASK
```

**验收核心（§64）**
- Universal Core 直接处理 Job Candidate / Multiple Listings / Job Watch /
  Application ActionPlan / Answer Memory —— **无需修改任何 Core 代码**
- 反向验证：Core 不 import `domains.jobs`（grep 确认 CLEAN）
- 若需大改 Core 才通过 → 本测试即失败信号（当前通过）

**Known limitations**
- Job 数据源为 fixture 回放（真实 LinkedIn/招聘源接入属后续——需登录/风控，§56 限制）
- ActionPlan 只 build 不执行（正确）；PREPARE 到提交前是 Phase 6 范围
- 薪资匹配度为静态规则；偏好学习（§55）在 Phase C

**Security / 合规**
- Job 提交 IRREVERSIBLE → Gateway 硬拦截（§40/§56，无自动申请）
- 无登录/凭据/绕过验证码
- SHADOW MODE 保持

**Host coupling audit**：CLEAN ✓（Core/domains/coordinator 均无 hosts 依赖）

**Migration compatibility**
- Jarvis Host Swap Test 继续通过（198 全绿）
- **CareerPilot Migration Test 通过：Universal Core 对 Job 域零修改**（§64 验收达成）

**Next phase**
- **PHASE 6 — Action Preparation**：只实现 PREPARE（机票→确认页 / Job→提交前 /
  购物→结算页），不真正 Commit；需先补 Idempotency/Slippage/Approval/Audit 骨架
