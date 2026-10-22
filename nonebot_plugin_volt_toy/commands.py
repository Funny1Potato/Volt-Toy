"""指令层：Alconna 解析参数，平台层解析会话，业务在内核 ZapService。

注意：Alconna 对象必须被强引用持有。alconna 的规则只持弱引用，若写成
`on_alconna(Alconna(...))`，命令对象可能被 GC 回收，matcher 会静默失效。
"""

from __future__ import annotations

from typing import Any

from nonebot import logger
from nonebot.adapters import Bot, Event
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    At,
    Match,
    UniMessage,
    on_alconna,
)

from volt_toy_core import texts
from volt_toy_core.fmt import kwh_text
from volt_toy_core.rankings import kings, top
from volt_toy_core.service import ZapRequest

from . import platform
from .runtime import config, save_whitelist, service, settings, state
from .store import store

_ALCONNA_REFS: list[Alconna] = []


def _cmd(*args: Any, **kwargs: Any) -> Alconna:
    alc = Alconna(*args, **kwargs)
    _ALCONNA_REFS.append(alc)
    return alc


zap_cmd = on_alconna(
    _cmd("zap", Args["target?", At]["reason?", str]),
    aliases={"电", "电击", "雷"},
    priority=10,
    block=True,
)
zapkwh_cmd = on_alconna(_cmd("zapkwh"), aliases={"度数榜", "电费榜"}, priority=11, block=True)
zaptop_cmd = on_alconna(_cmd("zaptop"), aliases={"被电榜"}, priority=11, block=True)
zapmax_cmd = on_alconna(_cmd("zapmax"), aliases={"峰值榜"}, priority=11, block=True)
zapking_cmd = on_alconna(_cmd("zapking"), aliases={"电王榜"}, priority=11, block=True)
zapinfo_cmd = on_alconna(
    _cmd("zapinfo", Args["target?", At]), aliases={"电档"}, priority=11, block=True
)
zapclear_cmd = on_alconna(_cmd("zapclear", Args["target?", At]), priority=11, block=True)
zapnodo_cmd = on_alconna(_cmd("zapnodo", Args["target?", At]), aliases={"绝缘"}, priority=11, block=True)
zapon_cmd = on_alconna(_cmd("zapon"), priority=11, block=True)
zapoff_cmd = on_alconna(_cmd("zapoff"), priority=11, block=True)

_NO_SESSION = "这个适配器没有提供会话信息，暂时电不了。"


def _at_value(segment: Any) -> str:
    for attr in ("target", "qq", "user_id", "id"):
        value = getattr(segment, attr, None)
        if value:
            return str(value)
    data = getattr(segment, "data", None)
    if isinstance(data, dict):
        for key in ("qq", "user_id", "id"):
            if data.get(key):
                return str(data[key])
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
async def _handle_zap(bot: Bot, event: Event, target: Match[At], reason: Match[str]) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return

    target_id, target_name = await _resolve_target(bot, session, target)
    if target_id == session.bot_id and target_id:
        await _reply(
            texts.render(texts.pick("bot", scope=session.key), actor=session.display_user, target=target_name)
        )
        return

    request = ZapRequest(
        gid=session.key,
        actor=session.user_id,
        target=target_id,
        actor_name=session.display_user,
        target_name=target_name or target_id,
        reason=(reason.result if reason.available else "")[:60],
        self_zap=target_id == session.user_id,
        privileged=platform.is_admin(bot, session, session.user_id),
    )
    outcome = await service.zap(request)

    message = UniMessage.text(outcome.text)
    if outcome.ok and config.volt_show_avatar:
        avatar = await platform.fetch_avatar(session, target_id, config.volt_avatar_timeout)
        if avatar:
            try:
                message = message + UniMessage.image(raw=avatar)
            except Exception as error:
                logger.warning(f"volt-toy 头像发送失败: {error}")
    await message.send()


@zapkwh_cmd.handle()
async def _handle_kwh(bot: Bot, event: Event) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    records = store.records(session.key)
    items = top(records, "kwh", 5)
    if not items:
        await _reply(texts.pick("empty", scope=session.key))
        return
    lines = [texts.render(texts.RANK_TITLES["kwh"], limit=5)]
    for index, (uid, name, value) in enumerate(items, 1):
        lines.append(f"{index}. {name or uid} {kwh_text(value)} 度 · 约 {settings.fee(value):.2f} 元")
    await _reply("\n".join(lines))


@zaptop_cmd.handle()
async def _handle_top(bot: Bot, event: Event) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    records = store.records(session.key)
    items = top(records, "num", 5)
    if not items:
        await _reply(texts.pick("empty", scope=session.key))
        return
    lines = [texts.render(texts.RANK_TITLES["top"], limit=5)]
    for index, (uid, name, value) in enumerate(items, 1):
        record = records.get(uid, {})
        lines.append(f"{index}. {name or uid} {int(value)} 次（{int(record.get('fail', 0))} 失败）")
    await _reply("\n".join(lines))


@zapmax_cmd.handle()
async def _handle_max(bot: Bot, event: Event) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    records = store.records(session.key)
    items = top(records, "peak", 5)
    if not items:
        await _reply(texts.pick("empty", scope=session.key))
        return
    lines = [texts.render(texts.RANK_TITLES["max"], limit=5)]
    for index, (uid, name, value) in enumerate(items, 1):
        record = records.get(uid, {})
        lines.append(
            f"{index}. {name or uid} {kwh_text(value)} 度"
            f"（{int(record.get('peak_volt', 0))}V / {float(record.get('peak_ah', 0)):.2f}Ah）"
        )
    await _reply("\n".join(lines))


@zapking_cmd.handle()
async def _handle_king(bot: Bot, event: Event) -> None:
    session = await platform.resolve(bot, event)
    if session is None:
        await _reply(_NO_SESSION)
        return
    items = kings(store.records(session.key), 5)
    if not items:
        await _reply(texts.pick("empty", scope=session.key))
        return
    lines = [texts.render(texts.RANK_TITLES["king"], limit=5)]
    for index, (uid, name, value) in enumerate(items, 1):
        lines.append(f"{index}. {name or uid} 电王值 {value}")
    await _reply("\n".join(lines))


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
    total = float(record.get("kwh", 0.0))
    await _reply(
        texts.render(
            texts.INFO_TEXT,
            name=record.get("name") or name or uid,
            n=int(record.get("num", 0)),
            fail=int(record.get("fail", 0)),
            day_n=int(record.get("day_num", 0)),
            day_fail=int(record.get("day_fail", 0)),
            total=kwh_text(total),
            fee=f"{settings.fee(total):.2f}",
        )
    )


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
