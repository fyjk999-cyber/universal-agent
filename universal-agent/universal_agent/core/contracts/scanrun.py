"""ScanRun — 独立运行状态（P0.2 修复）。

禁止：一次平台临时失败 → WatchTask = FAILED → Watch 永久死亡。
ScanRun 记录每次扫描运行的独立状态；WatchTask 保持 WATCHING。
"""
from __future__ import annotations

from datetime import datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field

from .base import utc_now


class ScanRunStatus(str, Enum):
    PENDING = "PENDING"
    RUNNING = "RUNNING"
    SUCCESS = "SUCCESS"
    FAILED_RETRYABLE = "FAILED_RETRYABLE"
    FAILED_FATAL = "FAILED_FATAL"
    PARTIAL_SUCCESS = "PARTIAL_SUCCESS"
    CANCELLED = "CANCELLED"


class ScanRun(BaseModel):
    """一次扫描运行的独立状态记录。"""

    model_config = ConfigDict(extra="forbid")

    run_id: str
    task_id: str
    started_at: datetime = Field(default_factory=utc_now)
    finished_at: Optional[datetime] = None
    status: ScanRunStatus = ScanRunStatus.PENDING
    attempt: int = 1
    retry_count: int = 0
    error_type: Optional[str] = None
    error_message: Optional[str] = None
    next_retry_at: Optional[datetime] = None
    trace_id: Optional[str] = None


#: 可重试失败类型 → exponential backoff（P0.2）
RETRY_BACKOFF = [60, 300, 900, 3600]  # 1m / 5m / 15m / 1h


def is_retryable(error_type: Optional[str]) -> bool:
    """临时性失败（网络/源不可用/限流/浏览器）→ 可重试。"""
    if not error_type:
        return True
    retryable = {
        "network_timeout", "source_unavailable", "rate_limit",
        "browser_crash", "temporary_error",
    }
    return error_type in retryable


class ExecutionState(str, Enum):
    """P0.4 事务执行状态机。"""
    PREPARED = "PREPARED"
    COMMITTING = "COMMITTING"
    COMMITTED = "COMMITTED"
    VERIFYING = "VERIFYING"
    VERIFIED = "VERIFIED"
    FAILED = "FAILED"
    UNKNOWN = "UNKNOWN"
    COMPENSATING = "COMPENSATING"
    COMPENSATED = "COMPENSATED"
