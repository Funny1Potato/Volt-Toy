"""跨协议会话解析（依据 nonebot-plugin-uninfo 与 alconna 官方文档）。

- `get_session(bot, event)`：uninfo 的公开接口，适配器不支持时返回 None
- `get_target(event, bot)`：alconna 的回落，只保证有会话 id
- 会话键：`适配器slug:scene_path`，scene_path 由 uninfo 统一（群=群号，频道=父id_子id）
- 昵称/头像：uninfo 的 `User.name` / `User.avatar`，取不到再退回 id
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

import httpx
from nonebot import get_driver, logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna.uniseg import get_target
from nonebot_plugin_uninfo import get_interface, get_session

MAX_AVATAR_BYTES = 5 * 1024 * 1024

_ADAPTER_ALIASES = {
    "OneBot V11": "onebot11",
    "OneBot V12": "onebot12",
}

# uninfo 在各适配器里统一了角色 id（见 uninfo permission.py 的 ADMIN/OWNER）
_ADMIN_ROLE_IDS = {"OWNER", "ADMINISTRATOR"}
_ADMIN_ROLE_NAMES = {"owner", "admin"}


def adapter_name_of(value: Any) -> str:
    """SupportAdapter 是枚举，必须取 .value 才是 'onebot11'。"""
    return str(getattr(value, "value", value) or "")


def adapter_slug(name: Any) -> str:
    text = adapter_name_of(name).strip()
    if text in _ADAPTER_ALIASES:
        return _ADAPTER_ALIASES[text]
    return re.sub(r"[^0-9a-z]+", "", text.lower()) or "unknown"


def _user_name(user: Any) -> str:
    if user is None:
        return ""
    return str(getattr(user, "name", None) or getattr(user, "nick", None) or "")


@dataclass(slots=True)
class SceneInfo:
    key: str
    slug: str
    scene_path: str
    chat_id: str
    user_id: str
    user_name: str
    card: str = ""
    avatar: str = ""
    is_private: bool = False
    is_channel: bool = False
    adapter: str = ""
    role_id: str = ""
    role_name: str = ""
    bot_id: str = ""
    scene_type: Any = None
    member_scene_type: Any = None
    member_scene_id: str = ""

    @property
    def display_user(self) -> str:
        return self.card or self.user_name or self.user_id


def _role_fields(member: Any) -> tuple[str, str]:
    role = getattr(member, "role", None) if member is not None else None
    if role is None:
        return "", ""
    return str(getattr(role, "id", "") or ""), str(getattr(role, "name", "") or "")


async def _from_uninfo(bot: Bot, event: Event, session: Any) -> SceneInfo:
    scene = session.scene
    member = getattr(session, "member", None)
    user = getattr(session, "user", None)
    parent = getattr(scene, "parent", None) or scene
    slug = adapter_slug(session.adapter)
    role_id, role_name = _role_fields(member)
    return SceneInfo(
        key=f"{slug}:{session.scene_path}",
        slug=slug,
        scene_path=str(session.scene_path),
        chat_id=str(scene.id),
        user_id=str(getattr(user, "id", "") or _event_user_id(event)),
        user_name=_user_name(user),
        card=str(getattr(member, "nick", "") or "").strip(),
        avatar=str(getattr(user, "avatar", "") or ""),
        is_private=bool(getattr(scene, "is_private", False)),
        is_channel=bool(getattr(scene, "is_channel", False)),
        adapter=bot.adapter.get_name(),
        role_id=role_id,
        role_name=role_name.lower(),
        bot_id=str(getattr(session, "self_id", "") or getattr(bot, "self_id", "")),
        scene_type=getattr(scene, "type", None),
        member_scene_type=getattr(parent, "type", None),
        member_scene_id=str(getattr(parent, "id", "") or ""),
    )


def _event_user_id(event: Event) -> str:
    try:
        return str(event.get_user_id() or "")
    except Exception:
        return ""


async def resolve(bot: Bot, event: Event) -> SceneInfo | None:
    """解析当前事件所属会话；适配器不支持时返回 None。"""
    try:
        session = await get_session(bot, event)
    except Exception as error:
        logger.debug(f"volt-toy: uninfo 解析会话失败: {error}")
        session = None

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
    """按 id 取显示名：群名片 > 昵称 > id。"""
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
                return str(getattr(member, "nick", "") or _user_name(getattr(member, "user", None)) or uid)
        except Exception as error:
            logger.debug(f"volt-toy: 取成员 {uid} 失败: {error}")
    try:
        user = await interface.get_user(uid)
        if user is not None:
            return _user_name(user) or uid
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
    return session.role_id in _ADMIN_ROLE_IDS or session.role_name in _ADMIN_ROLE_NAMES


def _qq_like(session: SceneInfo) -> bool:
    return session.slug in {"onebot11", "onebot12", "qq"} or "qq" in session.adapter.lower()


async def _avatar_url(bot: Bot, session: SceneInfo, uid: str) -> str:
    """优先用 uninfo 给出的头像地址；QQ 系协议再用 qlogo 兜底。"""
    if uid == session.user_id and session.avatar:
        return session.avatar
    interface = get_interface(bot)
    if interface is not None:
        try:
            user = await interface.get_user(uid)
            if user is not None and user.avatar:
                return str(user.avatar)
        except Exception as error:
            logger.debug(f"volt-toy: 取头像地址失败: {error}")
    if _qq_like(session) and uid.isdigit():
        return f"https://q4.qlogo.cn/headimg_dl?dst_uin={uid}&spec=640"
    return ""


async def fetch_avatar(bot: Bot, session: SceneInfo, uid: str, timeout: float) -> bytes | None:
    """尽力取头像；拿不到就返回 None，不影响文本消息。"""
    url = await _avatar_url(bot, session, uid)
    if not url.startswith(("http://", "https://")):
        return None
    try:
        async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
            response = await client.get(url)
            if response.status_code != 200 or len(response.content) > MAX_AVATAR_BYTES:
                return None
            return response.content
    except Exception as error:
        logger.debug(f"volt-toy: 头像下载失败: {error}")
        return None
