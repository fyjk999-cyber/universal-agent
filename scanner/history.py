"""历史记录存储与趋势对比（任务无关）。

每个任务一份 JSONL 文件：每次扫描追加一行完整记录（JSON）。
提供：最近一次记录、历史最低价、与上一次的差值、新低判断。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("scanner.history")


class HistoryStore:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)

    # ---- 写入 ----
    def append(self, record: Dict[str, Any]) -> None:
        """追加一条扫描记录。record 必须 JSON 可序列化。"""
        with self.path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")

    # ---- 读取 ----
    def read_all(self) -> List[Dict[str, Any]]:
        if not self.path.exists():
            return []
        records = []
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    records.append(json.loads(line))
                except json.JSONDecodeError:
                    log.warning("跳过损坏的历史记录行: %s...", line[:80])
        return records

    def last(self) -> Optional[Dict[str, Any]]:
        records = self.read_all()
        return records[-1] if records else None

    def count(self) -> int:
        return len(self.read_all())

    # ---- 趋势分析 ----
    def price_history(self, key: str = "min_price") -> List[Dict[str, Any]]:
        """返回 [(ts, price), ...] 序列，忽略缺失价格的记录。"""
        out = []
        for rec in self.read_all():
            summary = rec.get("summary", {})
            price = summary.get(key)
            if price is None:
                price = rec.get(key)
            if price is None:
                continue
            try:
                out.append({"ts": rec.get("scan_time", ""), "price": float(price)})
            except (TypeError, ValueError):
                continue
        return out

    def lowest_ever(self, key: str = "min_price") -> Optional[Dict[str, Any]]:
        """历史最低（含本次之前）。"""
        seq = self.price_history(key)
        if not seq:
            return None
        return min(seq, key=lambda x: x["price"])

    def delta_vs_previous(self, current_price: float, key: str = "min_price") -> Optional[float]:
        """与上一次扫描的差价（当前 - 上次）；无上次记录返回 None。"""
        seq = self.price_history(key)
        if len(seq) < 2:
            return None
        prev = seq[-2]["price"]
        return current_price - prev
