"""Shadow scan CLI — run the Queenstown watch end-to-end (SHADOW MODE).

Usage:
  # Replay 模式（无网络，fixture 回放）:
  ../.venv/bin/python -m universal_agent.apps.shadow_scan \
      --task tasks/queenstown-travel-watch.yaml \
      --fixtures tests/replay/fixtures \
      --sources ctrip,fliggy

  # Live 模式（真实 Skyscanner 浏览器抓取，需本机 Chrome）:
  ../.venv/bin/python -m universal_agent.apps.shadow_scan --live

No purchase, no network — replays fixtures through the full pipeline and
prints the Top5 recommendations.
"""
from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path

from universal_agent.adapters.replay import make_fetchers
from universal_agent.adapters.skyscanner import (
    SkyscannerAdapter,
    SkyscannerConfig,
    skyscanner_marketplace_manifest,
)
from universal_agent.coordinator.scanner import ShadowScanCoordinator
from universal_agent.coordinator.task_registry import load_task_spec
from universal_agent.events import InProcessEventBus
from universal_agent.memory import ObservationStore
from universal_agent.registry import MarketplaceManifest, SkillRegistry


def _build_registry(sources: list[str]) -> SkillRegistry:
    reg = SkillRegistry()
    for i, mid in enumerate(sources):
        reg.register_marketplace(MarketplaceManifest(
            id=mid, domains=["flight"], health="HEALTHY",
            capabilities={"search": True},
            trust={"default_score": 0.95 - i * 0.05}))
    return reg


async def _run(task_path: Path, fixtures: Path, sources: list[str],
               live: bool = False, max_queries: int = 60) -> None:
    task = load_task_spec(task_path)
    reg = _build_registry(sources)
    fetchers = make_fetchers(fixtures, sources)
    if live:
        # 真实源：Skyscanner 浏览器抓取（Tier2 验证），与 replay 并存
        reg.register_marketplace(skyscanner_marketplace_manifest())
        sky = SkyscannerAdapter(config=SkyscannerConfig(
            max_results=5, request_delay_sec=1, timeout_ms=45000,
            headless=True, real_chrome=True))
        fetchers["skyscanner"] = sky.fetch
    coord = ShadowScanCoordinator(
        bus=InProcessEventBus(),
        registry=reg,
        observations=ObservationStore(fixtures.parent / ".obs"),
        fetchers=fetchers,
        max_queries=max_queries,
    )
    outcome = await coord.scan(task)
    print(json.dumps(outcome.summary(), ensure_ascii=False, indent=2))
    print("\n--- Top5 推荐 ---")
    for i, r in enumerate(outcome.top5, 1):
        stops = r.outbound.stops + r.inbound.stops
        print(f"  #{i} {r.origin_airport}→{r.dest_airport} "
              f"{r.depart_date}~{r.return_date} ¥{r.price_cny:.0f} 转机{stops}次")
    if outcome.verification is not None:
        v = outcome.verification
        print(f"\n[验证] {v.verified_by} passed={v.passed} "
              f"confidence={v.confidence.final_confidence} "
              f"evidence={len(v.evidence)}条")
    if outcome.opportunity is not None:
        o = outcome.opportunity
        print(f"[机会] score={o.total_score} hist_low={o.historical_low} "
              f"drop=¥{o.absolute_drop_cny:.0f} ({o.percent_drop:.1f}%)")
    if outcome.notified:
        print("\n[通知] 已触发推荐通知（历史最低/机会分达标）")


def main() -> None:
    parser = argparse.ArgumentParser(description="Shadow scan CLI (SHADOW MODE)")
    parser.add_argument("--task", default="tasks/queenstown-travel-watch.yaml")
    parser.add_argument("--fixtures", default="tests/replay/fixtures")
    parser.add_argument("--sources", default="ctrip,fliggy")
    parser.add_argument("--live", action="store_true",
                        help="接入真实 Skyscanner 浏览器抓取（需本机 Chrome）")
    parser.add_argument("--max-queries", type=int, default=60)
    args = parser.parse_args()
    asyncio.run(_run(Path(args.task), Path(args.fixtures),
                     [s.strip() for s in args.sources.split(",")],
                     live=args.live, max_queries=args.max_queries))


if __name__ == "__main__":
    main()
