"""RawListing contract (§19, §47) — the raw observation before normalization.

A raw listing is what a source skill returns. It is NOT yet a Candidate.
Normalizer consumes it; replay fixtures store it verbatim.
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, ConfigDict, Field

from .base import utc_now


class RawSegment(BaseModel):
    model_config = ConfigDict(extra="allow")

    airline: str
    flight_no: str
    dep_airport: str
    arr_airport: str
    dep_time: str  # "HH:MM"
    arr_time: str
    dep_date: str  # "YYYY-MM-DD"
    arr_date: str  # "YYYY-MM-DD"
    duration_min: int
    cabin: str = "economy"


class RawLeg(BaseModel):
    """One direction of a trip (outbound or inbound)."""

    model_config = ConfigDict(extra="allow")

    segments: List[RawSegment] = Field(default_factory=list)
    total_min: int = 0
    stops: int = 0
    layovers: List[int] = Field(default_factory=list)
    layover_airports: List[str] = Field(default_factory=list)
    overnight_layover: bool = False
    airport_change: bool = False
    self_transfer: bool = False


class RawListing(BaseModel):
    """A raw round-trip listing from one source (Bing/Trip/Fliggy/...)."""

    model_config = ConfigDict(extra="allow")

    listing_id: str
    source: str
    marketplace_id: str
    task_id: str
    origin_airport: str
    dest_airport: str
    depart_date: str
    return_date: str
    nights: int
    price_cny: float
    currency: str = "CNY"
    outbound: RawLeg
    inbound: RawLeg
    url: Optional[str] = None
    luggage: Dict[str, Any] = Field(default_factory=dict)
    fetched_at: datetime = Field(default_factory=utc_now)
    extra: Dict[str, Any] = Field(default_factory=dict)


class RawHotel(BaseModel):
    """A raw hotel room offer from one source (§63)."""

    model_config = ConfigDict(extra="allow")

    hotel_id: str
    source: str
    marketplace_id: str
    task_id: str
    name: str
    city: str = ""
    address: Optional[str] = None
    brand: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    check_in: str = ""   # YYYY-MM-DD
    check_out: str = ""  # YYYY-MM-DD
    nights: int = 0
    room_name: str = ""          # free text, normalized later
    price_per_night_cny: float
    currency: str = "CNY"
    rating: float = 0.0          # 0-5
    url: Optional[str] = None
    fetched_at: datetime = Field(default_factory=utc_now)
    extra: Dict[str, Any] = Field(default_factory=dict)


class RawJob(BaseModel):
    """A raw job listing from one source (§64)."""

    model_config = ConfigDict(extra="allow")

    job_id: str
    source: str
    marketplace_id: str
    task_id: str
    title: str
    company: str
    location: str = ""
    job_reference: Optional[str] = None  # 招聘方职位编号
    salary_min_cny: Optional[float] = None
    salary_max_cny: Optional[float] = None
    salary_text: Optional[str] = None
    url: Optional[str] = None
    skills: List[str] = Field(default_factory=list)
    description: str = ""
    posted_at: Optional[str] = None
    fetched_at: datetime = Field(default_factory=utc_now)
    extra: Dict[str, Any] = Field(default_factory=dict)


class DataCompleteness(str, Enum):
    """P0.6 数据完整性等级。"""
    DISCOVERED = "DISCOVERED"   # 仅发现，信息极少
    PARTIAL = "PARTIAL"         # 部分字段
    STRUCTURED = "STRUCTURED"   # 结构化但缺验证
    VERIFIED = "VERIFIED"       # 已验证


def field_completeness_score(listing: "RawListing") -> float:
    """0-1 数据完整度：segments/航班号/时长/经停等字段齐全度。"""
    total = 0
    checks = 0
    for leg_name in ("outbound", "inbound"):
        leg = getattr(listing, leg_name)
        total += 1 if leg.segments else 0; checks += 1
        total += 1 if leg.total_min > 0 else 0; checks += 1
        total += 1 if leg.stops >= 0 and leg.segments else 0; checks += 1
        for seg in leg.segments:
            total += 1 if seg.flight_no else 0; checks += 1
            total += 1 if seg.airline else 0; checks += 1
            total += 1 if seg.dep_time else 0; checks += 1
    return round(total / max(1, checks), 3)


class RankEligibility(str, Enum):
    """P0.9-4: Final Ranking Eligibility Gate."""
    DISCOVERY_ONLY = "DISCOVERY_ONLY"    # DISCOVERED → 仅发现池
    PRELIMINARY = "PRELIMINARY"          # PARTIAL → 初选池 + 验证队列
    FINAL_ELIGIBLE = "FINAL_ELIGIBLE"    # STRUCTURED → 最终排行
    ACTION_ELIGIBLE = "ACTION_ELIGIBLE"  # VERIFIED → 可执行池


def _structurally_complete(listing: "RawListing") -> bool:
    """双方向 segments 完整（round-trip）→ 视为 STRUCTURED 结构级数据。"""
    if not listing.outbound.segments or not listing.inbound.segments:
        return False
    for seg in listing.outbound.segments + listing.inbound.segments:
        if not seg.flight_no or not seg.dep_time or not seg.dep_airport:
            return False
    return True


def rank_eligibility(listing: "RawListing") -> RankEligibility:
    """由 completeness 推导排行资格（P0.9-4）。

    - 显式 VERIFIED → ACTION_ELIGIBLE
    - 显式 STRUCTURED 或结构完整（双方向 segments）→ FINAL_ELIGIBLE
    - 显式 PARTIAL → PRELIMINARY（禁止 Final Top5）
    - 其余 → DISCOVERY_ONLY
    """
    comp = listing.extra.get("completeness", None)
    if comp == DataCompleteness.VERIFIED.value:
        return RankEligibility.ACTION_ELIGIBLE
    if comp == DataCompleteness.STRUCTURED.value:
        return RankEligibility.FINAL_ELIGIBLE
    if comp == DataCompleteness.PARTIAL.value:
        return RankEligibility.PRELIMINARY
    # 未显式标记：结构完整（旧 fixture/完整 detail 数据）→ FINAL_ELIGIBLE
    if _structurally_complete(listing):
        return RankEligibility.FINAL_ELIGIBLE
    return RankEligibility.DISCOVERY_ONLY


class RawRailway(BaseModel):
    """A raw railway trip offer from one source (P17)."""
    model_config = ConfigDict(extra="allow")
    railway_id: str
    source: str
    marketplace_id: str
    task_id: str
    train_no: str
    origin_city: str = ""
    dest_city: str = ""
    depart_date: str = ""   # YYYY-MM-DD
    depart_time: str = ""   # HH:MM
    arrive_time: str = ""
    seat_class: str = ""    # 二等座/一等座/商务座
    price_cny: float
    currency: str = "CNY"


class RawProduct(BaseModel):
    """A raw ecommerce product offer (P18)."""
    model_config = ConfigDict(extra="allow")
    product_id: str
    source: str
    marketplace_id: str
    task_id: str
    title: str
    sku: str = ""           # canonical SKU
    price_cny: float
    currency: str = "CNY"
    stock: Optional[int] = None
    coupon_discount_cny: float = 0.0


class RawDish(BaseModel):
    """A raw food/dish offer (P19)."""
    model_config = ConfigDict(extra="allow")
    dish_id: str
    source: str
    marketplace_id: str
    task_id: str
    restaurant: str
    dish_name: str
    price_cny: float
    currency: str = "CNY"
