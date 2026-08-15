# SPAC.md

Universal Persistent Watch & Decision Platform

Project: fyjk999-cyber/universal-agent
Project Class: LONG
Primary Development Skill: free-dp-pro
Current Host: DeepSeek Harness
Future Host: Jarvis
Architecture Mode: Host-Agnostic / Contract-First / Event-Driven / Replaceable
Document Role: Product + Architecture + Functional Requirement Source of Truth

---

## 1. Product Vision

Universal Agent 是一个长期存在的个人扫描、监控与决策基础设施。

它不是：

* 单一机票搜索工具
* 单一酒店搜索工具
* 单一求职 Agent
* 单一购物 Agent
* 单一浏览器自动化 Agent

这些只是 Universal Agent 上运行的不同 Domain。

完整长期工作循环：

REMEMBER
→ WATCH
→ OBSERVE
→ NORMALIZE
→ COMPARE
→ VERIFY
→ DECIDE
→ NOTIFY
→ PREPARE
→ APPROVE
→ ACT
→ VERIFY ACTION
→ LEARN
→ REMEMBER

系统应允许用户提出类似：

8 月 30 日到 9 月 3 日准备去 Queenstown。
持续关注：
- 上海 / 杭州 → Queenstown 的机票
- Queenstown 酒店
- 多个平台价格
如果发现明显低于历史价格、
综合性价比明显提升或稀缺库存，
主动通知我。
如果未来授权，
可以自动推进到预订确认页，
但高风险操作必须经过审批。

系统随后长期运行，而不是只进行一次搜索。

---

## 2. Product Positioning

产品正式定位：

Universal Persistent Watch & Decision Infrastructure

核心价值不是"搜索"，而是：

持续观察
+
多来源扫描
+
统一标准化
+
历史比较
+
机会发现
+
决策
+
通知
+
受控执行
+
长期记忆

Universal Agent 负责：

REMEMBER
WATCH
SCAN
NORMALIZE
VERIFY
COMPARE
SCORE
RANK
DECIDE
NOTIFY
PREPARE
CONTROLLED ACTION
AUDIT

---

## 3. Core Architecture

目标架构：

                 User
                   │
                   ▼
        DeepSeek Harness / Jarvis
                   │
                   ▼
             Host Adapter
                   │
                   ▼
              HostProtocol
                   │
                   ▼
        UniversalAgentService
                   │
        ┌──────────┼──────────┐
        ▼          ▼          ▼
 TaskCoordinator  Memory    Scheduler
        │          │          │
        └──────────┼──────────┘
                   ▼
            Universal Core
                   │
     ┌─────────────┼─────────────┐
     ▼             ▼             ▼
 Query Planner  Source Planner  Scanner
     │             │             │
     └─────────────┼─────────────┘
                   ▼
              Skill Runtime
                   │
            Adapter Layer
                   │
     ┌─────────────┼─────────────┐
     ▼             ▼             ▼
    API          Browser        HTTP
                   │
                   ▼
            External Platforms
                   │
                   ▼
             Raw Observation
                   │
                   ▼
               Normalize
                   │
                   ▼
          Candidate / Evidence
                   │
                   ▼
         Constraint / Scoring
                   │
                   ▼
           Verification
                   │
                   ▼
             Opportunity
                   │
                   ▼
              Decision
                   │
          ┌────────┴────────┐
          ▼                 ▼
     Notification       ActionIntent
                            │
                            ▼
                      ActionGateway
                            │
                      Policy Engine
                            │
                         Approval
                            │
                    TransactionExecutor

---

## 4. Non-Negotiable Architecture Rules

RULE-001 — Host Independence

Universal Agent Core 不得依赖：

* DeepSeek Harness
* Jarvis
* OpenCode
* Codex
* 其他具体 Host

依赖方向只能是：

Host
→ HostAdapter
→ HostProtocol
→ Universal Agent

禁止：

Universal Core
→ DeepSeek Harness

---

RULE-002 — Jarvis Replaceability

未来切换：

DeepSeek Harness
→ Jarvis

只允许新增或替换：

JarvisHostAdapter

不得因此重写：

* Core
* Memory
* Scheduler
* Domain
* Skill Runtime
* Persistence
* Action Gateway

---

RULE-003 — SQLite Runtime Truth

SQLite 是 Runtime State 的唯一事实源。

以下状态不得存在第二套可写真相：

* WatchTask
* ScanRun
* Memory
* Events
* Outbox
* Notification
* Approval
* Action
* Idempotency
* Source Health
* Execution State

JSON / JSONL 只能用于：

* Export
* Debug
* Log
* Snapshot
* Metrics

不能作为第二 Runtime State。

---

RULE-004 — Host Does Not Own Task Truth

所有 WatchTask 状态修改必须经过：

Host
→ TaskCoordinator
→ StateMachine
→ TaskRepository

Host 不允许直接修改 Repository。

---

RULE-005 — Deterministic Core

以下流程必须优先程序化：

Filter
Dedup
Normalize
Entity Resolution
Constraint
Score
Rank
Change Detection
Price Calculation
Availability
Policy

LLM 不得成为这些逻辑的唯一实现。

---

RULE-006 — Observation / Evidence / Decision Separation

必须保持：

Observation
≠
Evidence
≠
Decision

外部平台产生 Observation。

Verification 后得到 Evidence。

Decision 必须基于 Evidence。

禁止：

"LLM认为当前价格是 ¥1000"

直接成为事实。

---

RULE-007 — External Side Effects

所有外部副作用必须经过：

ActionGateway

禁止 Skill、Domain、Scanner 直接执行高风险操作。

---

RULE-008 — Default Deny

所有高风险操作：

DEFAULT = DENY

只有明确 Policy + Approval 满足时才允许执行。

---

RULE-009 — Fail Closed

数据不完整时：

PARTIAL
UNKNOWN
UNVERIFIED

不得自动脑补为完整数据。

---

RULE-010 — Traceability

所有重要行为必须：

Traceable
Replayable
Explainable
Recoverable

---

## 5. Supported Task Types

FR-001 — OneShot

立即运行一次扫描。

---

FR-002 — Scheduled

固定时间或固定周期运行。

---

FR-003 — Watch

长期持续监控。

---

FR-004 — ConditionWatch

只有满足指定条件才通知。

---

FR-005 — Composite

支持多个条件组合。

例如：

价格低于 ¥4000
AND
总旅行时间 < 25 小时
AND
最多一次转机

---

FR-006 — MultiDomain

一个 Task 可以同时涉及多个 Domain。

例如：

Flight
+
Hotel
+
Travel Bundle

---

## 6. Watch Lifecycle

Watch 状态必须采用显式状态机。

核心状态至少支持：

DRAFT
ACTIVE
WATCHING
PAUSED
COMPLETED
FAILED
CANCELLED

终态不得被错误恢复。

---

## 7. Scheduler

FR-010 — Persistent Scheduler

Watch 必须跨 Host / Agent 重启继续存在。

---

FR-011 — Timezone

使用：

IANA Timezone

例如：

Asia/Shanghai
Australia/Melbourne
America/New_York

必须正确处理 DST。

---

FR-012 — Misfire Policy

支持：

SKIP
RUN_ONCE
CATCH_UP_LIMITED

默认建议：

RUN_ONCE

---

FR-013 — Retry

外部 Source 临时失败时：

不得：

Watch → FAILED

应：

ScanRun
→ FAILED_RETRYABLE
→ Backoff
→ Retry

Watch 保持有效状态。

---

FR-014 — RunLease

多进程/多 Worker 环境下：

同一 Task 不得重复运行。

使用：

DB-backed RunLease

---

FR-015 — Crash Recovery

进程崩溃后重新启动：

必须能够：

* 恢复 Watch
* 恢复 Scheduler
* 识别未完成 ScanRun
* 安全重试
* 避免重复不可逆 Action

---

## 8. Persistence

统一：

UniversalAgentService
        ↓
RepositorySet
        ↓
Single Database

最终 RepositorySet 必须覆盖：

tasks
scan_runs
events
outbox
memory
observations
notifications
approvals
actions
audit
source_health

业务模块不得自行创建第二套 Runtime Database。

---

## 9. Events

FR-020 — EventEnvelope

所有关键事件通过统一 Event Envelope。

至少包含：

event_id
event_type
timestamp
trace_id
task_id
run_id
source
payload

---

FR-021 — Reliable Event

关键事件必须支持：

SQLite EventStore
+
Transactional Outbox
+
Dispatcher
+
Retry
+
Dead Letter handling

进程崩溃不应静默丢失重要事件。

---

## 10. DeepSeek Harness Integration

DeepSeek Harness 是当前正式 Host。

---

FR-030 — Harness Commands

HarnessHostAdapter 必须真正实现：

create_task
update_task
pause_task
resume_task
cancel_task
run_task_once
list_tasks
get_task

run_task_once() 不得保留：

not_implemented

---

FR-031 — Harness Notification

Harness 必须能够真正接收到：

OPPORTUNITY
PRICE_DROP
WATCH_FAILED
APPROVAL_REQUIRED
ACTION_RESULT

而不是只写日志。

---

FR-032 — Harness Approval

完整审批流程：

ActionIntent
→ Approval Request
→ Persistence
→ User Decision
→ APPROVED / DENIED
→ Resume Action Pipeline

不得固定返回：

pending

---

FR-033 — Portable DSH Bridge

移除硬编码：

/Users/<name>/...

使用：

UA_ROOT
UA_PYTHON
UA_DATA_DIR
UA_CONFIG

配置优先级：

Plugin Config
→ Environment
→ Auto Discovery
→ Explicit Failure

禁止 silent fallback 到开发者机器路径。

---

FR-034 — Harness Restart

DeepSeek Harness 重启：

不得导致 Watch 丢失。

长期 Scheduler 不能依赖临时 Plugin Timer 才能存在。

---

## 11. Jarvis Integration Boundary

当前 Jarvis 可以继续保留 Mock / Preview Adapter。

但 Contract 必须稳定。

---

FR-040 — Jarvis Host Swap

未来：

DeepSeek Harness
→ Jarvis

必须满足：

ZERO CORE REWRITE

---

FR-041 — Jarvis Capabilities

预留：

voice_intent
desktop_notification
mobile_notification
approval_request
task_status
memory_query
watch_query
action_status
agent_health

---

## 12. Skill Runtime

Skill = 某个平台提供的能力。

统一接口：

search()
detail()
verify()
availability()
prepare_action()
health_check()

---

FR-050 — Skill Search

返回 Source Raw Data。

---

FR-051 — Skill Detail

返回结构化详情。

---

FR-052 — Skill Verify

确认：

* Price
* Availability
* Conditions
* Freshness

---

FR-053 — Skill Availability

查询实时可用状态。

---

FR-054 — Skill Prepare Action

允许：

推进到提交/支付确认之前

但不得 Commit。

---

FR-055 — Health Check

统一状态：

HEALTHY
DEGRADED
UNAVAILABLE
RATE_LIMITED
AUTH_REQUIRED

---

FR-056 — Execute Separation

禁止：

SkillProtocol.execute_action()

高风险执行必须：

ActionGateway
→ Policy
→ Approval
→ TransactionExecutor

---

## 13. Generic Adapter Runtime

正式建立通用 Adapter：

FR-060 — HTTP Adapter

---

FR-061 — API Adapter

---

FR-062 — Browser Adapter

---

FR-063 — Mobile Adapter Contract

第一阶段 Mobile 可以仅定义 Protocol。

---

FR-064 — Failure Isolation

任何单个平台 Source 崩溃：

不得导致整个 Scanner Pipeline 崩溃。

---

## 14. Source Planning

SourcePlanner 必须根据：

Domain
Task Type
Health
Capability
Cost
Verification Tier
Availability

选择 Source。

---

## 15. Domain Model

正式 Domain：

Flight
Hotel
Travel
Jobs
Railway
Ecommerce
Food
Future

新增 Domain 应满足：

ZERO / MINIMAL CORE CHANGE

新增逻辑应主要位于：

domains/<domain>
skills/<source>
contracts/raw

---

## 16. Flight

Flight 是第一优先级成熟 Domain。

---

FR-070 — Flight Normalize

不同 Source 转换成统一 Flight Candidate。

---

FR-071 — Flight Entity Resolution

跨平台识别同一航班。

不得因字段缺失错误合并。

---

FR-072 — Flight Scoring

至少考虑：

* Price
* Duration
* Stops
* Airport
* Schedule
* Confidence
* Verification
* User Preference

---

FR-073 — Ranking Eligibility

PARTIAL / 不完整结果：

可以进入 Preliminary Results。

不得直接进入 Final Top Recommendation。

---

FR-074 — Multi-Source

目标架构支持：

Skyscanner
Trip / Ctrip
Fliggy
Tongcheng
Other Sources

不要求所有 Source 永远可用。

不可访问时必须明确：

DEGRADED
UNAVAILABLE

---

## 17. Hotel

FR-080 — Hotel Normalize

标准化：

* Hotel
* Room
* Bed
* Breakfast
* Cancellation
* Tax
* Guests
* Price
* Currency

---

FR-081 — Hotel Entity Resolution

不同平台上的同一家酒店必须尽可能正确合并。

---

FR-082 — Hotel Live

完整 Pipeline：

Search
→ Detail
→ Room Normalize
→ Availability
→ Policy Normalize
→ Price
→ Verify
→ Score
→ Rank

---

FR-083 — Independent Failure

Hotel Source 与 Flight Source 互不影响。

---

## 18. Travel Bundle

FR-090 — BundleCandidate

Flight + Hotel 可以组合成：

BundleCandidate

---

FR-091 — Total Trip Utility

不得简单：

Cheapest Flight
+
Cheapest Hotel

必须考虑：

Flight Price
Hotel Price
Travel Time
Stops
Arrival Time
Check-in Compatibility
Airport
Hotel Location
Cancellation
Preferences
Verification Confidence

---

FR-092 — Explainability

每个推荐 Bundle 必须返回：

why_this_bundle

---

## 19. Jobs

FR-100 — Job Normalize

跨招聘平台统一 Job Candidate。

---

FR-101 — Job Matching

根据：

* 用户背景
* 技能
* 地点
* 职位类型
* 公司
* 签证/工作权
* 偏好

产生匹配结果。

---

FR-102 — Application State

状态：

DISCOVERED
SHORTLISTED
PREPARED
NEEDS_USER
READY
SUBMITTED
FAILED

---

FR-103 — Answer Memory

用户确认过的历史回答可以复用。

---

FR-104 — Human-only

以下内容默认 Human-only：

* Personality Test
* Psychological Assessment
* Identity Declaration
* Truthfulness Declaration
* 明确禁止第三方代答的问题

---

## 20. Railway

Railway 当前目标：

Domain Complete

至少实现：

FR-110

Raw Contract

FR-111

Normalize

FR-112

Entity Key

FR-113

Scoring

FR-114

Live Skill

FR-115

Availability

FR-116

Watch

FR-117

Verification

满足后才标记：

RAILWAY_LIVE_READY

---

## 21. Ecommerce

同样必须实现：

Raw
Normalize
Entity
Price
Availability
Source
Verify
Score
Watch
Prepare

满足后：

ECOMMERCE_LIVE_READY

---

## 22. Food

同样必须实现：

Raw
Normalize
Restaurant / Dish Entity
Availability
Price
Source
Verify
Score
Watch

满足后：

FOOD_LIVE_READY

---

## 23. Observation / Evidence / Decision

FR-130 — Observation

每次 Source Scanner 得到真实 Observation。

---

FR-131 — Evidence

经过 Verification 后生成 Evidence。

---

FR-132 — Decision

Decision 必须引用：

supporting_evidence[]

---

FR-133 — Trace

必须支持：

Decision
→ Evidence
→ Observation
→ Source

反查。

---

## 24. Decision Engine

确定性 Decision Pipeline：

Normalize
→ Entity Resolution
→ Constraint
→ Dedup
→ Score
→ Rank
→ Change Detection
→ Verification
→ Opportunity

LLM 只辅助：

Intent Parsing
Semantic Reasoning
Explanation
Summary
Preference Extraction

---

## 25. Opportunity Engine

FR-140 — OpportunityScore

综合：

Current Price
Historical Baseline
Percentile
Availability
Verification
Confidence
Preference
Time Remaining
Source Health

---

FR-141 — Opportunity Result

返回：

OpportunityScore
Confidence
Reason
Evidence
RecommendedAction

---

FR-142 — Rare Opportunity

系统必须能够识别：

明显低于历史水平
+
库存稀缺
+
时间窗口临近
+
用户高度偏好

这类机会。

---

## 26. Long-Term Memory

正式 Memory Domain：

Intent
Preference
Decision
Observation
Answer
TaskState
Policy
ExecutionHistory

---

FR-150 — Scope

支持：

GLOBAL
USER
DOMAIN
TASK

---

FR-151 — Confidence

Memory Record 可以记录 Confidence。

---

FR-152 — Preference Learning

根据用户行为更新 Preference。

---

FR-153 — Policy Isolation

Preference Learning 不得自动修改 Policy。

---

FR-154 — Explainable Preference

自动学习出的 Preference 必须保留来源。

---

FR-155 — Reversible Preference

Preference 更新必须可以撤销或恢复旧版本。

---

## 27. Notification System

统一：

NotificationService

---

FR-160 — Persistent Dedup

重启后仍能知道通知是否已经发送。

---

FR-161 — Cooldown

避免反复通知同一个机会。

---

FR-162 — Priority

至少：

LOW
NORMAL
HIGH
URGENT

---

FR-163 — Channel

支持抽象：

Harness
Desktop
Mobile
Webhook
Jarvis
Future

---

FR-164 — Notification Events

至少：

PRICE_DROP
RARE_OPPORTUNITY
AVAILABILITY_CHANGE
WATCH_FAILED
APPROVAL_REQUIRED
ACTION_RESULT

---

## 28. Controlled Actions

Action Level：

L0 READ
L1 SAFE AUTOMATION
L2 PREPARE
L3 REVERSIBLE ACTION
L4 HIGH-RISK / IRREVERSIBLE

---

FR-170 — L0

只读扫描。

---

FR-171 — L1

安全自动化。

---

FR-172 — L2

可以自动推进到：

confirmation page

之前。

---

FR-173 — L3/L4

必须同时满足：

Policy Allow
+
Approval
+
Valid Quote Snapshot
+
Slippage Check
+
Idempotency
+
Executor

---

FR-174 — Snapshot

审批后如果：

* Price
* Date
* Passenger
* Hotel Room
* Currency
* Cancellation
* Material Terms

发生变化：

必须：

REAPPROVAL_REQUIRED

---

FR-175 — Idempotency

不可逆操作必须防重复执行。

---

FR-176 — Reconciliation

External Call 结果未知：

UNKNOWN
→ RECONCILE

禁止盲目重新执行。

---

## 29. Kill Switch

FR-180

系统必须存在 Global Kill Switch。

Kill Switch 开启：

禁止所有受控写操作。

---

## 30. Security

FR-190 — Credential Isolation

Credential 不得明文进入：

* Prompt
* Memory
* Logs
* Audit

---

FR-191 — macOS

Production 支持：

macOS Keychain

---

FR-192 — Windows

Production 支持：

Windows Credential Manager

---

FR-193 — Identity

Identity Vault 独立于普通 Memory。

---

FR-194 — Session

Session Broker 独立管理外部平台 Session。

---

## 31. Observability

统一：

Structured Logs
Metrics
Traces
Audit

完整 Trace：

Task
→ ScanRun
→ Query
→ Source
→ Observation
→ Candidate
→ Evidence
→ Opportunity
→ Notification
→ Action

---

## 32. Legacy Cleanup

仓库根目录旧：

scanner/
tasks/

必须进行 Reality Audit。

若确定属于早期原型：

DO NOT EXTEND

处理方式：

extract useful logic/tests
→ migrate
→ archive under legacy/
or
→ remove

不得同时存在：

Old Scanner Architecture
+
Universal Agent Core

两套持续演进的主框架。

---

## 33. Product Non-Goals

当前不要求：

* 自研基础大模型
* 自研浏览器引擎
* 绕过平台安全机制
* 绕过验证码
* 未审批自动支付
* 无 Policy 的高风险操作
* 把所有网站逻辑写入 Core
* 为每个新 Domain 重写 Core

---

## 34. Development Chapters

---

### CHAPTER 0 — Repository Reality Lock

0.1

运行当前 Full Regression。

0.2

重新生成最新 Capability Matrix。

0.3

对齐：

README
ROADMAP
KNOWN_LIMITATIONS
FINAL_VERIFICATION_REPORT
ACTUAL CODE

0.4

审计 Legacy：

scanner/
tasks/

0.5

建立：

SPAC.md
HARNESS_GOAL.md
MISSING_FEATURE_REPORT.md
.ai-memory/

Chapter Gate

运行：

agent-project-test

必须：

PASS

---

## 35. CHAPTER 1 — Runtime Composition

1.1

RepositorySet 完整化。

1.2

Event / Outbox 统一 DB。

1.3

Observation Repository。

1.4

Notification Repository。

1.5

Approval Repository。

1.6

Action / Audit / SourceHealth Repository。

1.7

Runtime lifecycle。

Gate

验证：

restart
persistence
crash recovery
multi-process

然后：

agent-project-test

---

## 36. CHAPTER 2 — DeepSeek Harness Production Integration

2.1

实现真实：

run_task_once()

2.2

Harness Notification Sink。

2.3

Harness Approval flow。

2.4

DSH Bridge portable config。

2.5

安装 / reload / healthcheck。

2.6

Harness restart recovery。

Acceptance Flow

Harness
→ Create Watch
→ Persist
→ Scan
→ Opportunity
→ Notification
→ Pause
→ Resume
→ Restart Harness
→ Watch Restored
→ Scan Continues

完成后：

agent-project-test

---

## 37. CHAPTER 3 — Generic Source Runtime

3.1 HTTP Adapter

3.2 API Adapter

3.3 Browser Adapter

3.4 Mobile Adapter Contract

3.5 Capability Resolver

3.6 Source Health

3.7 Failure Isolation

Gate

模拟：

Source A FAIL
Source B PASS
Source C DEGRADED

整个 Task 仍必须完成有效结果。

运行：

agent-project-test

---

## 38. CHAPTER 4 — Travel Multi-Source

4.1

Skyscanner hardening。

4.2

第二 Flight Source。

4.3

第三 Flight Source。

4.4

Hotel Live Source。

4.5

Cross-source Entity Resolution。

4.6

Verification。

4.7

Live Bundle。

Gate

真实流程：

Multi Source
→ Normalize
→ Dedup
→ Verify
→ Compare
→ Bundle
→ Rank
→ Explain

运行：

agent-project-test

---

## 39. CHAPTER 5 — Persistent Opportunity Watch

5.1 Historical Baseline

5.2 Price History

5.3 Trend

5.4 Opportunity Score

5.5 Condition Watch

5.6 Notification Cooldown

5.7 Deadline-sensitive Scan Frequency

Gate

真实运行 Watch。

普通波动：

NO NOTIFICATION

满足机会条件：

NOTIFY

运行：

agent-project-test

---

## 40. CHAPTER 6 — Jobs Productization

6.1 Live Source

6.2 Job Pipeline

6.3 Application State

6.4 Answer Memory

6.5 Human-only Gate

6.6 Prepare Action

Gate

Discover
→ Normalize
→ Match
→ Decide
→ Prepare

并保证：

Human-only

不被自动越过。

运行：

agent-project-test

---

## 41. CHAPTER 7 — Additional Domains

顺序开发：

Railway
→ Ecommerce
→ Food

每个 Domain 必须完成：

Raw Contract
Normalize
Entity
Constraint
Score
Skill
Source
Verify
Watch
Notification

每完成一个小 Domain：

独立测试。

整个 Chapter 完成：

agent-project-test

---

## 42. CHAPTER 8 — Controlled Execution Productionization

8.1 Production Credential Backend

8.2 Identity Vault

8.3 Session Broker

8.4 Approval Lifecycle

8.5 L3 Execution

8.6 L4 Policy Boundary

8.7 Reconciliation

8.8 Compensation

8.9 Kill Switch Integration

Gate

默认：

DENY

模拟所有：

success
failure
timeout
unknown
crash
duplicate

情况。

运行：

agent-project-test

---

## 43. CHAPTER 9 — Jarvis Ready

9.1

正式 Jarvis Host Adapter。

9.2

Task bridge。

9.3

Memory bridge。

9.4

Notification bridge。

9.5

Approval bridge。

9.6

Health bridge。

9.7

Host Swap Test。

Gate

执行：

DeepSeek Harness
→ Jarvis

要求：

ZERO CORE REWRITE

运行：

agent-project-test

---

## 44. Subchapter Test Gate

每完成一个 Subchapter：

必须：

IMPLEMENT
→ TEST
→ FIX
→ RETEST
→ PASS

如果：

FAIL

则：

NEXT SUBCHAPTER = BLOCKED

不得继续。

---

## 45. No Parallel Small Tests

小章节：

SUBCHAPTER_PARALLEL_TESTING = FALSE

禁止为了速度同时启动大量测试 Agent。

小章节测试必须顺序、可重复、可定位失败原因。

---

## 46. Subchapter Test Coverage

根据模块至少测试：

Syntax
Import
Compile
Type
Lint
Unit
Runtime
API
State
Persistence
Functional Behavior
Error Path
Regression

PASS 必须同时：

CODE_CORRECT = TRUE

以及：

FUNCTION_IMPLEMENTED = TRUE

---

## 47. Major Chapter Gate

每完成一个大 Chapter：

必须调用：

agent-project-test

测试范围：

CHAPTER 0
→
CURRENT CHAPTER

累计测试。

不是只测试新代码。

---

## 48. agent-project-test Scope

必须包含：

Code

* Syntax
* Import
* Type
* Runtime
* Dependencies
* Exceptions

Functional

* SPAC 功能是否真正存在
* 用户路径是否能完成
* API 是否真实工作
* Watch 是否真实运行
* Notification 是否真实发送
* Approval 是否真实流转

Integration

* Host
* Coordinator
* Scheduler
* Persistence
* Memory
* Skill
* Adapter
* Domain
* Notification
* Action

Regression

前面 Chapter 已完成能力不得被破坏。

Failure Injection

* Source Fail
* API Timeout
* Crash
* Restart
* Duplicate
* Partial Data

Requirement Coverage

每个 FR 标记：

PASS
FAIL
PARTIAL
NOT_IMPLEMENTED
BLOCKED

---

## 49. Missing Feature Report

每次大 Chapter 测试后：

对比：

SPAC
VS
ACTUAL CODE

如果发现：

* 未实现
* 部分实现
* Mock
* Stub
* UI Shell
* Backend 未接
* API 未调用
* 功能不能走通

必须生成或更新：

MISSING_FEATURE_REPORT.md

格式：

Requirement:
FR-xxx
Expected:
...
Actual:
...
Status:
PARTIAL / NOT_IMPLEMENTED / FAIL
Severity:
P0 / P1 / P2 / P3
Affected Modules:
...
Missing Work:
...
Recommended Chapter:
...

---

## 50. Project Memory

长期维护：

.ai-memory/
├── CURRENT_STATE.md
├── TODO.md
├── DECISIONS.md
├── TEST_STATUS.md
└── CHANGELOG.md

每个小章节完成更新：

CURRENT_STATE
TODO
TEST_STATUS

重大决策更新：

DECISIONS

重要实现更新：

CHANGELOG

禁止保存大量原始聊天记录。

---

## 51. Project Runtime State

Harness 每次恢复项目必须能够读取：

PROJECT_STATUS
CURRENT_CHAPTER
CURRENT_SUBCHAPTER
LAST_TEST_STATUS
BLOCKERS
NEXT_ACTION
GLOBAL_TEST_REQUIRED

例如：

PROJECT_STATUS: DEVELOPMENT
CURRENT_CHAPTER:
CHAPTER 2 — DeepSeek Harness Production Integration
CURRENT_SUBCHAPTER:
2.3 Approval Flow
LAST_TEST_STATUS:
PASS
BLOCKERS:
NONE
NEXT_ACTION:
Implement 2.4
GLOBAL_TEST_REQUIRED:
FALSE

---

## 52. Architecture Change Policy

开发过程中如果新需求影响：

* Product Positioning
* Core Architecture
* Runtime Truth
* Security Boundary
* Permission Model
* Execution Model
* Host/Core Boundary
* Core Data Contracts

必须：

STOP
→ lean-brainstorm-grill
→ UPDATE SPAC
→ UPDATE DECISIONS
→ RELOCK
→ CONTINUE

不得由开发 Agent 私自改变架构。

---

## 53. Definition of Done

Universal Agent 只有同时满足以下条件，才能认为最终产品完成。

Runtime

所有核心 Runtime State 有可靠单一持久化。

Watch

长期 Watch 能跨重启运行。

Scheduler

时区、misfire、retry、lease 正确。

DeepSeek Harness

Harness 可以真正：

Create
Run
Pause
Resume
Cancel
Notify
Approve

Multi-Source

至少 Flight + Hotel 具有真实多 Source Pipeline。

Decision

可以：

Observe
Normalize
Compare
Verify
Decide
Explain

Opportunity

Condition Watch 可以持续识别真正机会。

Notification

机会出现时可以真实通知用户。

Memory

长期偏好、决策和历史可以保存并恢复。

Skill Runtime

Source 能插件化扩展。

Failure Isolation

单 Source 失败不会拖垮整个 Watch。

Controlled Actions

所有高风险 Action：

Policy
+
Approval
+
Idempotency
+
Slippage
+
Audit

完整。

Security

Production Credential 不明文落盘。

Jarvis

Jarvis 可以通过 Host Adapter 接入。

Architecture

Jarvis Host Swap：

ZERO CORE REWRITE

Testing

全部 Subchapter Gate PASS。

全部 Major Chapter：

agent-project-test = PASS

Final Regression

0 failed

Requirement Coverage

关键 SPAC Requirement：

不得存在未披露 P0 / P1：

NOT_IMPLEMENTED

Missing Features

所有剩余功能必须明确：

implemented
or
deferred

不得伪装成完成。

---

## 54. Final Acceptance Test

最终必须执行一次：

agent-project-test

覆盖完整真实工作流：

CREATE WATCH
→ PERSIST
→ SCHEDULE
→ SCAN MULTIPLE SOURCES
→ SOURCE FAILURE ISOLATION
→ NORMALIZE
→ ENTITY RESOLUTION
→ VERIFY
→ SCORE
→ RANK
→ CHANGE DETECTION
→ OPPORTUNITY
→ NOTIFY
→ MEMORY UPDATE
→ PREPARE ACTION
→ APPROVAL
→ POLICY CHECK
→ CONTROLLED EXECUTION
→ AUDIT
→ RESTART
→ RECOVER
→ CONTINUE WATCH

---

## 55. Final Completion Report

最终生成：

PROJECT_COMPLETION_REPORT.md

必须包含：

Completed Chapters
Requirement Coverage
Full Regression Results
Functional Test Results
Live Source Status
Known Limitations
Deferred Features
Security Status
Jarvis Readiness
Technical Debt
Remaining Risks

---

## 56. Final Project Status Rule

禁止为了"看起来完成"而完成。

最终原则：

IMPLEMENTED
+
TESTED
+
FUNCTIONALLY VERIFIED
+
REGRESSION SAFE
+
TRACEABLE
+
RECOVERABLE
+
TRACEABLE TO SPAC

只有满足 Definition of Done 后：

PROJECT_STATUS = COMPLETE

否则：

PROJECT_STATUS = DEVELOPMENT

或：

PROJECT_STATUS = PARTIAL

END OF SPAC
