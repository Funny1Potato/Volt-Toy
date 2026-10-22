"""指令层：Alconna 负责解析，Uninfo 负责跨协议会话。

所有业务判断在内核 ZapService 里，这里只做「取参数 → 调服务 → 发消息」。
"""

from __future__ import annotations

from typing import Any

from nonebot import logger
from nonebot_plugin_alconna import (
    Alconna,
    Args,
    At,
    Match,
    UniMessage,
    on_alconna,
)
from nonebot_plugin_uninfo import Uninfo

from volt_toy_core import texts
from volt_toy_core.fmt import kwh_text
from volt_toy_core.rankings import kings, top
from volt_toy_core.service import ZapRequest

from . import platform
from .runtime import config, save_whitelist, service, settings, state
from .store import store

zap_cmd = on_alconna(
    Alconna("zap", Args["target?", At]["reason?", str]),
    aliases={"电", "电击", "雷"},
)
zapkwh_cmd = on_alconna(Alconna("zapkwh"), aliases={"度数榜", "电费榜"})
zaptop_cmd = on_alconna(Alconna("zaptop"), aliases={"被电榜"})
zapmax_cmd = on_alconna(Alconna("zapmax"), aliases={"峰值榜"})
zapking_cmd = on_alconna(Alconna("zapking"), aliases={"电王榜"})
zapinfo_cmd = on_alconna(Alconna("zapinfo", Args["target?", At]), aliases={"电档"})
zapclear_cmd = on_alconna(Alconna("zapclear", Args["target?", At]))
zapnodo_cmd = on_alconna(Alconna("zapnodo", Args["target?", At]), aliases={"绝缘"})
zapon_cmd = on_alconna(Alconna("zapon"))
zapoff_cmd = on_alconna(Alconna("zapoff"))


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
            return str(value)
    return ""


def _resolve_target(session: Any, match: Match[At]) -> tuple[str, str]:
    if match.available:
        uid = _at_value(match.result)
        if uid:
            return uid, _at_name(match.result)
    return platform.user_id(session), platform.sender_name(session)


async def _reply(text: str) -> None:
    await UniMessage.text(text).send()


@zap_cmd.handle()
async def _handle_zap(session: Uninfo, target: Match[At], reason: Match[str]) -> None:
    gid = platform.scope_key(session)
    actor = platform.user_id(session)
    actor_name = platform.sender_name(session)
    target_id, target_name = _resolve_target(session, target)

    if target_id == platform.self_id(session) and target_id:
        await _reply(texts.render(texts.pick("bot", scope=gid), actor=actor_name, target=target_name))
        return

    request = ZapRequest(
        gid=gid,
        actor=actor,
        target=target_id,
        actor_name=actor_name,
        target_name=target_name or target_id,
        reason=(reason.result if reason.available else "")[:60],
        self_zap=target_id == actor,
        privileged=platform.is_admin(session),
    )
    outcome = await service.zap(request)

    message = UniMessage.text(outcome.text)
    if outcome.ok and config.volt_show_avatar:
        avatar = await platform.fetch_avatar(session, target_id, config.volt_avatar_timeout)
        if avatar:
            try:
                message = message + UniMessage.image(raw=avatar)
            except Exception as error:  # 头像失败不影响文本
                logger.warning(f"volt-toy 头像发送失败: {error}")
    await message.send()


@zapkwh_cmd.handle()
async def _handle_kwh(session: Uninfo) -> None:
    records = store.records(platform.scope_key(session))
    items = top(records, "kwh", 5)
    if not items:
        await _reply(texts.pick("empty", scope=platform.scope_key(session)))
        return
    lines = [texts.render(texts.RANK_TITLES["kwh"], limit=5)]
    for index, (uid, name, value) in enumerate(items, 1):
        lines.append(f"{index}. {name or uid} {kwh_text(value)} 度 · 约 {settings.fee(value):.2f} 元")
    await _reply("\n".join(lines))


@zaptop_cmd.handle()
async def _handle_top(session: Uninfo) -> None:
    gid = platform.scope_key(session)
    records = store.records(gid)
    items = top(records, "num", 5)
    if not items:
        await _reply(texts.pick("empty", scope=gid))
        return
    lines = [texts.render(texts.RANK_TITLES["top"], limit=5)]
    for index, (uid, name, value) in enumerate(items, 1):
        record = records.get(uid, {})
        lines.append(f"{index}. {name or uid} {int(value)} 次（{int(record.get('fail', 0))} 失败）")
    await _reply("\n".join(lines))


@zapmax_cmd.handle()
async def _handle_max(session: Uninfo) -> None:
    gid = platform.scope_key(session)
    records = store.records(gid)
    items = top(records, "peak", 5)
    if not items:
        await _reply(texts.pick("empty", scope=gid))
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
async def _handle_king(session: Uninfo) -> None:
    gid = platform.scope_key(session)
    items = kings(store.records(gid), 5)
    if not items:
        await _reply(texts.pick("empty", scope=gid))
        return
    lines = [texts.render(texts.RANK_TITLES["king"], limit=5)]
    for index, (uid, name, value) in enumerate(items, 1):
        lines.append(f"{index}. {name or uid} 电王值 {value}")
    await _reply("\n".join(lines))


@zapinfo_cmd.handle()
async def _handle_info(session: Uninfo, target: Match[At]) -> None:
    gid = platform.scope_key(session)
    uid, name = _resolve_target(session, target)
    record = store.records(gid).get(uid)
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
async def _handle_clear(session: Uninfo, target: Match[At]) -> None:
    if not platform.is_admin(session):
        await _reply("无权限使用此命令。")
        return
    gid = platform.scope_key(session)
    uid, name = _resolve_target(session, target)
    cleared = await store.clear(gid, uid)
    if not cleared:
        await _reply(f"没有查到 {name or uid} 的用电记录。")
        return
    await _reply(
        texts.render(
            texts.pick("clear", scope=gid),
            name=name or uid,
            actor=platform.sender_name(session),
        )
    )


@zapnodo_cmd.handle()
async def _handle_nodo(session: Uninfo, target: Match[At]) -> None:
    if not platform.is_admin(session):
        await _reply("无权限使用此命令。")
        return
    uid, name = _resolve_target(session, target)
    if uid in state.whitelist:
        state.whitelist.discard(uid)
        save_whitelist(state.whitelist)
        await _reply(f"已解除 {name or uid} 的免电保护。")
    else:
        state.whitelist.add(uid)
        save_whitelist(state.whitelist)
        await _reply(f"已将 {name or uid} 加入免电名单。")


@zapon_cmd.handle()
async def _handle_on(session: Uninfo) -> None:
    if not platform.is_admin(session):
        await _reply("无权限使用此命令。")
        return
    state.set_group_enabled(platform.scope_key(session), True)
    await _reply("本群用电业务已恢复。")


@zapoff_cmd.handle()
async def _handle_off(session: Uninfo) -> None:
    if not platform.is_admin(session):
        await _reply("无权限使用此命令。")
        return
    state.set_group_enabled(platform.scope_key(session), False)
    await _reply("本群用电业务已停止。")
