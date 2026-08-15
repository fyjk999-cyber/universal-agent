"""Ecommerce Domain（P18）— 商品标准化（canonical SKU）。"""
from __future__ import annotations

from typing import Tuple

from ...core.contracts import (
    Candidate,
    Evidence,
    Money,
    Offer,
    Quote,
    RawProduct,
    new_id,
)


def entity_key(raw: "RawProduct") -> str:
    return raw.sku or f"{raw.title}|{raw.marketplace_id}"


def normalize_product(raw: RawProduct, task_id: str) -> Tuple[Candidate, Offer, Quote, Evidence]:
    key = entity_key(raw)
    # coupon-aware effective cost
    effective = max(raw.price_cny - raw.coupon_discount_cny, 0.0)
    candidate = Candidate(
        candidate_id=new_id("ecand"), domain="ecommerce", task_id=task_id,
        entity_key=key,
        attributes={"title": raw.title, "sku": raw.sku, "stock": raw.stock,
                    "coupon_discount_cny": raw.coupon_discount_cny},
        source_ids=[raw.marketplace_id], is_verified=False,
    )
    offer = Offer(
        offer_id=new_id("eoff"), candidate_id=candidate.candidate_id,
        marketplace_id=raw.marketplace_id,
        terms={"sku": raw.sku, "title": raw.title},
    )
    quote = Quote(
        quote_id=new_id("equote"), offer_id=offer.offer_id,
        price=Money(amount=effective, currency=raw.currency),
        method="search", confidence=0.9,
        snapshot_reference=raw.product_id, source=raw.marketplace_id,
    )
    evidence = Evidence(
        evidence_id=new_id("eevid"), field="effective_price", value=effective,
        source=raw.marketplace_id, method="search_result",
        snapshot_reference=raw.product_id, confidence=0.9,
    )
    return candidate, offer, quote, evidence
