"""数据源适配器基类。

每个数据源实现 FlightSearcher 接口，返回统一的 Itinerary 列表。
框架按配置的 preferred_order 依次尝试；某个数据源失败不影响整体。
"""
from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from typing import List, Optional

from ..models import Itinerary

log = logging.getLogger("flights_zqn.searchers")


class FlightSearcher(ABC):
    """一个机票数据源。"""

    name: str = "base"
    #: 结果价格币种（未知为 None，由任务统一换算）
    currency: Optional[str] = None
    #: 是否需要 headless 浏览器
    needs_browser: bool = False

    @abstractmethod
    def search_roundtrip(self, origin: str, dest: str, depart: str, return_: str,
                         adults: int = 1) -> List[Itinerary]:
        """搜索一次往返，返回方案列表（可空）。失败时抛异常由上层捕获。"""

    def warmup(self) -> None:
        """可选：数据源预热（浏览器启动等），避免每次查询重复开销。"""

    def shutdown(self) -> None:
        """可选：释放资源。"""


class SearcherPool:
    """管理多个数据源，按优先级尝试。"""

    def __init__(self, searchers: List[FlightSearcher]):
        self.searchers = searchers

    def search_roundtrip(self, origin: str, dest: str, depart: str, return_: str,
                         adults: int = 1) -> tuple[List[Itinerary], List[str]]:
        """按优先级尝试所有数据源；返回 (合并去重结果, 使用的数据源名列表)。"""
        merged: List[Itinerary] = []
        used: List[str] = []
        seen = set()

        def key(it: Itinerary) -> str:
            out = it.outbound.first
            inn = it.inbound.first
            return (
                f"{it.origin_airport}|{it.depart_date}|{it.return_date}|"
                f"{(out.flight_no if out else '')}|{(inn.flight_no if inn else '')}|"
                f"{it.price_cny}"
            )

        for s in self.searchers:
            try:
                found = s.search_roundtrip(origin, dest, depart, return_, adults)
                for it in found or []:
                    k = key(it)
                    if k in seen:
                        continue
                    seen.add(k)
                    merged.append(it)
                if found:
                    used.append(s.name)
                    log.info("[%s] %s->%s %s~%s 返回 %d 个方案",
                             s.name, origin, dest, depart, return_, len(found))
            except Exception as exc:  # noqa: BLE001
                log.warning("[%s] 查询 %s->%s %s~%s 失败: %s", s.name, origin, dest, depart, return_, exc)
        return merged, used

    def warmup_all(self) -> None:
        for s in self.searchers:
            try:
                s.warmup()
            except Exception:  # noqa: BLE001
                log.warning("[%s] warmup 失败", s.name)

    def shutdown_all(self) -> None:
        for s in self.searchers:
            try:
                s.shutdown()
            except Exception:  # noqa: BLE001
                log.warning("[%s] shutdown 失败", s.name)
