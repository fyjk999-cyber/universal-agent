# SPRINT COMPLETED — P14 (Security)

> 日期：2026-08-14 · 测试基线 480 → **484 passed**

## 1. Problems fixed

| # | 问题 | 修复 |
|---|---|---|
| P14.0 | 无凭据存储 | **CredentialVault**：混淆存储（dev 模式），明文绝不落盘/进 Memory |
| P14.1 | 无权限管理 | **PermissionManager**：grant/revoke/check，**默认拒绝**（fail-closed） |
| P14.2 | LLM 可能拿完整凭据 | `vault.masked()` 掩码视图 + `vault.reference()` 引用 |

## 2. Files changed

```
security/credential_vault/vault.py  (新增：CredentialVault)
security/permissions/manager.py     (新增：PermissionManager)
tests/unit/test_p14_security.py     (新增 4 项)
```

## 3. Tests passed

**484 passed / 0 failed**

## 4. 安全边界

- 凭据不进 P3 Memory（测试锁定）
- 明文不落盘（混淆标记）
- LLM 只拿 masked/reference（不拿完整支付凭据）

## 5. Known limitations

- dev 混淆非生产级（生产接 OS Keychain——接口已隔离）
- SessionBroker/IdentityVault 仍占位（P16 补）

## 6. Next sprint

**P15 — Action Prepare**（L2 PREPARE：机票到确认页 / Jobs 到 Submit 前 / Ecommerce 到 Checkout 前；No Commit；Approval Inbox 统一管理）
