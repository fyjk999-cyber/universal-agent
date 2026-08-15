# SPRINT COMPLETED — P17/P18/P19 (Railway + Ecommerce + Food)

> 日期：2026-08-14 · 测试基线 496 → **500 passed**

## 1. Problems fixed

| # | Domain | 实现 |
|---|---|---|
| P17 | Railway | RawRailway 契约 + normalize（train_no/席别/时间/价格）+ entity_key |
| P18 | Ecommerce | RawProduct 契约 + normalize（canonical SKU + coupon-aware 有效价）+ entity_key |
| P19 | Food | RawDish 契约 + normalize（餐厅/菜品/价格）+ entity_key |

三个 Domain 全部复用既有 Core 契约（Candidate/Offer/Quote/Evidence），**零 Core 修改**。

## 2. Files changed

```
core/contracts/raw.py            (RawRailway/RawProduct/RawDish)
core/contracts/__init__.py       (导出)
domains/railway/normalize.py     (新增)
domains/ecommerce/normalize.py   (新增)
domains/food/normalize.py        (新增)
domains/{railway,ecommerce,food}/__init__.py (导出)
tests/unit/test_p17_19_domains.py (新增 4 项)
```

## 3. Tests passed

**500 passed / 0 failed**

## 4. Next sprint

**P20 — Jarvis Integration**（真正 JarvisHostAdapter；Host Swap Core 零修改）
