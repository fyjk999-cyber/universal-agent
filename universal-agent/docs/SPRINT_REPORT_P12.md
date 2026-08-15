# SPRINT COMPLETED — P12 (Preference Learning)

> 日期：2026-08-14 · 测试基线 471 → **476 passed**

## 1. Problems fixed

| # | 问题 | 修复 |
|---|---|---|
| P12.0 | 无偏好学习 | **PreferenceLearner**：从 Decision Memory 观察（accepted/price/platform）更新价格敏感度 + 平台偏好 |
| P12.1 | 无版本/可解释/可逆 | versioned（upsert 递增）/ explainable（evidence/counts）/ reversible（rollback 低置信标记） |
| P12.2 | 学习可能触碰 Policy | 学习只写 preference 子域；Policy 独立，测试锁定不被改变（IRON RULE 7） |

## 2. Files changed

```
memory/preferences/learner.py  (新增：PreferenceLearner)
memory/preferences/__init__.py (导出)
tests/unit/test_p12_preference.py (新增 5 项)
```

## 3. Tests passed

**476 passed / 0 failed**

## 4. Known limitations

- 用户固定 u1（多用户隔离后续）；学习规则简单（±0.05）
- 无趋势学习（P11 trend 是 estimate；P13+ 可加权）

## 5. Next sprint

**P13 — CareerPilot Live**（Jobs 作为第二 Domain 验证通用性；不得为大改 Core）
