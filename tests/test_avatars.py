from __future__ import annotations

import asyncio
import io
import os
import struct
from unittest.mock import AsyncMock, Mock

import pytest
from PIL import Image

from volt_toy_core.avatars import MAX_AVATAR_BYTES, AvatarCache


@pytest.fixture
def avatar() -> bytes:
    buffer = io.BytesIO()
    Image.new("RGB", (32, 24), "salmon").save(buffer, format="PNG")
    return buffer.getvalue()


@pytest.fixture
def clock():
    now = [1_800_000_000.0]
    return now, lambda: now[0]


def test_fresh_hit_and_refresh(avatar, clock):
    now, tick = clock
    cache = AvatarCache(fresh_ttl=10, max_age=100, clock=tick)
    loader = AsyncMock(return_value=avatar)

    async def scenario():
        assert await cache.get("u", loader) == avatar
        now[0] += 9
        assert await cache.get("u", loader) == avatar
        assert loader.await_count == 1
        now[0] += 1
        assert await cache.get("u", loader) == avatar
        assert loader.await_count == 2

    asyncio.run(scenario())


def test_failure_uses_stale_without_extending_lifetime(avatar, clock):
    now, tick = clock
    cache = AvatarCache(fresh_ttl=10, max_age=100, retry_delay=30, clock=tick)
    loader = AsyncMock(return_value=avatar)

    async def scenario():
        assert await cache.get("u", loader) == avatar
        loader.side_effect = TimeoutError("offline")
        now[0] += 10
        assert await cache.get("u", loader) == avatar
        assert loader.await_count == 2
        now[0] += 29
        assert await cache.get("u", loader) == avatar
        assert loader.await_count == 2
        now[0] += 60  # 原始下载时间 + 99 秒
        assert await cache.get("u", loader) == avatar
        now[0] += 1
        assert await cache.get("u", loader) is None
        assert loader.await_count == 3  # 退避期间也不能越过旧图寿命

    asyncio.run(scenario())


def test_first_failure_backoff_and_retry(avatar, clock):
    now, tick = clock
    cache = AvatarCache(clock=tick)
    loader = AsyncMock(return_value=None)

    async def scenario():
        assert await cache.get("u", loader) is None
        loader.return_value = avatar
        assert await cache.get("u", loader) is None
        assert loader.await_count == 1
        now[0] += 30
        assert await cache.get("u", loader) == avatar
        assert loader.await_count == 2

    asyncio.run(scenario())


def test_concurrent_requests_share_download_and_survive_waiter_cancel(avatar):
    async def scenario():
        cache = AvatarCache()
        started, release = asyncio.Event(), asyncio.Event()

        async def download():
            started.set()
            await release.wait()
            return avatar

        loader = AsyncMock(side_effect=download)
        first = asyncio.create_task(cache.get("u", loader))
        await started.wait()
        others = [asyncio.create_task(cache.get("u", loader)) for _ in range(12)]
        first.cancel()
        with pytest.raises(asyncio.CancelledError):
            await first
        release.set()
        assert await asyncio.gather(*others) == [avatar] * 12
        assert loader.await_count == 1
        assert not cache._inflight

    asyncio.run(scenario())


@pytest.mark.parametrize("invalid", [b"", b"<html>unavailable</html>", b"\x89PNG\r\n\x1a\n", None])
def test_invalid_images_do_not_replace_good_cache(avatar, clock, invalid):
    now, tick = clock
    cache = AvatarCache(fresh_ttl=1, clock=tick)
    loader = AsyncMock(return_value=avatar)

    async def scenario():
        assert await cache.get("u", loader) == avatar
        now[0] += 1
        loader.return_value = invalid
        assert await cache.get("u", loader) == avatar
        assert cache.size_bytes == len(avatar)

    asyncio.run(scenario())


def test_oversized_download_rejected():
    cache = AvatarCache()
    loader = AsyncMock(return_value=b"x" * (MAX_AVATAR_BYTES + 1))
    assert asyncio.run(cache.get("u", loader)) is None
    assert cache.size_bytes == 0


def test_lru_limits_and_key_isolation(avatar):
    cache = AvatarCache(max_entries=2, max_bytes=2 * len(avatar))
    loader = AsyncMock(return_value=avatar)

    async def scenario():
        a, b, c = ("qq", "bot", "1"), ("other", "bot", "1"), ("qq", "bot", "2")
        for key in (a, b, a, c):
            assert await cache.get(key, loader) == avatar
        assert len(cache) == 2
        assert cache.size_bytes == 2 * len(avatar)
        assert b not in cache._entries
        assert await cache.get(b, loader) == avatar
        assert loader.await_count == 4

    asyncio.run(scenario())


def test_total_byte_budget(avatar):
    cache = AvatarCache(max_entries=10, max_bytes=len(avatar))
    loader = AsyncMock(return_value=avatar)

    async def scenario():
        await cache.get("a", loader)
        await cache.get("b", loader)
        assert len(cache) == 1
        assert cache.size_bytes == len(avatar)

    asyncio.run(scenario())


def test_disabled_cache_bypasses_memory_and_disk(tmp_path, avatar):
    directory = tmp_path / "never-created"
    cache = AvatarCache(directory=directory)
    loader = AsyncMock(return_value=avatar)

    async def scenario():
        for _ in range(2):
            assert await cache.get("u", loader, enabled=False) == avatar
        assert len(cache) == 0
        assert not directory.exists()
        assert loader.await_count == 2

    asyncio.run(scenario())


def test_disk_survives_restart_and_uses_original_timestamp(tmp_path, avatar, clock):
    now, tick = clock
    loader = AsyncMock(return_value=avatar)

    def new_cache():
        return AvatarCache(directory=tmp_path, clock=tick, fresh_ttl=10, max_age=100)

    async def scenario():
        assert await new_cache().get("u", loader) == avatar
        files = list(tmp_path.glob("*.avatar"))
        assert len(files) == 1
        assert files[0].read_bytes()[8:] == avatar
        assert not list(tmp_path.glob("*.tmp"))
        now[0] += 9
        assert await new_cache().get("u", loader) == avatar
        assert loader.await_count == 1
        now[0] += 1
        loader.side_effect = TimeoutError()
        assert await new_cache().get("u", loader) == avatar
        assert loader.await_count == 2
        now[0] += 90
        assert await new_cache().get("u", loader) is None
        assert not list(tmp_path.glob("*.avatar"))

    asyncio.run(scenario())


@pytest.mark.parametrize("byte_limit", [False, True])
def test_disk_eviction_limits(tmp_path, avatar, clock, byte_limit):
    _, tick = clock
    cache = AvatarCache(
        directory=tmp_path,
        clock=tick,
        max_entries=10 if byte_limit else 2,
        max_bytes=len(avatar) * 2 if byte_limit else 1024 * 1024,
    )
    loader = AsyncMock(return_value=avatar)

    async def scenario():
        await cache.get("a", loader)
        await cache.get("b", loader)
        # 保证时间戳粒度不同的文件系统下，LRU 淘汰顺序也确定。
        path_a, path_b = cache._disk._path("a"), cache._disk._path("b")
        os.utime(path_a, ns=(1, 1))
        os.utime(path_b, ns=(2, 2))
        await cache.get("a", loader)
        await cache.get("c", loader)
        assert path_a.exists()
        assert not path_b.exists()
        files = list(tmp_path.glob("*.avatar"))
        assert len(files) == 2
        assert sum(path.stat().st_size - 8 for path in files) == len(avatar) * 2

    asyncio.run(scenario())


@pytest.mark.parametrize("payload", [b"broken", struct.pack("!d", float("nan")) + b"x"])
def test_corrupt_disk_metadata_is_replaced(tmp_path, avatar, clock, payload):
    _, tick = clock
    cache = AvatarCache(directory=tmp_path, clock=tick)
    path = cache._disk._path("u")
    path.write_bytes(payload)
    loader = AsyncMock(return_value=avatar)
    assert asyncio.run(cache.get("u", loader)) == avatar
    assert path.read_bytes()[8:] == avatar
    assert loader.await_count == 1


def test_corrupt_disk_image_is_replaced(tmp_path, avatar, clock):
    now, tick = clock
    cache = AvatarCache(directory=tmp_path, clock=tick)
    path = cache._disk._path("u")
    path.write_bytes(struct.pack("!d", now[0]) + b"not an image")
    loader = AsyncMock(return_value=avatar)
    assert asyncio.run(cache.get("u", loader)) == avatar
    assert path.read_bytes()[8:] == avatar


def test_truncated_jpeg_rejected():
    buffer = io.BytesIO()
    Image.new("RGB", (64, 64), "orange").save(buffer, format="JPEG")
    # 保留完整 JPEG 头，只截断尾部像素流，verify() 本身不会拒绝它。
    loader = AsyncMock(return_value=buffer.getvalue()[:-10])
    assert asyncio.run(AvatarCache().get("u", loader)) is None


def test_decompression_bomb_warning_rejected(avatar, monkeypatch):
    monkeypatch.setattr(Image, "MAX_IMAGE_PIXELS", 500)
    loader = AsyncMock(return_value=avatar)  # 32×24=768，超过警告阈值但未到异常阈值
    assert asyncio.run(AvatarCache().get("u", loader)) is None


def test_failed_atomic_write_keeps_old_file(tmp_path, avatar, clock, monkeypatch):
    now, tick = clock
    cache = AvatarCache(directory=tmp_path, fresh_ttl=1, clock=tick)
    loader = AsyncMock(return_value=avatar)

    async def scenario():
        await cache.get("u", loader)
        path = cache._disk._path("u")
        original = path.read_bytes()
        now[0] += 1
        monkeypatch.setattr(os, "replace", Mock(side_effect=OSError("disk full")))
        assert await cache.get("u", loader) == avatar
        assert path.read_bytes() == original
        assert not list(tmp_path.glob("*.tmp"))

    asyncio.run(scenario())


def test_expired_disk_cleanup_after_failed_refresh(tmp_path, avatar, clock):
    now, tick = clock
    cache = AvatarCache(directory=tmp_path, fresh_ttl=1, max_age=10, clock=tick)
    loader = AsyncMock(return_value=avatar)

    async def scenario():
        await cache.get("u", loader)
        now[0] += 10
        loader.return_value = None
        assert await cache.get("u", loader) is None
        assert not list(tmp_path.glob("*.avatar"))

    asyncio.run(scenario())


def test_unwritable_cache_falls_back_to_memory(tmp_path, avatar):
    blocked = tmp_path / "file-not-directory"
    blocked.write_text("block", encoding="utf-8")
    logs = []
    cache = AvatarCache(directory=blocked, logger=logs.append)
    loader = AsyncMock(return_value=avatar)

    async def scenario():
        assert await cache.get("u", loader) == avatar
        assert await cache.get("u", loader) == avatar
        assert loader.await_count == 1
        assert logs

    asyncio.run(scenario())
