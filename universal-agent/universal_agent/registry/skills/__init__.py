"""skills package — SkillProtocol + CapabilityResolver."""
from .protocol import SkillProtocol
from .resolver import CapabilityResolver, NoSkillAvailable

__all__ = ["SkillProtocol", "CapabilityResolver", "NoSkillAvailable"]
