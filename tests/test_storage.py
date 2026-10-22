from __future__ import annotations

import asyncio
import json

from volt_toy_core.model import Roll
from volt_toy_core.storage import JsonStore, JsonlLog, read_json_list, write_json_list


def roll(kwh: float = 0.10) -> Roll:
    return Roll(volt=220, ah=0.45, kwh=kwh, tier="家用", crit=False, combo=0)


def test_persist_and_reload(tmp_path) -> None:
    path = tmp_path / "zap.json"

    async def scenario() -> None:
        store = JsonStore(path)
        await store.load()
        await store.apply("g", "u", "a", roll(), cap=25, today="2026-10-22")
        fresh = JsonStore(path)
        await fresh.load()
        record = fresh.record("g", "u")
        assert record["num"] == 1
        assert record["kwh"] == 0.10
        assert fresh.record("g", "missing")["num"] == 0

    asyncio.run(scenario())


def test_concurrent_zaps_are_serialized(tmp_path) -> None:
    path = tmp_path / "zap.json"

    async def scenario() -> None:
        store = JsonStore(path)
        await store.load()
        await asyncio.gather(
            *(
                store.apply("g", "u", f"a{i}", roll(), cap=25, today="2026-10-22")
                for i in range(20)
            )
        )
        record = store.record("g", "u")
        assert record["num"] == 20
        assert record["kwh"] == 2.00

    asyncio.run(scenario())


def test_corrupt_file_is_preserved(tmp_path) -> None:
    path = tmp_path / "zap.json"
    path.write_text("{ not json", encoding="utf-8")

    async def scenario() -> None:
        store = JsonStore(path)
        await store.load()
        assert store.records("g") == {}
        assert any(p.name.startswith("zap.json.corrupt-") for p in tmp_path.iterdir())

    asyncio.run(scenario())


def test_falls_back_to_backup(tmp_path) -> None:
    path = tmp_path / "zap.json"
    backup = tmp_path / "zap.json.bak"
    path.write_text("{ broken", encoding="utf-8")
    backup.write_text(
        json.dumps({"v": 1, "groups": {"g": {"u": {"num": 3}}}}),
        encoding="utf-8",
    )

    async def scenario() -> None:
        store = JsonStore(path)
        await store.load()
        assert store.record("g", "u")["num"] == 3

    asyncio.run(scenario())


def test_clear_removes_record(tmp_path) -> None:
    path = tmp_path / "zap.json"

    async def scenario() -> None:
        store = JsonStore(path)
        await store.load()
        await store.apply("g", "u", "a", roll(), cap=25, today="2026-10-22")
        assert await store.clear("g", "u") is True
        assert await store.clear("g", "u") is False
        assert store.records("g") == {}

    asyncio.run(scenario())


def test_jsonl_log_appends(tmp_path) -> None:
    log = JsonlLog(tmp_path / "zap_log.jsonl")

    async def scenario() -> None:
        await log.append({"a": 1})
        await log.append({"a": 2})
        assert [item["a"] for item in await log.tail(5)] == [1, 2]

    asyncio.run(scenario())


def test_whitelist_roundtrip(tmp_path) -> None:
    path = tmp_path / "zap_whitelist.json"
    write_json_list(path, ["10001", "10002"])
    assert read_json_list(path) == ["10001", "10002"]
    assert read_json_list(tmp_path / "missing.json") == []
