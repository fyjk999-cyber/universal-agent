"""航班结果数据模型（任务相关但结构通用）。

一个 Itinerary = 一次往返方案。所有时间用分钟表示，价格统一 CNY。
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class Segment:
    """一个航段（起飞-降落）。"""

    airline: str          # 运营航司代码，如 CA
    flight_no: str        # 航班号，如 CA123
    dep_airport: str      # 出发机场代码
    arr_airport: str      # 到达机场代码
    dep_time: str         # 本地起飞 "HH:MM"
    arr_time: str         # 本地到达 "HH:MM"
    dep_date: str         # "YYYY-MM-DD"
    arr_date: str         # "YYYY-MM-DD"（跨日时为 +1 等）
    duration_min: int
    cabin: str = "economy"
    aircraft: str = ""


@dataclass
class Leg:
    """去程或返程的一段行程（可含多个航段）。"""

    segments: List[Segment]
    total_min: int = 0            # 总时长（含转机）
    stops: int = 0                # 转机次数
    layovers: List[int] = field(default_factory=list)  # 每次转机等待分钟
    layover_airports: List[str] = field(default_factory=list)
    overnight_layover: bool = False
    airport_change: bool = False  # 是否换机场转机
    self_transfer: bool = False   # 是否自行转机

    @property
    def first(self) -> Optional[Segment]:
        return self.segments[0] if self.segments else None

    @property
    def last(self) -> Optional[Segment]:
        return self.segments[-1] if self.segments else None


@dataclass
class Itinerary:
    """一个完整往返方案。"""

    origin_airport: str           # 实际出发机场（HGH/PVG/SHA）
    dest_airport: str
    depart_date: str
    return_date: str
    nights: int
    outbound: Leg
    inbound: Leg
    price_cny: float
    price_orig: Optional[float] = None   # 原始货币价格
    currency_orig: str = "CNY"
    fx_note: str = ""              # 汇率说明（原始货币 → CNY 换算）
    luggage: Dict[str, Any] = field(default_factory=dict)  # {"carry_on":..., "checked":...}
    booking_channel: str = ""      # 携程 / 去哪儿 / Bing(Fareportal) / 航司官网 ...
    link: str = ""
    source: str = ""               # 数据源标识
    airlines: List[str] = field(default_factory=list)
    airline_full: str = ""
    score: Optional[float] = None
    score_breakdown: Dict[str, Any] = field(default_factory=dict)
    notes: List[str] = field(default_factory=list)
    price_verified: bool = False
    is_direct: bool = False

    @property
    def total_duration_min(self) -> int:
        return self.outbound.total_min + self.inbound.total_min

    def to_dict(self) -> Dict[str, Any]:
        return {
            "origin_airport": self.origin_airport,
            "dest_airport": self.dest_airport,
            "depart_date": self.depart_date,
            "return_date": self.return_date,
            "nights": self.nights,
            "outbound": {
                "stops": self.outbound.stops,
                "total_min": self.outbound.total_min,
                "layovers": self.outbound.layovers,
                "layover_airports": self.outbound.layover_airports,
                "overnight_layover": self.outbound.overnight_layover,
                "airport_change": self.outbound.airport_change,
                "self_transfer": self.outbound.self_transfer,
                "segments": [s.__dict__ for s in self.outbound.segments],
            },
            "inbound": {
                "stops": self.inbound.stops,
                "total_min": self.inbound.total_min,
                "layovers": self.inbound.layovers,
                "layover_airports": self.inbound.layover_airports,
                "overnight_layover": self.inbound.overnight_layover,
                "airport_change": self.inbound.airport_change,
                "self_transfer": self.inbound.self_transfer,
                "segments": [s.__dict__ for s in self.inbound.segments],
            },
            "price_cny": self.price_cny,
            "price_orig": self.price_orig,
            "currency_orig": self.currency_orig,
            "luggage": self.luggage,
            "booking_channel": self.booking_channel,
            "link": self.link,
            "source": self.source,
            "airlines": self.airlines,
            "score": self.score,
            "is_direct": self.is_direct,
            "total_duration_min": self.total_duration_min,
            "notes": self.notes,
        }
