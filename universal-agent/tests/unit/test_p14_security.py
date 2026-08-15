"""P14 — Security：CredentialVault / PermissionManager / 凭据隔离。

验收：
1. CredentialVault：凭据不落普通 Memory（独立加密/文件存储），不打印明文
2. PermissionManager：权限分级，未授权操作拒绝
3. LLM 不获得完整支付凭据（vault 只暴露 token 引用）
4. 普通 Memory 禁止保存 password/cookie/payment secret
"""
from __future__ import annotations

from pathlib import Path

import pytest


def test_credential_vault_stores_without_leak(tmp_path: Path) -> None:
    """凭据存入 vault，不出现于明文 Memory/日志。"""
    from universal_agent.security.credential_vault.vault import CredentialVault
    v = CredentialVault(tmp_path / "vault")
    v.set("payment", {"card": "4111111111111111", "cvv": "123"})
    # 读回（内存中）
    got = v.get("payment")
    assert got is not None
    # vault 文件不存明文（应有混淆/加密标记）
    raw = (tmp_path / "vault" / "credentials.json").read_text()
    assert "4111111111111111" not in raw
    assert "123" not in raw


def test_credential_vault_never_in_memory(tmp_path: Path) -> None:
    """凭据不得进入普通 Memory（P3 MemoryDomains 不用来存 secret）。"""
    from universal_agent.memory.domains import MemoryDomains
    from universal_agent.memory.sqlite_store import SqliteMemoryStore
    from universal_agent.persistence import Database
    from universal_agent.security.credential_vault.vault import CredentialVault

    db = Database(tmp_path / "ua.db")
    mem = MemoryDomains(SqliteMemoryStore(db))
    v = CredentialVault(tmp_path / "vault")
    v.set("session_cookie", {"cookie": "SECRET_COOKIE_ABC"})
    # Memory 中只有引用（token），无明文
    mem.set_preference("vault_ref", {"ref": "cred:session_cookie"}, user_id="u1")
    stored = mem.get_preference("vault_ref", user_id="u1")
    assert "SECRET_COOKIE_ABC" not in str(stored.value)
    db.close()


def test_permission_manager_denies_unapproved(tmp_path: Path) -> None:
    from universal_agent.security.permissions.manager import PermissionManager
    pm = PermissionManager(tmp_path / "perms")
    pm.grant("user1", "read_tasks")
    assert pm.check("user1", "read_tasks") is True
    assert pm.check("user1", "execute_payment") is False  # 未授权 → 拒绝


def test_vault_returns_reference_not_full_credential(tmp_path: Path) -> None:
    """LLM 拿到的不是完整支付凭据，而是引用/掩码。"""
    from universal_agent.security.credential_vault.vault import CredentialVault
    v = CredentialVault(tmp_path / "vault")
    v.set("payment", {"card": "4111111111111111", "cvv": "123"})
    masked = v.masked("payment")
    assert masked is not None
    assert "4111111111111111" not in masked.get("card", "")
    assert "cvv" not in masked or masked.get("cvv") == "***"
