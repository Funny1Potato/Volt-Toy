"""Volt-Toy 内核：与框架无关的抽取、记账、文案与业务编排。

只依赖标准库。适配层负责提供存储路径、会话信息与消息发送。
"""

from .model import TIERS, Roll, Tier, settle, tier_of
from .rankings import kings, top
from .records import Record, Result, apply_zap, new_record, roll_day
from .service import Outcome, ZapRequest, ZapService
from .settings import Settings
from .state import RuntimeState
from .storage import JsonStore, JsonlLog

__all__ = [
    "TIERS",
    "Roll",
    "Tier",
    "settle",
    "tier_of",
    "kings",
    "top",
    "Record",
    "Result",
    "apply_zap",
    "new_record",
    "roll_day",
    "Outcome",
    "ZapRequest",
    "ZapService",
    "Settings",
    "RuntimeState",
    "JsonStore",
    "JsonlLog",
]

__version__ = "0.1.5"
