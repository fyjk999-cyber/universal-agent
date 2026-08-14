"""CLI 入口：扫描 / 历史 / 安装 cron / 测试。

用法：
  .venv/bin/python -m scanner.run --task flights_zqn scan
  .venv/bin/python -m scanner.run --task flights_zqn history [--tail 5]
  .venv/bin/python -m scanner.run --task flights_zqn cron-install
  .venv/bin/python -m scanner.run --task flights_zqn cron-remove
  .venv/bin/python -m scanner.run --task flights_zqn test-search

所有子命令都可省略 --task（默认全部已发现任务）。
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(BASE_DIR))

from scanner.core import TaskContext, iso_ts, now_str  # noqa: E402
from scanner.fx import Fx  # noqa: E402
from scanner.history import HistoryStore  # noqa: E402
from scanner.report import write_report  # noqa: E402


def _setup_logging(verbose: bool = False) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )


def _build_ctx(task, args) -> TaskContext:
    data_dir = Path(getattr(args, "data_dir", None) or BASE_DIR / "data")
    fx = Fx(cache_path=data_dir / "fx_cache.json")
    fx.load()
    ctx = TaskContext(
        task=task,
        data_dir=data_dir,
        history=HistoryStore(data_dir / "history" / f"{task.name}.jsonl"),
        fx=fx,
        dry_run=getattr(args, "dry_run", False),
    )
    return ctx


def _selected_tasks(args, registry) -> list:
    if getattr(args, "task", None):
        task = registry.get(args.task)
        if task is None:
            print(f"未找到任务: {args.task}（可用: {[t.name for t in registry.all()]}）", file=sys.stderr)
            sys.exit(2)
        return [task]
    return registry.all()


def cmd_scan(args) -> None:
    from scanner.core import Registry

    registry = Registry(BASE_DIR)
    tasks = _selected_tasks(args, registry)
    if not tasks:
        print("没有任何可用任务", file=sys.stderr)
        sys.exit(1)
    for task in tasks:
        logging.getLogger("scanner").info("开始扫描任务: %s", task.name)
        ctx = _build_ctx(task, args)
        try:
            result = task.run(ctx)
        except Exception as exc:  # noqa: BLE001
            logging.getLogger("scanner").exception("任务 %s 扫描失败", task.name)
            print(f"[{task.name}] 扫描失败: {exc}", file=sys.stderr)
            continue
        if result is None:
            continue
        result.setdefault("scan_time", now_str())
        result.setdefault("_ts_iso", iso_ts())
        # 历史归档（min_price 等关键字段放到 summary）
        summary = result.get("summary") or {}
        summary.setdefault("min_price", result.get("min_price"))
        result["summary"] = summary
        ctx.history.append({"scan_time": result["scan_time"], "summary": summary})
        # 报告渲染：任务自带 render_report(result, ctx)
        md = task.render_report(result, ctx) if hasattr(task, "render_report") else _generic_render(task, result)
        if not ctx.dry_run:
            write_report(task.name, ctx.data_dir, md, result["scan_time"].replace(" ", "_").replace(":", "-"))
        print(f"[{task.name}] 扫描完成，最低价 {summary.get('min_price')}")


def _generic_render(task, result) -> str:
    import json

    return f"# {task.name} 扫描报告\n\n扫描时间: {result.get('scan_time')}\n\n```json\n{json.dumps(result, ensure_ascii=False, indent=2)}\n```\n"


def cmd_history(args) -> None:
    from scanner.core import Registry

    registry = Registry(BASE_DIR)
    for task in _selected_tasks(args, registry):
        store = HistoryStore(BASE_DIR / "data" / "history" / f"{task.name}.jsonl")
        records = store.read_all()
        print(f"== {task.name}: 共 {len(records)} 次扫描 ==")
        tail = args.tail
        for rec in records[-tail:]:
            print(f"  {rec.get('scan_time')}  min_price={rec.get('summary', {}).get('min_price')}")


def cmd_cron_install(args) -> None:
    """为任务的 schedule 安装 crontab 条目（绝对路径、防重）。"""
    import subprocess

    from scanner.core import Registry

    registry = Registry(BASE_DIR)
    tasks = _selected_tasks(args, registry)
    py = BASE_DIR / ".venv" / "bin" / "python"
    script = BASE_DIR / "scanner" / "run.py"
    log_dir = BASE_DIR / "data" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)

    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    lines = [ln for ln in existing.splitlines() if ln.strip()]
    marker = "# dsh-scanner"
    lines = [ln for ln in lines if marker not in ln and not ln.strip().startswith("# dsh-scanner:")]
    for task in tasks:
        if not task.schedule:
            print(f"[{task.name}] 未定义 schedule，跳过 cron 安装")
            continue
        hour_min = task.schedule  # 例如 "0 9,15,21 * * *"
        line = f"{hour_min} {py} {script} --task {task.name} scan >> {log_dir}/cron.log 2>&1 {marker}:{task.name}"
        lines.append(line)
        print(f"[{task.name}] 安装 cron: {hour_min}")
    new_crontab = "\n".join(lines) + "\n"
    subprocess.run(["crontab", "-"], input=new_crontab, text=True, check=True)
    print("crontab 已更新，当前条目：")
    print(new_crontab)


def cmd_cron_remove(args) -> None:
    import subprocess

    existing = subprocess.run(["crontab", "-l"], capture_output=True, text=True).stdout
    lines = [ln for ln in existing.splitlines() if "# dsh-scanner" not in ln]
    subprocess.run(["crontab", "-"], input="\n".join(lines) + "\n", text=True, check=True)
    print("已移除所有 dsh-scanner 定时条目")


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="通用定时扫描框架")
    parser.add_argument("--task", help="任务名（省略则全部）")
    parser.add_argument("--data-dir", default=None, help="数据目录（默认 <项目>/data）")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("scan")
    hp = sub.add_parser("history")
    hp.add_argument("--tail", type=int, default=10)
    sub.add_parser("cron-install")
    sub.add_parser("cron-remove")
    sp = sub.add_parser("test-search")
    sp.add_argument("--query", help="测试搜索查询参数（任务自定义）")
    args = parser.parse_args(argv)
    _setup_logging(args.verbose)

    if args.cmd == "scan":
        cmd_scan(args)
    elif args.cmd == "history":
        cmd_history(args)
    elif args.cmd == "cron-install":
        cmd_cron_install(args)
    elif args.cmd == "cron-remove":
        cmd_cron_remove(args)
    elif args.cmd == "test-search":
        from scanner.core import Registry

        registry = Registry(BASE_DIR)
        task = registry.get(args.task) if args.task else None
        if task is None:
            print("test-search 需要 --task <name>", file=sys.stderr)
            return 2
        ctx = _build_ctx(task, args)
        getattr(task, "test_search", lambda ctx, q: print("任务未实现 test_search"))(ctx, args.query)
    return 0


if __name__ == "__main__":
    sys.exit(main())
