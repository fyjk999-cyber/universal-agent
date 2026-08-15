"""coordinator.scanner package."""
from __future__ import annotations

from .hotel import HotelScanCoordinator, HotelScanOutcome
from .job import JobScanCoordinator, JobScanOutcome
from .railway import RailwayScanCoordinator, RailwayScanOutcome
from .shadow import ScanOutcome, ShadowScanCoordinator

__all__ = [
    "HotelScanCoordinator",
    "JobScanCoordinator",
    "JobScanOutcome",
    "HotelScanOutcome",
    "RailwayScanCoordinator",
    "RailwayScanOutcome",
    "ScanOutcome",
    "ShadowScanCoordinator",
]
