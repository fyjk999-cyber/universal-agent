# PHASE 6 — Action Preparation 验收报告

> 日期：2026-08-14 · 环境：Python 3.12 · pytest 9.1.1

---

## PHASE COMPLETED

**Implemented（§65 PREPARE-only + §37-§41/§50 风险控制骨架）**

### 风险控制骨架（Phase 6 前置）
| 模块 | 内容 | § |
|---|---|---|
| `actions/idempotency/store.py` | IdempotencyStore：idempotency_key 去重，重复同结果返回已有、异结果抛 DuplicateRequest | §38 |
| `actions/slippage/guard.py` | SlippageGuard：确认价 vs 执行价，CNY/百分比双上限，超限 ABORT | §39 |
| `actions/approval/inbox.py` | ApprovalInbox：统一审批（purchase/job_application/order/captcha/identity），**绝不自动通过**，支持 approve/reject | §41 |
| `observability/audit/audit.py` | AuditLog：append-only JSONL，六要素（actor/action/reason/based_on/approved/result） | §50 |

### PREPARE 管线（§65）
`actions/gateway/prepare.py` — **ActionPreparer.prepare()**：
```
Preflight(§37) → Idempotency(§38) → Slippage(§39) → Skill Capability(§43)
→ Approval(§41) → Audit(§50) → 登记幂等 → PREPARED
```
- 只接受 **L2_PREPARE**；L3_CONFIRM / L4_EXECUTE 仍硬阻塞（§65 不 Commit）
- IRREVERSIBLE 不能 PREPARE（§40/§56）
- PREPARE 本身无外部副作用（不导航到确认页/不提交），只产出审批请求 + audit

**Tests（+14）**：unit/test_action_prepare.py
- Idempotency：登记/重复同结果/异结果冲突/持久化
- Slippage：限内放行 / ¥370 超 ¥100 ABORT / 5% 超 2% ABORT
- Approval：绝不自动通过 / approve+reject / pending 列表
- Audit：六字段 append-only
- PREPARE：成功建审批+audit / DUPLICATE / IRREVERSIBLE 拒绝 / **不是 Commit** / L3 拒绝

**端到端实测**
```text
1. PREPARE 机票: PREPARED | 审批 ap_2802f PENDING
2. 重复 PREPARE: DUPLICATE (幂等保护 §38)
3. Slippage ¥4380→¥4750: ABORT | slippage ¥370 > max ¥100 (§39)
4. 审批: APPROVED (由 user 决定)
5. Audit: 2 条; 最近: PREPARE::prepare_order
```

**Known limitations**
- PREPARE 尚未接真实 Skill/Adapter（"导航到确认页"是计划产物，未执行）
- Approval 由 Harness/GUI 展示（Phase 6 骨架为 JSON 存储 + 确定性 decide）
- Compensation（§37）仍为目录占位（未实现补偿逻辑）
- Idempotency 为 JSON 持久化（生产可换 Redis）

**Security / 合规**
- **无任何真实 Commit**：PREPARE 只产出审批请求，不触发外部副作用
- L3/L4 硬阻塞；IRREVERSIBLE 拦截（Job 提交/支付仍不可执行）
- 审批绝不自动通过（§56）
- SHADOW MODE 保持

**Host coupling audit**：CLEAN ✓（新增全在 actions/observability，无 hosts 依赖）

**Migration compatibility**：Jarvis Host Swap + CareerPilot Migration Test 继续通过（212 全绿）

**Next phase**
- **PHASE 7 — Controlled Execution**：仅在 Idempotency/Slippage/Approval/Audit/
  Compensation/Policy/Kill Switch 全部稳定后讨论——当前骨架已就绪（缺
  Compensation/Policy/Kill Switch），短期保持 L3/L4 阻塞
- 可选：PREPARE 接真实 Skill（机票到确认页）/ Compensation 实现
