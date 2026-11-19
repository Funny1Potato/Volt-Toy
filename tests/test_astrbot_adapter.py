"""AstrBot 适配层契约测试（SDK 边界桩，不冒充真实 AstrBot 运行时测试）。"""

from __future__ import annotations

import asyncio
import importlib.util
import io
import logging
import sys
from dataclasses import dataclass
from pathlib import Path
from types import ModuleType, SimpleNamespace
from unittest.mock import Mock

import pytest
from PIL import Image as PILImage

from volt_toy_core import service
from volt_toy_core.model import Roll


@dataclass
class Plain:
    text: str


@dataclass
class Image:
    raw: bytes

    @classmethod
    def fromBytes(cls, raw):
        return cls(raw)


@dataclass
class At:
    qq: str
    name: str = "目标"


class Reply:
    pass


@pytest.fixture
def adapter(monkeypatch, tmp_path):
    def module(name, **attributes):
        value = ModuleType(name)
        value.__dict__.update(attributes)
        monkeypatch.setitem(sys.modules, name, value)

    class Star:
        def __init__(self, context):
            self.context = context

    module("astrbot")
    module("astrbot.api", AstrBotConfig=dict, logger=logging.getLogger("astrbot-test"))
    module(
        "astrbot.api.event",
        AstrMessageEvent=object,
        filter=SimpleNamespace(command=lambda *a, **kw: lambda function: function),
    )
    module("astrbot.api.message_components", At=At, Plain=Plain, Image=Image, Reply=Reply)
    module("astrbot.api.star", Context=object, Star=Star)
    module("astrbot.core")
    module("astrbot.core.utils")
    module("astrbot.core.utils.astrbot_path", get_astrbot_data_path=lambda: str(tmp_path))
    path = Path(__file__).resolve().parents[1] / "main.py"
    spec = importlib.util.spec_from_file_location("volt_toy_astrbot_test", path)
    loaded = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loaded)
    buffer = io.BytesIO()
    PILImage.new("RGB", (32, 32), "orange").save(buffer, format="PNG")
    avatar = buffer.getvalue()
    download = Mock(return_value=avatar)
    render = Mock(return_value=b"effect-image")
    monkeypatch.setattr(loaded, "_download_avatar", download)
    monkeypatch.setattr(loaded, "_render_effect", render)
    monkeypatch.setattr(service, "settle", lambda **kw: Roll(900, 1.11, 1.0, "雷击", False, 0))
    return loaded, avatar, download, render


def event(platform="aiocqhttp"):
    return SimpleNamespace(
        get_platform_name=lambda: platform,
        get_sender_id=lambda: "10001",
        get_sender_name=lambda: "测试员",
        get_self_id=lambda: "30000",
        unified_msg_origin="qq:GroupMessage:617770183",
        get_messages=lambda: [At("30004")],
        is_admin=lambda: False,
        plain_result=lambda text: ("text", text),
        chain_result=lambda chain: ("chain", chain),
    )


async def zap(plugin, ev=None):
    return [result async for result in plugin.zap(ev or event())]


@pytest.mark.parametrize("tier", ["家用", "雷击"])
@pytest.mark.parametrize("effect,gif", [(False, False), (False, True), (True, False), (True, True)])
def test_effect_and_gif_switches(adapter, monkeypatch, tier, effect, gif):
    loaded, avatar, download, render = adapter
    monkeypatch.setattr(service, "settle", lambda **kw: Roll(220, 0.45, 0.1, tier, False, 0))
    plugin = loaded.VoltToy(None, {"volt_avatar_effect": effect, "volt_avatar_effect_gif": gif})
    results = asyncio.run(zap(plugin))
    assert len(results) == 1
    kind, chain = results[0]
    assert kind == "chain"
    assert [type(part) for part in chain] == [Plain, Image, Plain]
    assert "累计" not in chain[0].text
    assert "累计" in chain[2].text
    assert chain[1].raw == (b"effect-image" if effect else avatar)
    assert download.call_count == 1
    if effect:
        render.assert_called_once_with(avatar, tier, 220, 0.1, tier == "雷击" and gif)
    else:
        render.assert_not_called()
    assert plugin._store.record(event().unified_msg_origin, "30004")["num"] == 1


@pytest.mark.parametrize("failure", ["download", "invalid", "render"])
def test_image_failure_preserves_settlement(adapter, failure):
    loaded, avatar, download, render = adapter
    if failure == "download":
        download.side_effect = TimeoutError()
    elif failure == "invalid":
        download.return_value = b"<html>bad gateway</html>"
    else:
        render.side_effect = RuntimeError("broken renderer")
    plugin = loaded.VoltToy(None)
    kind, body = asyncio.run(zap(plugin))[0]
    if failure == "render":
        assert kind == "chain"
        assert body[1].raw == avatar
    else:
        assert kind == "text"
        assert "累计" in body
        render.assert_not_called()
    assert plugin._store.record(event().unified_msg_origin, "30004")["num"] == 1


@pytest.mark.parametrize("disabled", ["volt_show_avatar", "unsupported-platform"])
def test_hidden_or_unsupported_avatar_does_not_download(adapter, disabled):
    loaded, _, download, _ = adapter
    config = {"volt_show_avatar": False} if disabled == "volt_show_avatar" else {}
    plugin = loaded.VoltToy(None, config)
    ev = event("telegram") if disabled == "unsupported-platform" else event()
    assert asyncio.run(zap(plugin, ev))[0][0] == "text"
    download.assert_not_called()


def test_cache_uses_astrbot_directory_and_survives_restart(adapter, tmp_path):
    loaded, avatar, download, render = adapter
    config = {"volt_avatar_effect": False}

    async def scenario():
        first = loaded.VoltToy(None, config)
        assert (await zap(first))[0][1][1].raw == avatar
        base = tmp_path / "plugin_data" / loaded.PLUGIN_NAME
        assert first._store.path == base / "zap.json"
        assert len(list((base / "cache" / "avatars").glob("*.avatar"))) == 1
        second = loaded.VoltToy(None, config)
        assert (await zap(second))[0][1][1].raw == avatar
        assert download.call_count == 1
        render.assert_not_called()

    asyncio.run(scenario())


def test_legacy_path_fallback_does_not_write_cache_into_source(adapter, monkeypatch):
    loaded, avatar, _, _ = adapter
    monkeypatch.setattr(loaded, "_data_dir", lambda name: loaded._ROOT / "data")
    plugin = loaded.VoltToy(None, {"volt_avatar_effect": False})
    assert plugin._avatar_cache._disk is None
    outcome = SimpleNamespace(roll=Roll(220, 0.45, 0.1, "家用", False, 0))
    assert asyncio.run(plugin._avatar_image(event(), "30004", outcome)) == avatar


def test_cache_disable_and_no_effect_caching(adapter):
    loaded, _, download, render = adapter

    async def scenario():
        plugin = loaded.VoltToy(None, {"volt_avatar_cache": False})
        await zap(plugin)
        await zap(plugin)
        assert download.call_count == 2
        assert render.call_count == 2
        assert not plugin._avatar_cache._disk.directory.exists()
        cached = loaded.VoltToy(None)
        await zap(cached)
        await zap(cached)
        assert download.call_count == 3
        assert render.call_count == 4  # 每次按当次结算重新渲染，只有原图缓存

    asyncio.run(scenario())
