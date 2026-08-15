"""Railway Domain（P23）— FR-117 Verification（确定性，RULE-005）。

12306 是余票/时刻的权威源；验证 = 新鲜度 + 完整性：
- 新鲜度：depart_date 必须等于查询日期（拒绝缓存过期/串日）
- 完整性：余票字段必须存在（available 非空），否则 UNVERIFIED（fail-closed）
"""
from __future__ import annotations

from typing import Dict

from ...core.contracts import RawRailway


def verify_railway(raw: RawRailway, query_date: str = "") -> Dict:
    """→ {status: VERIFIED|UNVERIFIED, reasons: [...]}。"""
    reasons: list = []
    if query_date and raw.depart_date != query_date:
        reasons.append(f"日期不匹配: {raw.depart_date} != {query_date}")
    avail = str(raw.extra.get("available", "")).strip()
    if not avail:
        reasons.append("缺少余票字段（数据不完整）")
    if raw.depart_time == "" or raw.arrive_time == "":
        reasons.append("缺少时刻字段（数据不完整）")
    return {"status": "VERIFIED" if not reasons else "UNVERIFIED",
            "reasons": reasons}
