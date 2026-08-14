"""Flight Entity Resolution（§21 + P0.7 修复）.

Strong Entity Key：carrier | flight_no | date | segment airports | departure time
Weak Match：字段不完整时生成弱键，禁止直接 merge。

resolution_confidence:
  MATCH          → 可合并 Candidate
  PROBABLE_MATCH → 待确认
  UNKNOWN        → 不合并
  CONFLICT       → 禁止合并
"""
from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import List, Optional

from ...core.contracts import RawListing, RawSegment


class ResolutionConfidence(str, Enum):
    MATCH = "MATCH"
    PROBABLE_MATCH = "PROBABLE_MATCH"
    UNKNOWN = "UNKNOWN"
    CONFLICT = "CONFLICT"


@dataclass
class ResolutionResult:
    key: str
    confidence: ResolutionConfidence
    strong: bool
    reason: str = ""


def flight_numbers(listing: RawListing) -> List[str]:
    out: List[str] = []
    for seg in listing.outbound.segments + listing.inbound.segments:
        if seg.flight_no not in out:
            out.append(seg.flight_no)
    return out


def _has_complete_segments(listing: RawListing) -> bool:
    """P0.9-2: round-trip 必须双方向 segments 都非空 + 全字段完整。

    空列表或仅单程数据 → 一律 False（绝不生成 Strong Entity Key）。
    """
    if not listing.outbound.segments:
        return False
    if not listing.inbound.segments:
        return False
    for seg in listing.outbound.segments + listing.inbound.segments:
        if not seg.flight_no or not seg.dep_time or not seg.dep_airport \
                or not seg.arr_airport or not seg.dep_date or not seg.arr_date:
            return False
    return True


def strong_entity_key(listing: RawListing) -> Optional[str]:
    """Strong key：carrier|flight_no|date|seg airports|dep time（P0.7）。"""
    if not _has_complete_segments(listing):
        return None
    parts = []
    for seg in listing.outbound.segments + listing.inbound.segments:
        parts.append(f"{seg.airline}{seg.flight_no}")
        parts.append(seg.dep_airport)
        parts.append(seg.arr_airport)
        parts.append(seg.dep_time)
    fns = "|".join(flight_numbers(listing))
    return "|".join([listing.depart_date, fns, *parts])


def weak_entity_key(listing: RawListing) -> str:
    """Weak key：date|origin|dest（字段不完整时用）。"""
    return "|".join([listing.depart_date, listing.origin_airport,
                     listing.dest_airport])


def resolve(listing_a: RawListing, listing_b: RawListing) -> ResolutionResult:
    """P0.7: 判断两 listing 是否同一实体。只有 MATCH 才允许合并。"""
    ka = strong_entity_key(listing_a)
    kb = strong_entity_key(listing_b)
    if ka is not None and kb is not None:
        if ka == kb:
            return ResolutionResult(key=ka, confidence=ResolutionConfidence.MATCH,
                                    strong=True, reason="strong keys equal")
        # 强键不同 → CONFLICT（同日期同路线不同航班号）
        if (listing_a.depart_date == listing_b.depart_date
                and listing_a.origin_airport == listing_b.origin_airport
                and listing_a.dest_airport == listing_b.dest_airport):
            return ResolutionResult(key=ka, confidence=ResolutionConfidence.CONFLICT,
                                    strong=True,
                                    reason="same route/date but different strong keys")
        return ResolutionResult(key=ka, confidence=ResolutionConfidence.UNKNOWN,
                                strong=True, reason="different routes")

    # 至少一个弱键 → PROBABLE_MATCH（不直接 merge）
    wa = weak_entity_key(listing_a)
    wb = weak_entity_key(listing_b)
    if wa == wb:
        return ResolutionResult(key=wa, confidence=ResolutionConfidence.PROBABLE_MATCH,
                                strong=False,
                                reason="weak keys equal; needs detail verification")
    return ResolutionResult(key=wa, confidence=ResolutionConfidence.UNKNOWN,
                            strong=False, reason="weak keys differ")


def entity_key(listing: RawListing) -> str:
    """兼容旧接口：优先 strong key，否则 weak key。

    注意：weak key 由调用方结合 resolution_confidence 决定是否 merge。
    """
    k = strong_entity_key(listing)
    return k if k is not None else weak_entity_key(listing)


def candidate_attributes(listing: RawListing) -> dict:
    return {
        "origin": listing.origin_airport,
        "destination": listing.dest_airport,
        "depart_date": listing.depart_date,
        "return_date": listing.return_date,
        "nights": listing.nights,
        "stops_total": listing.outbound.stops + listing.inbound.stops,
        "total_duration_min": listing.outbound.total_min + listing.inbound.total_min,
        "outbound_flight_numbers": flight_numbers(listing),
    }


def segment_label(seg: RawSegment) -> str:
    return f"{seg.airline}{seg.flight_no} {seg.dep_airport}→{seg.arr_airport}"
