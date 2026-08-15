"""调度守护可执行入口 — 让 watch 任务按基线时间自动扫描.

用法:
  ../.venv/bin/python -m universal_agent.apps.scheduler \
      --tasks-dir tasks --data-dir data \
      --tick 60 --domain flight

SHADOW MODE：默认用 replay fixture 执行（不联网）；--live 接真实源。
"""
from __future__ import annotations

import argparse
import asyncio
import logging
from pathlib import Path
from typing import Dict

from universal_agent.coordinator.scheduler import load_watch_daemon
from universal_agent.core.contracts import WatchTask

log = logging.getLogger("ua.apps.scheduler")


def _flight_runner(fixtures: Path, sources: list[str], live: bool,
                   notifier=None):
    """返回一个 task → 执行 flight 扫描的 runner。

    notifier（FR-031）：机会通知真实投递回调（host send_notification），可选。
    """
    from universal_agent.adapters.replay import make_fetchers
    from universal_agent.adapters.skyscanner import (
        SkyscannerAdapter, SkyscannerConfig, skyscanner_marketplace_manifest)
    from universal_agent.coordinator.scanner import ShadowScanCoordinator
    from universal_agent.events import InProcessEventBus
    from universal_agent.memory import ObservationStore
    from universal_agent.registry import MarketplaceManifest, SkillRegistry

    reg = SkillRegistry()
    for mid in sources:
        reg.register_marketplace(MarketplaceManifest(
            id=mid, domains=["flight"], health="HEALTHY",
            capabilities={"search": True}, trust={"default_score": 0.9}))
    fetchers = make_fetchers(fixtures, sources)
    if live:
        reg.register_marketplace(skyscanner_marketplace_manifest())
        sky = SkyscannerAdapter(config=SkyscannerConfig(
            max_results=3, request_delay_sec=1, timeout_ms=45000,
            headless=True, real_chrome=True))
        fetchers["skyscanner"] = sky.fetch

    async def runner(task: WatchTask) -> Dict:
        coord = ShadowScanCoordinator(
            bus=InProcessEventBus(), registry=reg,
            observations=ObservationStore(Path("/tmp/ua-sched-obs")),
            fetchers=fetchers, max_queries=10, notifier=notifier)
        outcome = await coord.scan(task)
        return outcome.summary()

    return runner


async def _run(tasks_dir: Path, data_dir: Path, tick: int,
               domain: str, sources: list[str], live: bool) -> None:
    fixtures = Path(__file__).resolve().parent.parent.parent / "tests" / "replay" / "fixtures"
    runner = _flight_runner(fixtures, sources, live) if domain == "flight" else None
    daemon = await load_watch_daemon(tasks_dir, data_dir, runner=runner,
                                     tick_seconds=tick)
    try:
        await daemon.run_forever()
    except KeyboardInterrupt:
        log.info("收到中断，退出")
        await daemon.stop()


def main() -> None:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Watch 调度守护")
    parser.add_argument("--tasks-dir", default="tasks")
    parser.add_argument("--data-dir", default="data")
    parser.add_argument("--tick", type=int, default=60)
    parser.add_argument("--domain", default="flight")
    parser.add_argument("--sources", default="ctrip,fliggy")
    parser.add_argument("--live", action="store_true")
    args = parser.parse_args()
    asyncio.run(_run(Path(args.tasks_dir), Path(args.data_dir), args.tick,
                     args.domain, args.sources.split(","), args.live))


if __name__ == "__main__":
    main()
