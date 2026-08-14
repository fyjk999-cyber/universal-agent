"""任务抽象、注册表与运行上下文。

任意新任务只需：
  1. 继承 ScanTask，实现 name / describe() / run(ctx)；
  2. 在 tasks/<name>/task.py 中导出 `TASK = <实例>`；
  3. 由 scanner.run 自动发现并调度。
"""
from __future__ import annotations

import json
import logging
import os
import sys
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional

log = logging.getLogger("scanner")


class ScanTask(ABC):
    """一个定时扫描任务的抽象基类。"""

    #: 任务唯一名称（也是数据/报告目录名）
    name: str = "base"
    #: 是否启用（可在 run.py --task 时显式指定）
    enabled: bool = True
    #: 建议调度（cron 分钟/小时表达式），任务可覆盖；None 表示不安装 cron
    schedule: Optional[str] = None

    @abstractmethod
    def describe(self) -> str:
        """任务的一句话描述，用于 README / 日志。"""

    @abstractmethod
    def run(self, ctx: "TaskContext") -> Dict[str, Any]:
        """执行一次扫描，返回结构化结果（会被写入历史并渲染成报告）。

        返回值约定（JSON 可序列化）：
          {
            "scan_time": "YYYY-MM-DD HH:mm:ss",
            "summary": {...},   # 供历史对比使用的最小摘要
            "report":  {...},   # 完整报告数据（报告模板消费）
            "alerts":  [...],   # 价格提醒
          }
        """


@dataclass
class TaskContext:
    """运行上下文：数据目录、历史、汇率、日志。"""

    task: ScanTask
    data_dir: Path
    config: Dict[str, Any] = field(default_factory=dict)
    history: Any = None          # scanner.history.HistoryStore
    fx: Any = None               # scanner.fx.Fx
    dry_run: bool = False        # True 时不写磁盘（测试用）

    @property
    def history_path(self) -> Path:
        return self.data_dir / "history" / f"{self.task.name}.jsonl"

    @property
    def report_dir(self) -> Path:
        return self.data_dir / "reports" / self.task.name

    @property
    def latest_path(self) -> Path:
        return self.data_dir / "reports" / f"{self.task.name}_latest.md"


class Registry:
    """任务注册表：自动发现 tasks/ 下所有 task.py。"""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir
        self._tasks: Dict[str, ScanTask] = {}

    def discover(self) -> Dict[str, ScanTask]:
        tasks_dir = self.base_dir / "tasks"
        if not tasks_dir.is_dir():
            return {}
        for entry in sorted(tasks_dir.iterdir()):
            if not entry.is_dir():
                continue
            task_file = entry / "task.py"
            if not task_file.is_file():
                continue
            try:
                mod_name = f"tasks.{entry.name}.task"
                if str(tasks_dir.parent) not in sys.path:
                    sys.path.insert(0, str(tasks_dir.parent))
                import importlib

                mod = importlib.import_module(mod_name)
                task = getattr(mod, "TASK", None)
                if task is None or not isinstance(task, ScanTask):
                    log.warning("tasks/%s/task.py 未导出 TASK（ScanTask 实例），跳过", entry.name)
                    continue
                self._tasks[task.name] = task
                log.info("发现任务: %s — %s", task.name, task.describe())
            except Exception as exc:  # noqa: BLE001
                log.error("加载任务 %s 失败: %s", entry.name, exc)
        return self._tasks

    def get(self, name: str) -> Optional[ScanTask]:
        if not self._tasks:
            self.discover()
        return self._tasks.get(name)

    def all(self) -> List[ScanTask]:
        if not self._tasks:
            self.discover()
        return list(self._tasks.values())


def now_str() -> str:
    import datetime

    return datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")


def iso_ts() -> str:
    import datetime

    return datetime.datetime.now().isoformat(timespec="seconds")
