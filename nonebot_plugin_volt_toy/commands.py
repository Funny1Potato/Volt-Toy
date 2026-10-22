"""指令层：Alconna 解析参数，平台层解析会话，业务在内核 ZapService。

写法依据：
- nonebot 官方最佳实践 `on_alconna` 页面：`Match[<type>]` 注入、`use_cmd_start`
  默认是 False（必须显式打开才会响应 `/` 前缀）、`on_alconna(..., priority=, block=)`
  通过 **kwargs 转发给 matcher。
- alconna `uniseg` 页面：用 `UniMessage([Text(...), Image(...)])` 组装并 `.send()`；
  `At` 的字段是 `flag/target/display`，`flag` 可能是 role/channel，需要过滤。
"""

from __future__ import annotations

from typing import Any

from arclet.alconna import Alconna, Args
from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import At, Image, Match, on_alconna
from nonebot_plugin_alconna.uniseg import Text, UniMessage

from volt_toy_core import texts
from volt_toy_core.render import info_text, rank_king, rank_kwh, rank_max, rank_top
from volt_toy_core.service import ZapRequest

from . import platform
from .runtime import config, save_whitelist, service, settings, state
from .store import store

_ALCONNA_REFS: list[Alconna] = []


def _cmd(*args: Any, **kwargs: Any) -> Alconna:
    """持有强引用，避免 Alconna 被 GC 后 matcher 静默失效。"""
    alc = Alconna(*args, **kwargs)
    _ALCONNA_REFS.append(alc)
    return alc


zap_cmd = on_alconna(
    _cmd("zap", Args["target?", At]),
    aliases={"电", "电击", "雷"},
    use_cmd_start=True,
    priority=10,
    block=True,
)
zapkwh_cmd = on_alconna(
    _cmd("zapkwh"), aliases={"度数榜", "电费榜"}, use_cmd_start=True, priority=11, block=True
)
zaptop_cmd = on_alconna(
    _cmd("zaptop"), aliases={"被电榜"}, use_cmd_start=True, priority=11, block=True
)
zapmax_cmd = on_alconna(
    _cmd("zapmax"), aliases={"峰值榜"}, use_cmd_start=True, priority=11, block=True
)
zapking_cmd = on_alconna(
    _cmd("zapking"), aliases={"电王榜"}, use_cmd_start=True, priority=11, block=True
)
zapinfo_cmd = on_alconna(
    _cmd("zapinfo", Args["target?", At]), aliases={"电档"}, use_cmd_start=True, priority=11, block=True
)
zapclear_cmd = on_alconna(
    _cmd("zapclear", Args["target?", At]), use_cmd_start=True, priority=11, block=True
)
zapnodo_cmd = on_alconna(
    _cmd("zapnodo", Args["target?", At]), aliases={"绝缘"}, use_cmd_start=True, priority=11, block=True
)
zapon_cmd = on_alconna(_cmd("zapon"), use_cmd_start=True, priority=11, block=True)
zapoff_cmd = on_alconna(_cmd("zapoff"), use_cmd_start=True, priority=11, block=True)

_NO_SESSION = "这个适配器没有提供会话信息，暂时电不了。"


def _at_value(segment: Any) -> str:
    # At 也能表示 @角色 / @频道，这里只接受具体用户
    if str(getattr(segment, "flag", "user")) != "user":
        return ""
    for attr in ("target", "qq", "user_id", "id"):
        value = getattr(segment, attr, None)
        if value:
            return str(value)
    return ""


def _at_name(segment: Any) -> str:
    for attr in ("display", "name"):
        value = getattr(segment, attr, None)
        if value:
            return str(value).lstrip("@")
    return ""


async def _reply(text: str) -> None:
    await UniMessage.text(text).send()


async def _resolve_target(
    bot: Bot, session: platform.SceneInfo, target: Match[At]
) -> tuple[str, str]:
    if target.available:
        uid = _at_value(target.result)
        if uid:
            name = _at_name(target.result)
            if not name:
                name = await platform.member_name(bot, session, uid)
            return uid, name
    return session.user_id, session.display_user


@zap_cmd.handle()
async def _handle_zap(bot: Bot, event: Event, target: Match[At]) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return

    target_id, target_name = await _resolve_target(bot, session, target)
    if target_id == session.bot_id and target_id:
        await _reply(
            texts.render(
                texts.pick("bot", scope=session.key),
                actor=session.display_user,
                target=target_name,
            )
        )
        return

    request = ZapRequest(
        gid=session.key,
        actor=session.user_id,
        target=target_id,
        actor_name=session.display_user,
        target_name=target_name or target_id,
        self_zap=target_id == session.user_id,
        privileged=platform.is_admin(bot, session, session.user_id),
    )
    outcome = await service.zap(request)

    if outcome.ok and config.volt_show_avatar:
        avatar = await platform.fetch_avatar(
            bot, session, target_id, config.volt_avatar_timeout
        )
        if avatar:
            message = UniMessage([Text(outcome.text), Image(raw=avatar)])
        else:
            message = UniMessage.text(outcome.text)
    else:
        message = UniMessage.text(outcome.text)
    await message.send()


@zapkwh_cmd.handle()
async def _handle_kwh(bot: Bot, event: Event) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    records = store.records(session.key)
    await _reply(rank_kwh(records, settings, scope=session.key))


@zaptop_cmd.handle()
async def _handle_top(bot: Bot, event: Event) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    records = store.records(session.key)
    await _reply(rank_top(records, scope=session.key))


@zapmax_cmd.handle()
async def _handle_max(bot: Bot, event: Event) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    records = store.records(session.key)
    await _reply(rank_max(records, scope=session.key))


@zapking_cmd.handle()
async def _handle_king(bot: Bot, event: Event) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    await _reply(rank_king(store.records(session.key), scope=session.key))


@zapinfo_cmd.handle()
async def _handle_info(bot: Bot, event: Event, target: Match[At]) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    uid, name = await _resolve_target(bot, session, target)
    record = store.records(session.key).get(uid)
    if not record:
        await _reply(texts.render(texts.MISSING_TEXT, name=name or uid))
        return
    await _reply(info_text(record, settings, name=name))


@zapclear_cmd.handle()
async def _handle_clear(bot: Bot, event: Event, target: Match[At]) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    if not platform.is_admin(bot, session, session.user_id):
        await _reply("无权限使用此命令。")
        return
    uid, name = await _resolve_target(bot, session, target)
    if not await store.clear(session.key, uid):
        await _reply(f"没有查到 {name or uid} 的用电记录。")
        return
    await _reply(
        texts.render(
            texts.pick("clear", scope=session.key),
            name=name or uid,
            actor=session.display_user,
        )
    )


@zapnodo_cmd.handle()
async def _handle_nodo(bot: Bot, event: Event, target: Match[At]) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    if not platform.is_admin(bot, session, session.user_id):
        await _reply("无权限使用此命令。")
        return
    uid, name = await _resolve_target(bot, session, target)
    if uid in state.whitelist:
        state.whitelist.discard(uid)
        save_whitelist(state.whitelist)
        await _reply(f"已解除 {name or uid} 的免电保护。")
    else:
        state.whitelist.add(uid)
        save_whitelist(state.whitelist)
        await _reply(f"已将 {name or uid} 加入免电名单。")


@zapon_cmd.handle()
async def _handle_on(bot: Bot, event: Event) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    if not platform.is_admin(bot, session, session.user_id):
        await _reply("无权限使用此命令。")
        return
    state.set_group_enabled(session.key, True)
    await _reply("本群用电业务已恢复。")


@zapoff_cmd.handle()
async def _handle_off(bot: Bot, event: Event) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    if not platform.is_admin(bot, session, session.user_id):
        await _reply("无权限使用此命令。")
        return
    state.set_group_enabled(session.key, False)
    await _reply("本群用电业务已停止。")
