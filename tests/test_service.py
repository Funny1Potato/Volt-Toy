from __future__ import annotations

import asyncio

from volt_toy_core.service import ZapRequest, ZapService
from volt_toy_core.settings import Settings
from volt_toy_core.state import RuntimeState
from volt_toy_core.storage import JsonStore


def build(tmp_path, **overrides):
    store = JsonStore(tmp_path / "zap.json")
    asyncio.run(store.load())
    settings = Settings(**overrides)
    state = RuntimeState()
    return ZapService(store, state, settings), store, state


def request(target: str = "u", actor: str = "a", **kwargs) -> ZapRequest:
    payload = {
        "gid": "g",
        "actor": actor,
        "target": target,
        "actor_name": "阿雷",
        "target_name": "小满",
    }
    payload.update(kwargs)
    return ZapRequest(**payload)


def test_success_text_contains_totals(tmp_path) -> None:
    service, store, _ = build(tmp_path)

    async def scenario() -> None:
        outcome = await service.zap(request())
        assert outcome.ok
        assert "小满" in outcome.text
        assert "累计" in outcome.text
        record = store.record("g", "u")
        assert record["num"] == 1
        assert record["kwh"] > 0

    asyncio.run(scenario())


def test_over_cap_marks_failure(tmp_path) -> None:
    service, store, _ = build(tmp_path, receive_cap=1)

    async def scenario() -> None:
        first = await service.zap(request())
        second = await service.zap(request())
        assert first.ok
        assert not second.ok
        assert second.reason == "over_cap"
        assert "失败" in second.text
        record = store.record("g", "u")
        assert record["num"] == 2
        assert record["fail"] == 1
        assert record["kwh"] == first.kwh

    asyncio.run(scenario())


def test_whitelist_blocks_but_privileged_passes(tmp_path) -> None:
    service, _, state = build(tmp_path)
    state.whitelist.add("u")

    async def scenario() -> None:
        blocked = await service.zap(request())
        assert not blocked.ok
        assert blocked.reason == "immune"
        allowed = await service.zap(request(privileged=True))
        assert allowed.ok

    asyncio.run(scenario())


def test_disabled_group(tmp_path) -> None:
    service, _, state = build(tmp_path)
    state.set_group_enabled("g", False)

    async def scenario() -> None:
        outcome = await service.zap(request())
        assert outcome.reason == "disabled"

    asyncio.run(scenario())


def test_overload_trips_and_blocks(tmp_path) -> None:
    service, _, _ = build(tmp_path, overload_threshold=2, overload_ban=300)

    async def scenario() -> None:
        await service.zap(request())
        await service.zap(request())
        blocked = await service.zap(request())
        assert not blocked.ok
        assert blocked.reason == "overload"

    asyncio.run(scenario())


def test_cooldown_blocks_second_hit(tmp_path) -> None:
    service, _, _ = build(tmp_path, cooldown=10)

    async def scenario() -> None:
        await service.zap(request())
        blocked = await service.zap(request())
        assert blocked.reason == "cooldown"

    asyncio.run(scenario())


def test_quota_limits_actions(tmp_path) -> None:
    service, _, _ = build(tmp_path, daily_quota=1)

    async def scenario() -> None:
        await service.zap(request(target="u"))
        blocked = await service.zap(request(target="v"))
        assert blocked.reason == "quota"

    asyncio.run(scenario())
