"""Mock factory helpers for the Jarvis host (contract tests use these)."""
from __future__ import annotations

from pathlib import Path

from .adapter import MockJarvisHostAdapter
from .event_bridge import JarvisEventBridge


def mock_jarvis_host(data_dir: Path) -> MockJarvisHostAdapter:
    return MockJarvisHostAdapter(data_dir=data_dir)
