"""Flight Airport & Airline Knowledge（§21 知识层扩展）.

数据来源（借自本地"旅程智选 / Travel Reward Optimizer"项目，2026-07 调研整理）：
- 机场别名表：北京首都→PEK、上海浦东→PVG、东京成田→NRT 等 29 个常用机场，
  含中文城市名 / 机场名 / IATA 三字码（可离线使用，无需网络，RULE-003 合规）。
- 中国航司名录：民航局名录中的 46 家客运航司（IATA 码、官网、购票 URL），
  原始 JSON 见项目 data/china-airlines.json，verified_on 2026-07-23。

用途：
- `resolve_airport()` 让 Kiwi 等 Flight 源接受中文城市输入（"上海"→"PVG"），
  与 Railway 域的中文站名体验对齐。
- `airline_info()` 为机会卡片提供航司官方名称 / 官网核价链接。

Deterministic pure functions；失败一律返回 None / 显式异常（RULE-009 fail-closed）。
"""
from __future__ import annotations

import re
from typing import Dict, List, Optional

# ---------------------------------------------------------------------------
# 机场别名表（name_zh + aliases → IATA）
# ---------------------------------------------------------------------------
#: (iata, name_zh, [aliases...]) — aliases 均为已小写化的匹配词
_AIRPORT_ROWS: List[tuple] = [
    ("PEK", "北京首都国际机场", ["北京", "北京首都", "首都机场"]),
    ("PKX", "北京大兴国际机场", ["北京大兴", "大兴机场"]),
    ("PVG", "上海浦东国际机场", ["上海", "上海浦东", "浦东机场"]),
    ("SHA", "上海虹桥国际机场", ["上海虹桥", "虹桥机场"]),
    ("CAN", "广州白云国际机场", ["广州", "广州白云", "白云机场"]),
    ("SZX", "深圳宝安国际机场", ["深圳", "深圳宝安", "宝安机场"]),
    ("CTU", "成都双流国际机场", ["成都", "成都双流", "双流机场"]),
    ("TFU", "成都天府国际机场", ["成都天府", "天府机场"]),
    ("XIY", "西安咸阳国际机场", ["西安", "西安咸阳", "咸阳机场"]),
    ("HGH", "杭州萧山国际机场", ["杭州", "杭州萧山", "萧山机场"]),
    ("NKG", "南京禄口国际机场", ["南京", "南京禄口", "禄口机场"]),
    ("XMN", "厦门高崎国际机场", ["厦门", "厦门高崎", "高崎机场"]),
    ("KMG", "昆明长水国际机场", ["昆明", "昆明长水", "长水机场"]),
    ("WUH", "武汉天河国际机场", ["武汉", "武汉天河", "天河机场"]),
    ("CKG", "重庆江北国际机场", ["重庆", "重庆江北", "江北机场"]),
    ("TSN", "天津滨海国际机场", ["天津", "天津滨海", "滨海机场"]),
    ("TAO", "青岛胶东国际机场", ["青岛", "青岛胶东", "胶东机场"]),
    ("DLC", "大连周水子国际机场", ["大连", "大连周水子", "周水子机场"]),
    ("HKG", "香港国际机场", ["香港", "香港机场"]),
    ("TPE", "台北桃园国际机场", ["台北", "桃园机场"]),
    ("NRT", "东京成田国际机场", ["东京", "东京成田", "成田机场"]),
    ("HND", "东京羽田机场", ["东京羽田", "羽田机场"]),
    ("ICN", "首尔仁川国际机场", ["首尔", "首尔仁川", "仁川机场"]),
    ("SIN", "新加坡樟宜机场", ["新加坡", "新加坡樟宜", "樟宜机场"]),
    ("BKK", "曼谷素万那普机场", ["曼谷", "曼谷素万那普", "素万那普机场"]),
    ("LAX", "洛杉矶国际机场", ["洛杉矶", "洛杉矶机场"]),
    ("JFK", "纽约肯尼迪国际机场", ["纽约", "纽约肯尼迪", "肯尼迪机场"]),
    ("SFO", "旧金山国际机场", ["旧金山", "旧金山机场"]),
    ("LHR", "伦敦希思罗机场", ["伦敦", "伦敦希思罗", "希思罗机场"]),
    ("CDG", "巴黎戴高乐机场", ["巴黎", "巴黎戴高乐", "戴高乐机场"]),
]

#: alias（小写）→ IATA
AIRPORT_ALIASES: Dict[str, str] = {}
for _iata, _name_zh, _aliases in _AIRPORT_ROWS:
    for _a in _aliases:
        AIRPORT_ALIASES.setdefault(_a, _iata)
    AIRPORT_ALIASES.setdefault(_name_zh.lower().replace(" ", ""), _iata)

#: IATA → name_zh（看板展示用）
AIRPORT_NAMES_ZH: Dict[str, str] = {_iata: _name_zh for _iata, _name_zh, _ in _AIRPORT_ROWS}

_IATA_RE = re.compile(r"^[a-zA-Z]{3}$")


def _normalize(value: str) -> str:
    """小写 + 去空白与中英文括号（与 resolve 一致）。"""
    return re.sub(r"[\s（）()]", "", str(value or "")).strip().lower()


def resolve_airport(value: Optional[str]) -> Optional[str]:
    """中文城市 / 机场名 / IATA 三字码 → IATA 三字码；无法识别返回 None。

    - 已是合法三字码（大小写不敏感）→ 原样大写返回
    - 匹配别名表 → 返回 IATA
    - 其他 → None（调用方按 fail-closed 处理，不猜测）
    """
    if not value:
        return None
    norm = _normalize(value)
    if not norm:
        return None
    if _IATA_RE.match(norm):
        return norm.upper()
    return AIRPORT_ALIASES.get(norm)


def airport_name_zh(iata: Optional[str]) -> Optional[str]:
    """IATA → 中文机场名（未收录返回 None）。"""
    if not iata:
        return None
    return AIRPORT_NAMES_ZH.get(iata.upper())


# ---------------------------------------------------------------------------
# 中国航司名录（民航局名录子集：客运航司 + 集团官网购票 URL）
# ---------------------------------------------------------------------------
#: IATA → {name_zh, name_en, official_url, booking_url}
AIRLINE_CATALOG: Dict[str, dict] = {
    "CA": {"name_zh": "中国国际航空", "name_en": "Air China",
           "official_url": "https://www.airchina.com.cn/",
           "booking_url": "https://www.airchina.com.cn/"},
    "MU": {"name_zh": "中国东方航空", "name_en": "China Eastern Airlines",
           "official_url": "https://www.ceair.com/", "booking_url": "https://www.ceair.com/"},
    "FM": {"name_zh": "上海航空", "name_en": "Shanghai Airlines",
           "official_url": "https://www.ceair.com/", "booking_url": "https://www.ceair.com/"},
    "CZ": {"name_zh": "中国南方航空", "name_en": "China Southern Airlines",
           "official_url": "https://www.csair.com/", "booking_url": "https://www.csair.com/"},
    "OQ": {"name_zh": "重庆航空", "name_en": "Chongqing Airlines",
           "official_url": "https://www.csair.com/", "booking_url": "https://www.csair.com/"},
    "MF": {"name_zh": "厦门航空", "name_en": "XiamenAir",
           "official_url": "https://www.xiamenair.com/", "booking_url": "https://www.xiamenair.com/"},
    "HU": {"name_zh": "海南航空", "name_en": "Hainan Airlines",
           "official_url": "https://www.hainanairlines.com/",
           "booking_url": "https://www.hainanairlines.com/"},
    "XW": {"name_zh": "中国新华航空", "name_en": "China Xinhua Airlines",
           "official_url": "https://www.hainanairlines.com/",
           "booking_url": "https://www.hainanairlines.com/"},
    "9H": {"name_zh": "长安航空", "name_en": "Chang An Airlines",
           "official_url": "https://www.changan-air.com/",
           "booking_url": "https://www.changan-air.com/"},
    "GS": {"name_zh": "天津航空", "name_en": "Tianjin Airlines",
           "official_url": "https://www.tianjin-air.com/", "booking_url": "https://www.tianjin-air.com/"},
    "JD": {"name_zh": "首都航空", "name_en": "Beijing Capital Airlines",
           "official_url": "https://www.jdair.net/", "booking_url": "https://www.jdair.net/"},
    "Y8": {"name_zh": "金鹏航空", "name_en": "Suparna Airlines",
           "official_url": "https://www.suparnaairlines.com/",
           "booking_url": "https://www.suparnaairlines.com/"},
    "8L": {"name_zh": "祥鹏航空", "name_en": "Lucky Air",
           "official_url": "https://www.luckyair.net/", "booking_url": "https://www.luckyair.net/"},
    "SC": {"name_zh": "山东航空", "name_en": "Shandong Airlines",
           "official_url": "https://www.sda.cn/", "booking_url": "https://www.sda.cn/"},
    "KN": {"name_zh": "中国联合航空", "name_en": "China United Airlines",
           "official_url": "https://www.flycua.com/", "booking_url": "https://www.flycua.com/"},
    "ZH": {"name_zh": "深圳航空", "name_en": "Shenzhen Airlines",
           "official_url": "https://www.shenzhenair.com/", "booking_url": "https://www.shenzhenair.com/"},
    "3U": {"name_zh": "四川航空", "name_en": "Sichuan Airlines",
           "official_url": "https://www.sichuanair.com/", "booking_url": "https://www.sichuanair.com/"},
    "BK": {"name_zh": "奥凯航空", "name_en": "Okay Airways",
           "official_url": "https://www.okair.net/", "booking_url": "https://www.okair.net/"},
    "EU": {"name_zh": "成都航空", "name_en": "Chengdu Airlines",
           "official_url": "https://www.cdal.com.cn/", "booking_url": "https://www.cdal.com.cn/"},
    "9C": {"name_zh": "春秋航空", "name_en": "Spring Airlines",
           "official_url": "https://www.ch.com/", "booking_url": "https://www.ch.com/"},
    "G5": {"name_zh": "华夏航空", "name_en": "China Express Airlines",
           "official_url": "https://www.chinaexpressair.com/",
           "booking_url": "https://www.chinaexpressair.com/"},
    "DZ": {"name_zh": "东海航空", "name_en": "Donghai Airlines",
           "official_url": "https://www.donghaiair.com/", "booking_url": "https://www.donghaiair.com/"},
    "HO": {"name_zh": "吉祥航空", "name_en": "Juneyao Air",
           "official_url": "https://www.juneyaoair.com/", "booking_url": "https://www.juneyaoair.com/"},
    "CN": {"name_zh": "大新华航空", "name_en": "Grand China Air",
           "official_url": "https://www.hainanairlines.com/",
           "booking_url": "https://www.hainanairlines.com/"},
    "PN": {"name_zh": "西部航空", "name_en": "West Air",
           "official_url": "https://www.westair.cn/", "booking_url": "https://www.westair.cn/"},
    "NS": {"name_zh": "河北航空", "name_en": "Hebei Airlines",
           "official_url": "https://www.hbhk.com.cn/", "booking_url": "https://www.hbhk.com.cn/"},
    "KY": {"name_zh": "昆明航空", "name_en": "Kunming Airlines",
           "official_url": "https://www.airkunming.com/", "booking_url": "https://www.airkunming.com/"},
    "JR": {"name_zh": "幸福航空", "name_en": "Joy Air",
           "official_url": "https://www.joy-air.com/", "booking_url": "https://www.joy-air.com/"},
    "TV": {"name_zh": "西藏航空", "name_en": "Tibet Airlines",
           "official_url": "https://www.tibetairlines.com.cn/",
           "booking_url": "https://www.tibetairlines.com.cn/"},
    "GJ": {"name_zh": "长龙航空", "name_en": "Loong Air",
           "official_url": "https://www.loongair.cn/", "booking_url": "https://www.loongair.cn/"},
    "DR": {"name_zh": "瑞丽航空", "name_en": "Ruili Airlines",
           "official_url": "https://www.ruili.com/", "booking_url": "https://www.ruili.com/"},
    "QW": {"name_zh": "青岛航空", "name_en": "Qingdao Airlines",
           "official_url": "https://www.qdairlines.com/", "booking_url": "https://www.qdairlines.com/"},
    "UQ": {"name_zh": "乌鲁木齐航空", "name_en": "Urumqi Air",
           "official_url": "https://www.urumqi-air.com/", "booking_url": "https://www.urumqi-air.com/"},
    "FU": {"name_zh": "福州航空", "name_en": "Fuzhou Airlines",
           "official_url": "https://www.fuzhou-air.com/", "booking_url": "https://www.fuzhou-air.com/"},
    "AQ": {"name_zh": "九元航空", "name_en": "9 Air",
           "official_url": "https://www.9air.com/", "booking_url": "https://www.9air.com/"},
    "GX": {"name_zh": "北部湾航空", "name_en": "GX Airlines",
           "official_url": "https://www.gxairlines.com/", "booking_url": "https://www.gxairlines.com/"},
    "RY": {"name_zh": "江西航空", "name_en": "Jiangxi Air",
           "official_url": "https://www.airjiangxi.com/", "booking_url": "https://www.airjiangxi.com/"},
    "GY": {"name_zh": "多彩贵州航空", "name_en": "Colorful Guizhou Airlines",
           "official_url": "https://www.cgzair.com/", "booking_url": "https://www.cgzair.com/"},
    "A6": {"name_zh": "湖南航空", "name_en": "Hunan Airlines",
           "official_url": "https://www.airhunanair.com/", "booking_url": "https://www.airhunanair.com/"},
    "GT": {"name_zh": "桂林航空", "name_en": "Guilin Airlines",
           "official_url": "https://www.airguilin.com/", "booking_url": "https://www.airguilin.com/"},
    "LT": {"name_zh": "龙江航空", "name_en": "Longjiang Airlines",
           "official_url": "https://www.longjiangairlines.com/",
           "booking_url": "https://www.longjiangairlines.com/"},
    "B0": {"name_zh": "北京航空", "name_en": "Beijing Airlines",
           "official_url": "https://www.beijingair.com/", "booking_url": "https://www.beijingair.com/"},
    "9D": {"name_zh": "天骄航空", "name_en": "Tianjiao Airlines",
           "official_url": "https://www.tianjiaoair.com/", "booking_url": "https://www.tianjiaoair.com/"},
}


def airline_info(iata: Optional[str]) -> Optional[dict]:
    """航司 IATA → {name_zh, name_en, official_url, booking_url}；未收录返回 None。"""
    if not iata:
        return None
    return AIRLINE_CATALOG.get(iata.upper())


def airline_name_zh(iata: Optional[str]) -> str:
    """航司 IATA → 中文名（未收录返回原码，不伪造）。"""
    info = airline_info(iata)
    return info["name_zh"] if info else (iata or "?")


def airline_booking_url(iata: Optional[str]) -> Optional[str]:
    """航司 IATA → 官方购票 URL（未收录返回 None，UI 不显示链接）。"""
    info = airline_info(iata)
    return info["booking_url"] if info else None


def official_airline_hosts() -> List[str]:
    """航司名录中的官方 HTTPS 域名集合（Browser 白名单输入，去重排序）。"""
    hosts: set = set()
    for info in AIRLINE_CATALOG.values():
        url = info["official_url"]
        if url:
            try:
                from urllib.parse import urlparse
                hosts.add(urlparse(url).hostname)
            except ValueError:
                continue
    return sorted(h for h in hosts if h)
