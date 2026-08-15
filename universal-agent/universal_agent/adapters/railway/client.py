"""12306 公开接口客户端（无 key）— 余票/时刻/车站，best-effort 票价。

- 会话：GET /otn/leftTicket/init 建立 cookie 会话
- 车站：/otn/resources/js/framework/station_name.js（公开，含站码映射）
- 余票/时刻：/otn/leftTicket/queryG（公开；发站/到站可能返回区域变体，按精确码过滤）
- 票价：/otn/leftTicketPrice/query（best-effort；被限流时返回 UNKNOWN，fail-closed）

合规：公开匿名接口 + 标准 UA；不做登录态/验证码绕过（SPAC §33）。
礼貌：每次查询间隔 sleep（限流友好）。
"""
from __future__ import annotations

import json
import logging
import re
import time
import urllib.parse
import urllib.request
from http.cookiejar import CookieJar
from typing import Any, Dict, List, Optional

log = logging.getLogger("ua.adapters.railway12306")

BASE = "https://kyfw.12306.cn"
UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
      "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0 Safari/537.36")

#: queryG 记录字段位置（2024+ 公开格式，经实测验证）
F_TRAIN_NO = 2      # 车次标识（票价端点用）
F_NUMBER = 3        # 车次（G531）
F_FROM_CODE = 6     # 发站码
F_TO_CODE = 7       # 到站码
F_DEPART = 8        # 发时 HH:MM
F_ARRIVE = 9        # 到时 HH:MM
F_DURATION = 10     # 历时
F_BOOKABLE = 11     # Y/N
F_DATE = 13         # YYYYMMDD

#: 余票/座位字段（部分；'有'/'无'/数字/'B4' 等表示）
SEAT_FIELDS = {
    "商务座": 15, "一等座": 16, "二等座": 17,
    "硬卧": 18, "软卧": 19, "硬座": 20, "无座": 21,
}


class Railway12306Error(RuntimeError):
    pass


class Railway12306Client:
    def __init__(self, timeout: int = 15, query_delay: float = 1.0) -> None:
        self.timeout = timeout
        self.query_delay = query_delay
        self._cj = CookieJar()
        self._op = urllib.request.build_opener(
            urllib.request.HTTPCookieProcessor(self._cj))
        self._op.addheaders = [
            ("User-Agent", UA),
            ("Referer", f"{BASE}/otn/leftTicket/init"),
        ]
        self._stations: Optional[Dict[str, str]] = None  # 中文名 -> 站码
        self._station_codes: Optional[Dict[str, str]] = None  # 站码 -> 中文名
        self._session_ok = False

    # ------------------------------------------------------------------ session
    def _ensure_session(self) -> None:
        if self._session_ok:
            return
        try:
            self._op.open(f"{BASE}/otn/leftTicket/init", timeout=self.timeout)
            self._session_ok = True
        except Exception as exc:  # noqa: BLE001
            raise Railway12306Error(f"12306 会话初始化失败: {exc}") from exc

    def _get_json(self, url: str) -> Any:
        try:
            with self._op.open(url, timeout=self.timeout) as resp:
                return json.loads(resp.read().decode("utf-8", "replace"))
        except json.JSONDecodeError as exc:
            raise Railway12306Error(f"12306 响应非 JSON: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            raise Railway12306Error(f"12306 请求失败: {exc}") from exc

    def _get_text(self, url: str) -> str:
        try:
            with self._op.open(url, timeout=self.timeout) as resp:
                return resp.read().decode("utf-8", "replace")
        except Exception as exc:  # noqa: BLE001
            raise Railway12306Error(f"12306 请求失败: {exc}") from exc

    # ------------------------------------------------------------------ stations
    def stations(self) -> Dict[str, str]:
        """中文名 -> 站码（公开数据，缓存；station_name.js 为 JS 文本）。"""
        if self._stations is not None:
            return self._stations
        raw = self._get_text(
            f"{BASE}/otn/resources/js/framework/station_name.js?station_version=1.0")
        names: Dict[str, str] = {}
        codes: Dict[str, str] = {}
        for m in re.finditer(r"@([a-z]+)\|([\u4e00-\u9fa5]+)\|([A-Z]+)\|", raw):
            names[m.group(2)] = m.group(3)
            codes[m.group(3)] = m.group(2)
        if not names:
            raise Railway12306Error("12306 车站列表为空")
        self._stations = names
        self._station_codes = codes
        return names

    def code(self, city: str) -> str:
        c = self.stations().get(city)
        if not c:
            raise Railway12306Error(f"未知车站: {city}")
        return c

    # ------------------------------------------------------------------ query
    def query_trains(self, from_city: str, to_city: str, date: str,
                     exact_match: bool = True) -> List[Dict[str, Any]]:
        """余票/时刻查询。date=YYYY-MM-DD。

        exact_match=True 时仅保留发站/到站精确等于查询站的记录
        （12306 可能返回区域变体，如上海虹桥→杭州东 会带 上海松江→杭州）。
        """
        self._ensure_session()
        from_c, to_c = self.code(from_city), self.code(to_city)
        params = urllib.parse.urlencode({
            "leftTicketDTO.train_date": date,
            "leftTicketDTO.from_station": from_c,
            "leftTicketDTO.to_station": to_c,
            "purpose_codes": "ADULT"})
        data = self._get_json(f"{BASE}/otn/leftTicket/queryG?{params}")
        d = data.get("data") or {}
        if not d.get("flag") or not d.get("result"):
            log.warning("12306 查询无结果/被限流: %s->%s %s", from_city, to_city, date)
            return []
        smap = d.get("map") or {}
        out: List[Dict[str, Any]] = []
        for rec in d["result"]:
            fields = urllib.parse.unquote(rec).split("|")
            if len(fields) <= 25:
                continue
            f_from, f_to = fields[F_FROM_CODE], fields[F_TO_CODE]
            if exact_match and (f_from != from_c or f_to != to_c):
                continue
            out.append({
                "train_no": fields[F_TRAIN_NO],
                "number": fields[F_NUMBER],
                "from_code": f_from, "to_code": f_to,
                "from_city": smap.get(f_from, f_from),
                "to_city": smap.get(f_to, f_to),
                "depart": fields[F_DEPART], "arrive": fields[F_ARRIVE],
                "duration": fields[F_DURATION],
                "bookable": fields[F_BOOKABLE],
                "date": fields[F_DATE],
                "seats": {name: (fields[pos] if pos < len(fields) else "")
                          for name, pos in SEAT_FIELDS.items()},
            })
        return out

    def query_price(self, train_no: str, from_code: str, to_code: str,
                    date: str) -> Optional[Dict[str, Any]]:
        """票价查询（best-effort；限流时返回 None → fail-closed UNKNOWN）。"""
        self._ensure_session()
        params = urllib.parse.urlencode({
            "train_no": train_no, "from_station": from_code,
            "to_station": to_code, "seat_types": "OM9", "train_date": date})
        try:
            data = self._get_json(f"{BASE}/otn/leftTicketPrice/query?{params}")
        except Railway12306Error as exc:
            log.warning("12306 票价查询失败（fail-closed UNKNOWN）: %s", exc)
            return None
        d = data.get("data")
        if not d or not d.get("flag"):
            log.info("12306 票价不可用（限流/繁忙），train=%s", train_no)
            return None
        prices = d.get("price") or d
        return prices if isinstance(prices, dict) else {"price": prices}

    @staticmethod
    def availability_label(avail: str) -> str:
        """余票字段语义化（'有'/'0'/'无'/数字/'H3' 等票码）。"""
        v = str(avail or "").strip()
        if v in ("", "无"):
            return "无票"
        if v == "有":
            return "有票"
        if v.isdigit():
            return "无票" if int(v) == 0 else f"余{int(v)}张"
        # 'B4'/'H3'/'K2' 等：12306 座别票额码（首个字母=票类标记，非余票数）
        if v and v[0].isalpha():
            return f"有票({v})"
        return f"有票({v})"
