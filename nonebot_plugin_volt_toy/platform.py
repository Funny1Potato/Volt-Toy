"""把 Uninfo 会话与各协议差异收敛到这里。

- 群/私聊统一成稳定字符串 key（含协议名，避免跨平台 ID 撞车）
- 显示名优先群名片，其次昵称，最后退回 ID
- 管理员判定：超管 / 群主 / 群管理
- 头像只在 QQ 系协议可用，其余协议静默跳过
"""

from __future__ import annotations

from typing import Any

import httpx
from nonebot import get_driver

AVATAR_URL = "https://q4.qlogo.cn/headimg_dl?dst_uin={uid}&spec=640"
MAX_AVATAR_BYTES = 5 * 1024 * 1024


def _adapter_name(session: Any) -> str:
    value = getattr(session, "adapter", None)
    if isinstance(value, str) and value:
        return value
    return type(value).__name__ if value is not None else "unknown"


def _scene(session: Any) -> Any:
    return getattr(session, "scene", None)


def user_id(session: Any) -> str:
    user = getattr(session, "user", None)
    value = getattr(user, "id", None) or getattr(session, "user_id", "")
    return str(value)


def scene_id(session: Any) -> str:
    value = getattr(_scene(session), "id", None)
    return str(value) if value is not None else "0"


def scene_type(session: Any) -> str:
    value = getattr(_scene(session), "type", None)
    text = str(value).lower() if value is not None else "group"
    return text if text in {"group", "private", "guild", "channel"} else "group"


def scope_key(session: Any) -> str:
    """群聊按群隔离，私聊按人隔离，前缀带协议名。"""
    return f"{_adapter_name(session)}:{scene_type(session)}:{scene_id(session)}"


def sender_name(session: Any) -> str:
    member = getattr(session, "member", None)
    user = getattr(session, "user", None)
    for holder in (member, user):
        name = getattr(holder, "name", None) if holder is not None else None
        if name:
            return str(name)
    return user_id(session)


def self_id(session: Any) -> str:
    for holder in (session, getattr(session, "bot", None)):
        value = getattr(holder, "self_id", None) if holder is not None else None
        if value:
            return str(value)
    return ""


def is_admin(session: Any) -> bool:
    uid = user_id(session)
    superusers = set(getattr(get_driver().config, "superusers", set()) or set())
    if uid in superusers:
        return True
    member = getattr(session, "member", None)
    role = getattr(member, "role", None) if member is not None else None
    return str(role).lower() in {"owner", "admin"} if role is not None else False


def _is_qq_like(adapter: str) -> bool:
    text = adapter.lower()
    return "onebot" in text or "qq" in text


async def fetch_avatar(session: Any, uid: str, timeout: float) -> bytes | None:
    """尽力获取头像；拿不到就返回 None，绝不影响文本消息。"""
    if not _is_qq_like(_adapter_name(session)) or not uid.isdigit():
        return None
    url = AVATAR_URL.format(uid=uid)
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200:
                return None
            if len(response.content) > MAX_AVATAR_BYTES:
                return None
            return response.content
    except Exception:
        return None
