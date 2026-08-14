"""coordinator.scanner package."""
from __future__ import annotations

from .hotel import HotelScanCoordinator, HotelScanOutcome
from .job import JobScanCoordinator, JobScanOutcome
from .shadow import ScanOutcome, ShadowScanCoordinator

__all__ = [
    "HotelScanCoordinator",
    "JobScanCoordinator",
    "JobScanOutcome",
    "HotelScanOutcome",
    "ScanOutcome",
    "ShadowScanCoordinator",
]
