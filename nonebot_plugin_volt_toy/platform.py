"""跨协议会话解析。

参考 `nonebot_plugin_aigf_master` 的做法：优先用 uninfo 的 `get_session()`，
失败再回落到 alconna 的 `get_target()`。两者都不支持时返回 None，由调用方
给一句可读提示，而不是抛异常。
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx
from nonebot import get_driver, logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import get_target
from nonebot_plugin_uninfo import get_interface, get_session

AVATAR_URL = "https://q4.qlogo.cn/headimg_dl?dst_uin={uid}&spec=640"
MAX_AVATAR_BYTES = 5 * 1024 * 1024

_ADAPTER_ALIASES = {
    "OneBot V11": "onebot11",
    "OneBot V12": "onebot12",
}


def adapter_name_of(value: Any) -> str:
    """SupportAdapter 枚举在 3.10 下 str() 是 'SupportAdapter.xxx'，要取 .value。"""
    return str(getattr(value, "value", value) or "")


def adapter_slug(name: Any) -> str:
    text = adapter_name_of(name).strip()
    if text in _ADAPTER_ALIASES:
        return _ADAPTER_ALIASES[text]
    return re.sub(r"[^0-9a-z]+", "", text.lower()) or "unknown"


def _display_name(holder: Any) -> str:
    if holder is None:
        return ""
    for attr in ("name", "nick"):
        value = (getattr(holder, attr, None) or "").strip()
        if value:
            return str(value)
    return str(getattr(holder, "id", "") or "")


@dataclass(slots=True)
class SceneInfo:
    """一次事件所属的会话与用户。"""

    key: str
    slug: str
    scene_path: str
    chat_id: str
    user_id: str
    user_name: str
    card: str = ""
    is_private: bool = False
    is_channel: bool = False
    adapter: str = ""
    role: str = ""
    bot_id: str = ""
    scene_type: Any = None
    member_scene_type: Any = None
    member_scene_id: str = ""

    @property
    def display_user(self) -> str:
        return self.card or self.user_name or self.user_id


async def _from_uninfo(bot: Bot, event: Event, session: Any) -> SceneInfo:
    scene = session.scene
    member = getattr(session, "member", None)
    user = getattr(session, "user", None)
    parent = getattr(scene, "parent", None) or scene
    slug = adapter_slug(session.adapter)
    return SceneInfo(
        key=f"{slug}:{session.scene_path}",
        slug=slug,
        scene_path=str(session.scene_path),
        chat_id=str(scene.id),
        user_id=str(getattr(user, "id", "") or _event_user_id(event)),
        user_name=_display_name(user),
        card=str(getattr(member, "nick", "") or "").strip(),
        is_private=bool(getattr(scene, "is_private", False)),
        is_channel=bool(getattr(scene, "is_channel", False)),
        adapter=bot.adapter.get_name(),
        role=_role_name(member),
        bot_id=str(getattr(bot, "self_id", "") or ""),
        scene_type=getattr(scene, "type", None),
        member_scene_type=getattr(parent, "type", None),
        member_scene_id=str(getattr(parent, "id", "") or ""),
    )


def _role_name(member: Any) -> str:
    role = getattr(member, "role", None) if member is not None else None
    if role is None:
        return ""
    return str(getattr(role, "name", role) or "").lower()


def _event_user_id(event: Event) -> str:
    try:
        return str(event.get_user_id() or "")
    except Exception:
        return ""


async def resolve(bot: Bot, event: Event) -> SceneInfo | None:
    """解析当前事件所属会话；适配器不支持时返回 None。"""
    session = None
    try:
        session = await get_session(bot, event)
    except Exception as error:
        logger.debug(f"volt-toy: uninfo 解析会话失败: {error}")

    if session is not None:
        try:
            return await _from_uninfo(bot, event, session)
        except Exception as error:
            logger.debug(f"volt-toy: uninfo 会话结构异常: {error}")

    try:
        target = get_target(event, bot)
    except Exception as error:
        logger.debug(f"volt-toy: 无法解析会话: {error}")
        return None
    path = f"{target.parent_id}_{target.id}" if (target.channel and target.parent_id) else target.id
    slug = adapter_slug(bot.adapter.get_name())
    uid = _event_user_id(event)
    return SceneInfo(
        key=f"{slug}:{path}",
        slug=slug,
        scene_path=str(path),
        chat_id=str(target.id),
        user_id=uid,
        user_name=uid,
        is_private=bool(getattr(target, "private", False)),
        is_channel=bool(getattr(target, "channel", False)),
        adapter=bot.adapter.get_name(),
        bot_id=str(getattr(bot, "self_id", "") or ""),
    )


async def member_name(bot: Bot, session: SceneInfo | None, uid: str) -> str:
    """按 id 取显示名；取不到就退回 id。"""
    uid = str(uid or "").strip()
    if not uid or session is None:
        return uid
    interface = get_interface(bot)
    if interface is None:
        return uid
    if session.member_scene_type is not None and session.member_scene_id:
        try:
            member = await interface.get_member(
                session.member_scene_type, session.member_scene_id, uid
            )
            if member is not None:
                name = _display_name(getattr(member, "user", None))
                return name or str(getattr(member, "nick", "") or uid)
        except Exception as error:
            logger.debug(f"volt-toy: 取成员 {uid} 失败: {error}")
    try:
        user = await interface.get_user(uid)
        if user is not None:
            return _display_name(user) or uid
    except Exception as error:
        logger.debug(f"volt-toy: 取用户 {uid} 失败: {error}")
    return uid


def is_admin(bot: Bot, session: SceneInfo | None, uid: str) -> bool:
    if not uid:
        return False
    superusers = set(getattr(get_driver().config, "superusers", set()) or set())
    if uid in superusers:
        return True
    if session is None or session.is_private:
        return False
    return session.role in {"owner", "admin"}


def _is_qq_like(session: SceneInfo) -> bool:
    return session.slug in {"onebot11", "onebot12", "qq"} or "qq" in session.adapter.lower()


async def fetch_avatar(session: SceneInfo, uid: str, timeout: float) -> bytes | None:
    """尽力取头像；非 QQ 系协议或失败时返回 None。"""
    if not _is_qq_like(session) or not str(uid).isdigit():
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(AVATAR_URL.format(uid=uid))
            if response.status_code != 200 or len(response.content) > MAX_AVATAR_BYTES:
                return None
            return response.content
    except Exception as error:
        logger.debug(f"volt-toy: 头像获取失败: {error}")
        return None
