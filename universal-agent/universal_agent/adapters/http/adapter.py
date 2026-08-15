"""HTTP Adapter（FR-060）— 通用同步 HTTP 抓取（超时 / 重试 / 失败隔离）。

供 Skill 层复用：任何基于 HTTP/JSON 的 Source 都可以用它实现 search/health。
- 超时：单请求硬超时（默认 15s）
- 重试：网络错误重试 2 次（指数退避）
- 失败隔离：网络/HTTP 错误统一抛 HttpAdapterError，绝不吞掉让调用方静默
"""
from __future__ import annotations

import logging
import time
from typing import Any, Dict, Optional

import requests

log = logging.getLogger("ua.adapters.http")

DEFAULT_TIMEOUT_MS = 15_000
DEFAULT_RETRIES = 2


class HttpAdapterError(RuntimeError):
    """HTTP 抓取失败（网络错误 / 超时 / 非 2xx / JSON 解析失败）。"""


class HttpAdapter:
    def __init__(self, timeout_ms: int = DEFAULT_TIMEOUT_MS,
                 retries: int = DEFAULT_RETRIES,
                 user_agent: str = "universal-agent/0.1 (research; robots-ok)",
                 headers: Optional[Dict[str, str]] = None) -> None:
        self.timeout_ms = timeout_ms
        self.retries = retries
        self.headers = {"User-Agent": user_agent, **(headers or {})}

    def get_json(self, url: str, params: Optional[Dict[str, Any]] = None,
                 headers: Optional[Dict[str, str]] = None,
                 timeout_ms: Optional[int] = None) -> Any:
        """GET + JSON 解析；失败抛 HttpAdapterError（失败隔离）。"""
        last_err: Optional[Exception] = None
        hdrs = {**self.headers, **(headers or {})}
        timeout = (timeout_ms or self.timeout_ms) / 1000.0
        for attempt in range(self.retries + 1):
            try:
                resp = requests.get(url, params=params, headers=hdrs,
                                    timeout=timeout)
            except requests.RequestException as exc:  # 网络/超时
                last_err = exc
                if attempt < self.retries:
                    time.sleep(0.5 * (2 ** attempt))
                    continue
                break
            if resp.status_code == 429:
                raise HttpAdapterError(f"rate_limited: {url} -> HTTP 429")
            if resp.status_code >= 400:
                raise HttpAdapterError(f"http_error: {url} -> HTTP {resp.status_code}")
            try:
                return resp.json()
            except ValueError as exc:
                raise HttpAdapterError(f"bad_json: {url}: {exc}") from exc
        raise HttpAdapterError(f"network_error: {url}: {last_err}")

    def is_available(self, url: str, timeout_ms: int = 8_000) -> bool:
        """健康探测：可达 + 任意响应即 HEALTHY（不要求 JSON）。"""
        try:
            resp = requests.get(url, params={"ping": 1},
                                headers=self.headers,
                                timeout=timeout_ms / 1000.0)
            return resp.status_code < 500
        except requests.RequestException:
            return False
