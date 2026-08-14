"""汇率换算（任务无关）。

数据源：open.er-api.com（免费，无需 key）。
- base=CNY 返回各货币相对 1 CNY 的比值；
  外币 -> CNY 换算：CNY = 金额 / rates[币种]。
- 提供缓存与离线兜底（最后已知汇率 + 显式告警）。
"""
from __future__ import annotations

import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, Optional

import requests

log = logging.getLogger("scanner.fx")

DEFAULT_RATES_URL = "https://open.er-api.com/v6/latest/CNY"
CACHE_TTL = 6 * 3600  # 6 小时


class Fx:
    def __init__(self, cache_path: Optional[Path] = None, url: str = DEFAULT_RATES_URL, timeout: int = 15):
        self.cache_path = cache_path
        self.url = url
        self.timeout = timeout
        self._rates: Optional[Dict[str, float]] = None
        self._checked_at: Optional[str] = None
        self._source = "unknown"

    # ---- 获取 ----
    def load(self, force: bool = False) -> bool:
        """加载汇率（优先缓存，超 TTL 或 force 时联网刷新）。返回是否成功。"""
        if self._rates is not None and not force:
            return True
        if not force and self.cache_path and self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                age = time.time() - data.get("fetched_at", 0)
                if age < CACHE_TTL:
                    self._rates = data["rates"]
                    self._checked_at = data.get("checked_at")
                    self._source = "cache"
                    return True
            except Exception:  # noqa: BLE001
                pass
        try:
            resp = requests.get(self.url, timeout=self.timeout)
            resp.raise_for_status()
            data = resp.json()
            if data.get("result") != "success" or "rates" not in data:
                raise ValueError(f"汇率接口异常: {data.get('result')}")
            rates = data["rates"]
            self._rates = {k: float(v) for k, v in rates.items()}
            self._checked_at = data.get("time_last_update_utc") or datetime.now(timezone.utc).strftime(
                "%Y-%m-%d %H:%M UTC"
            )
            self._source = "open.er-api.com"
            if self.cache_path:
                self.cache_path.parent.mkdir(parents=True, exist_ok=True)
                self.cache_path.write_text(
                    json.dumps(
                        {"fetched_at": time.time(), "checked_at": self._checked_at, "rates": self._rates},
                        ensure_ascii=False,
                    ),
                    encoding="utf-8",
                )
            return True
        except Exception as exc:  # noqa: BLE001
            log.warning("汇率刷新失败(%s)，尝试兜底", exc)
            return self._fallback()

    def _fallback(self) -> bool:
        """离线兜底：读缓存中的旧数据（即便超 TTL）。"""
        if self.cache_path and self.cache_path.exists():
            try:
                data = json.loads(self.cache_path.read_text(encoding="utf-8"))
                self._rates = data["rates"]
                self._checked_at = data.get("checked_at", "缓存（可能过期）")
                self._source = f"cache-fallback({self._checked_at})"
                return True
            except Exception:  # noqa: BLE001
                pass
        return False

    # ---- 换算 ----
    def to_cny(self, amount: float, currency: str) -> Optional[float]:
        """外币金额 -> CNY。币种未知返回 None。"""
        if self._rates is None and not self.load():
            return None
        currency = (currency or "CNY").upper()
        if currency == "CNY":
            return round(float(amount), 2)
        rate = self._rates.get(currency)
        if rate is None or rate <= 0:
            log.warning("汇率表缺少币种 %s", currency)
            return None
        return round(float(amount) / rate, 2)

    @property
    def checked_at(self) -> str:
        return self._checked_at or "未获取"

    @property
    def source(self) -> str:
        return self._source
