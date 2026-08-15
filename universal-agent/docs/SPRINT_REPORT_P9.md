# SPRINT COMPLETED — P9 (Hotel Live 政策归一化)

> 日期：2026-08-14 · 测试基线 459 → **465 passed**

## 1. Problems fixed

| # | 问题 | 修复 |
|---|---|---|
| P9.0 | 无早餐/取消/税/入住归一化 | **HotelPolicy + normalize_policy**：从 extra 结构化字段或房型文本解析 |
| P9.1 | 未知政策被猜 | 未知一律 UNKNOWN（RULE 5 fail-closed） |
| P9.2 | Offer terms 无政策 | normalize_hotel 嵌入 breakfast/cancellation/tax/occupancy_max |

## 2. Files changed

```
domains/hotel/knowledge.py   (新增 HotelPolicy + normalize_policy)
domains/hotel/normalize.py   (offer terms 嵌入政策)
tests/unit/test_p9_hotel.py  (新增 6 项)
```

## 3. Tests passed

**465 passed / 0 failed**

## 4. Known limitations

- 无真实 Hotel 源 adapter（replay 已有；ctrip/booking 未接——P8 模式复用）
- policy 解析是规则版（P12 偏好学习可调 breakfast 权重，不改变政策本身）

## 5. Next sprint

**P10 — Travel Bundle**（Flight+Hotel 真实总效用优化，非 cheapest+cheapest）
