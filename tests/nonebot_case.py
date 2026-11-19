"""在 pytest 的独立子进程与临时工作目录中运行真实 NoneBot/OneBot 事件链。"""

# 必须先准备源码路径并加载插件，才能导入其运行时。
# ruff: noqa: E402
from __future__ import annotations

import asyncio
import base64
import io
import os
import sys
from pathlib import Path
from unittest.mock import AsyncMock, Mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import httpx
import nonebot
from nonebot.adapters.onebot.v11 import Adapter, Bot, GroupMessageEvent, Message, MessageSegment
from PIL import Image

nonebot.init(
    driver="~fastapi",
    localstore_use_cwd=True,
    localstore_cache_dir=os.environ.get("VOLT_TEST_CACHE_DIR"),
    volt_receive_cap=0,
    volt_overload_threshold=1000,
    log_level="ERROR",
)
nonebot.get_driver().register_adapter(Adapter)
plugin = nonebot.load_plugin("nonebot_plugin_volt_toy")
assert plugin is not None
assert Path(plugin.module.__file__).resolve().parent == ROOT / "nonebot_plugin_volt_toy"

from nonebot.message import handle_event

from nonebot_plugin_volt_toy import commands, platform, runtime, store
from volt_toy_core import service
from volt_toy_core.avatars import AvatarCache
from volt_toy_core.model import Roll

SELF, USER, TARGET, GROUP = "30000", "10001", "30004", "617770183"
scene = platform.SceneInfo(
    key=f"onebot11:{GROUP}",
    slug="onebot11",
    scene_path=GROUP,
    chat_id=GROUP,
    user_id=USER,
    user_name="测试员",
    bot_id=SELF,
)
platform.resolve = AsyncMock(return_value=scene)
platform.member_name = AsyncMock(return_value="目标")
platform._avatar_url = AsyncMock(return_value="https://example.invalid/avatar.png")
settled = {"tier": "家用"}
service.settle = lambda **kwargs: Roll(220, 0.45, 0.1, settled["tier"], False, 0)
buffer = io.BytesIO()
Image.new("RGB", (32, 24), "orange").save(buffer, format="PNG")
AVATAR = buffer.getvalue()
network = {"calls": 0, "mode": "ok"}


def respond(request):
    network["calls"] += 1
    if network["mode"] == "fail":
        raise httpx.ConnectError("offline", request=request)
    if network["mode"] == "invalid":
        return httpx.Response(200, content=b"<html>error</html>")
    if network["mode"] == "large":
        return httpx.Response(200, content=b"x" * (platform.MAX_AVATAR_BYTES + 1))
    return httpx.Response(200, content=AVATAR)


client_class = httpx.AsyncClient
platform.httpx.AsyncClient = lambda **kwargs: client_class(
    transport=httpx.MockTransport(respond), **kwargs
)
sent = []
send_control = {"fail_image": False}


async def record_message(message):
    if send_control["fail_image"] and any(seg.type == "image" for seg in message):
        raise RuntimeError("image send failed")
    sent.append(message)
    return {"message_id": len(sent)}


async def recording_send(self, event, message, **kwargs):
    return await record_message(message)


async def recording_api(self, **kwargs):
    return await record_message(kwargs["message"])


adapter = Adapter(nonebot.get_driver())
bot = Bot(adapter, SELF)
bot.send = recording_send.__get__(bot)
bot.send_msg = recording_api.__get__(bot)
sequence = 2000


async def drive(command="/电", *, with_at=True):
    global sequence
    sequence += 1
    message = Message(command)
    if with_at:
        message += MessageSegment.text(" ") + MessageSegment.at(TARGET)
    ev = GroupMessageEvent(
        time=1_800_000_000,
        self_id=int(SELF),
        post_type="message",
        sub_type="normal",
        user_id=int(USER),
        message_type="group",
        message_id=sequence,
        message=message,
        original_message=message,
        raw_message=str(message),
        font=0,
        sender={"user_id": int(USER), "nickname": "测试员"},
        group_id=int(GROUP),
        to_me=False,
        reply=None,
    )
    sent.clear()
    await handle_event(bot, ev)
    assert len(sent) == 1, (command, sent)
    return sent[0]


def image_bytes(message):
    parts = [segment for segment in message if segment.type == "image"]
    assert len(parts) == 1
    encoded = parts[0].data["file"]
    assert encoded.startswith("base64://")
    return base64.b64decode(encoded.removeprefix("base64://"))


async def main():
    original_cache_dir = store.get_plugin_cache_dir
    store.get_plugin_cache_dir = Mock(side_effect=PermissionError("cache directory denied"))
    store.resolve()
    assert store.AVATAR_CACHE_DIR is None
    store.get_plugin_cache_dir = original_cache_dir
    await runtime._prepare()
    cache_root = Path(os.environ.get("VOLT_TEST_CACHE_DIR", Path.cwd() / "cache"))
    expected = cache_root / "nonebot_plugin_volt_toy" / "avatars"
    assert expected == store.AVATAR_CACHE_DIR
    assert platform._avatar_cache._disk.directory == expected
    assert store.ACCOUNT_FILE.is_relative_to(Path.cwd())

    # 真实五档渲染；同一头像只下载一次。每条事件都有不同的 message_id。
    for tier in ("静电", "家用", "工业", "高压", "雷击"):
        settled["tier"] = tier
        message = await drive()
        assert [seg.type for seg in message] == ["text", "image", "text"]
        with Image.open(io.BytesIO(image_bytes(message))) as image:
            assert image.format == ("GIF" if tier == "雷击" else "PNG")
        assert "累计" in message.extract_plain_text()
    assert network["calls"] == 1
    files = list(expected.glob("*.avatar"))
    assert len(files) == 1 and files[0].read_bytes()[8:] == AVATAR

    # 重新创建缓存对象，验证 localstore 落盘后的原图可以复用。
    platform.configure_avatar_cache(expected)
    runtime.config.volt_avatar_effect = False
    assert image_bytes(await drive()) == AVATAR
    assert network["calls"] == 1
    runtime.config.volt_avatar_effect = True
    runtime.config.volt_avatar_effect_gif = False
    with Image.open(io.BytesIO(image_bytes(await drive()))) as image:
        assert image.format == "PNG"

    # 渲染异常回原图；图片消息发送异常回文本，账本仍然只结算一次。
    commands.effects.render = Mock(side_effect=RuntimeError("render failed"))
    assert image_bytes(await drive()) == AVATAR
    send_control["fail_image"] = True
    message = await drive()
    assert all(seg.type == "text" for seg in message)
    assert "累计" in message.extract_plain_text()
    send_control["fail_image"] = False

    # 缓存关闭时每次下载，且不会误用已有的磁盘缓存。
    runtime.config.volt_avatar_cache = False
    runtime.config.volt_avatar_effect = False
    before = network["calls"]
    for _ in range(2):
        assert image_bytes(await drive()) == AVATAR
    assert network["calls"] == before + 2
    runtime.config.volt_avatar_cache = True

    # 热缓存刷新失败仍可带图；关闭头像时完全不触发下载。
    now = [platform._avatar_cache._clock() + 3600]
    platform._avatar_cache._clock = lambda: now[0]
    network["mode"] = "fail"
    assert image_bytes(await drive()) == AVATAR
    runtime.config.volt_show_avatar = False
    before = network["calls"]
    assert all(seg.type == "text" for seg in await drive())
    assert network["calls"] == before
    runtime.config.volt_show_avatar = True

    # 首次失败、错误页面、超过大小上限都只发文字，不污染缓存。
    for mode in ("fail", "invalid", "large"):
        platform._avatar_cache = AvatarCache(directory=expected / mode)
        network["mode"] = mode
        message = await drive()
        assert all(seg.type == "text" for seg in message)
        assert "累计" in message.extract_plain_text()
        assert not list((expected / mode).glob("*.avatar"))

    count = runtime.get_store().record(scene.key, TARGET)["num"]
    assert count == 16, count
    for command, heading in (
        ("/被电榜", "被电榜"),
        ("/度数榜", "度数榜"),
        ("/峰值榜", "峰值榜"),
        ("/电王榜", "电王榜"),
    ):
        message = await drive(command, with_at=False)
        assert heading in message.extract_plain_text()
    assert runtime.get_store().record(scene.key, TARGET)["num"] == count
    print("nonebot adapter regression passed")


if __name__ == "__main__":
    asyncio.run(main())
