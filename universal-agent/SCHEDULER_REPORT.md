# 调度接入验收报告（WatchDaemon）

> 日期：2026-08-14 · 环境：Python 3.12 · pytest 9.1.1

---

## PHASE COMPLETED（增强）

**目标**：把 Universal Agent 接入定时调度，让 watch 任务按基线时间自动周期性扫描（核心目标"定期扫描 agent"）。

**Implemented**
- `coordinator/scheduler/daemon.py` — **WatchDaemon**：
  - asyncio 循环驱动，无第三方依赖（复用 §15 BaselineScheduler）
  - 每 tick（默认 60s）检查 `due_tasks` → 执行到期任务
  - 扫描后 `mark_scanned` 推进 `next_scan_at` 到下一基线时间
  - 单任务失败 → FAILED（可重试），不中断整体（§48）
  - `load_watch_daemon()`：从 `tasks/*.yaml` 加载所有 watch 任务（多任务支持）
  - 进程重启恢复：TaskRegistry + Checkpoint JSON 持久化（§60）
- `apps/scheduler.py` — 调度守护 CLI：`--tasks-dir --data-dir --tick --domain --sources --live`
- `_flight_runner()`：daemon → ShadowScanCoordinator 接线（真实扫描器 + 事件链）

**Tests（+5）**：unit/test_scheduler_daemon.py
- due_tasks 检测 / tick 执行到期任务并推进 / 失败标记 FAILED 不崩溃 / 多任务加载 / 重启恢复

**端到端实测**
```text
1. 任务 WATCHING 且到期，触发 tick...
   [执行] raw=2 top5=['HGH→ZQN ¥4380', 'HGH→ZQN ¥5080']
2. 扫描计数: 1 | 推进到: 2026-08-14 15:00:00+00:00   (下一基线时间)
3. Checkpoint in_flight: {}
run_forever 3s 稳定运行，无崩溃
```

**Host coupling audit**：CLEAN ✓（daemon 在 coordinator/scheduler，通过注入 runner 与宿主解耦——接 DSH 时由宿主 Adapter 提供执行器，Core 零改动）

**Next**（可选）
- daemon 接入 DSH 定时任务（宿主 Adapter 提供 runner）
- 多域调度（hotel/jobs runner 注入）
- Adaptive Scheduler 接入（Phase B）
