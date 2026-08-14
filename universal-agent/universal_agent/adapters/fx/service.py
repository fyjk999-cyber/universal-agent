"""实时汇率服务（open.er-api.com，免费无 key）— 缓存 + 离线兜底。

供 Skyscanner 等外币源换算 CNY 使用。格式：rates[币种] = 1 CNY 可兑多少外币，
外币→CNY = amount / rate。
"""
from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Dict, Optional

from universal_agent.adapters.skyscanner.adapter import to_cny

log = logging.getLogger("ua.fx")

DEFAULT_URL = "https://open.er-api.com/v6/latest/CNY"
CACHE_TTL = 6 * 3600  # 6h


class FxService:
    """Minimal FX: cache-first, network refresh on TTL, offline fallback."""

    def __init__(self, cache_path: Optional[Path] = None,
                 url: str = DEFAULT_URL, timeout: int = 10) -> None:
        self.cache_path = cache_path
        self.url = url
        self.timeout = timeout
        self._rates: Optional[Dict[str, float]] = None
        self._loaded = False

    def rates(self) -> Dict[str, float]:
        if not self._loaded:
            self._load()
        return self._rates or {}

    def _load(self) -> None:
        self._loaded = True
        if self.cache_path and self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text("utf-8"))
                age = time.time() - data.get("fetched_at", 0)
                if age < CACHE_TTL and data.get("rates"):
                    self._rates = data["rates"]
                    return
            except Exception:  # noqa: BLE001
                pass
        # 联网刷新
        try:
            import urllib.request
            req = urllib.request.Request(self.url, headers={"User-Agent": "universal-agent/0.1"})
            with urllib.request.urlopen(req, timeout=self.timeout) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            self._rates = data.get("rates")
            if self.cache_path and self._rates:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(
                    json.dumps({"fetched_at": time.time(), "rates": self._rates}), "utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("FX refresh failed, using cache/fallback: %s", exc)
            if self.cache_path and self.cache_path.exists():
                try:
                    data = json.loads(self.cache_path.read_text("utf-8"))
                    self._rates = data.get("rates")
                except Exception:  # noqa: BLE001
                    self._rates = None

    def convert(self, amount: float, currency: str) -> float:
        """外币 → CNY；未联网时用内置兜底。"""
        return to_cny(amount, currency, self.rates() if self._rates else None)
