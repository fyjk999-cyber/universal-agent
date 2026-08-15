from .normalize import entity_key, normalize_railway
from .scoring import score_railway
from .verify import verify_railway

__all__ = ["entity_key", "normalize_railway", "score_railway", "verify_railway"]

# SPAC §20：满足 FR-110~117 后标记（2026-08-15：12306 Live 源 + 全流程实测）
RAILWAY_LIVE_READY = True
