"""Booking HTTP Hotel Skill（FR-082 Hotel Live Source，CH4-4.4）。"""
from __future__ import annotations

from .adapter import (
    BookingHotelSkill,
    booking_marketplace_manifest,
    booking_skill_manifest,
)

__all__ = ["BookingHotelSkill", "booking_marketplace_manifest", "booking_skill_manifest"]
