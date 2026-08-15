"""CredentialVault（P14）— 凭据隔离存储。

注意：本实现是**开发/影子模式**的轻量混淆（base64 + 异或），
用于保证「明文不出现在普通 Memory/日志」。生产环境应接 OS Keychain
（macOS Security Framework / Keychain），本模块是接口+兜底实现。

设计原则：
  - 凭据绝不写入普通 Memory（P3 MemoryDomains）
  - 对外只暴露 masked 视图或引用（token），不暴露完整凭据
  - vault 文件带混淆标记，禁止明文
"""
from __future__ import annotations

import base64
import json
import secrets
from pathlib import Path
from typing import Any, Dict, Optional

_KEY = b"ua-dev-vault-2026"  # 开发用固定 key；生产接 Keychain


def _obfuscate(text: str) -> str:
    data = text.encode("utf-8")
    xored = bytes(b ^ _KEY[i % len(_KEY)] for i, b in enumerate(data))
    return base64.urlsafe_b64encode(xored).decode("ascii")


def _deobfuscate(token: str) -> str:
    xored = base64.urlsafe_b64decode(token.encode("ascii"))
    data = bytes(b ^ _KEY[i % len(_KEY)] for i, b in enumerate(xored))
    return data.decode("utf-8")


class CredentialVault:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = Path(data_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)
        self._file = self.data_dir / "credentials.json"
        self._store: Dict[str, Dict[str, Any]] = {}
        self._load()

    def _load(self) -> None:
        if self._file.exists():
            try:
                self._store = json.loads(self._file.read_text("utf-8"))
            except Exception:  # noqa: BLE001
                self._store = {}

    def _save(self) -> None:
        self._file.write_text(json.dumps(self._store, indent=2), "utf-8")

    def set(self, name: str, credential: Dict[str, Any]) -> None:
        """存凭据（混淆后落盘）。"""
        self._store[name] = {
            "ref": f"cred:{name}",
            "token": _obfuscate(json.dumps(credential, ensure_ascii=False)),
            "created_at": None,
        }
        self._save()

    def get(self, name: str) -> Optional[Dict[str, Any]]:
        entry = self._store.get(name)
        if entry is None:
            return None
        try:
            return json.loads(_deobfuscate(entry["token"]))
        except Exception:  # noqa: BLE001
            return None

    def masked(self, name: str) -> Optional[Dict[str, Any]]:
        """掩码视图：只暴露部分信息（LLM 只能拿这个）。"""
        full = self.get(name)
        if full is None:
            return None
        out = {}
        for k, v in full.items():
            sv = str(v)
            if len(sv) <= 4:
                out[k] = "***"
            else:
                out[k] = sv[:2] + "*" * (len(sv) - 4) + sv[-2:]
        return out

    def reference(self, name: str) -> Optional[str]:
        entry = self._store.get(name)
        return entry.get("ref") if entry else None
