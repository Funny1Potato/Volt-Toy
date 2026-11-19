"""有界的异步头像原图缓存；平台提供缓存目录，不涉及账本与特效图。"""

from __future__ import annotations

import asyncio
import hashlib
import io
import math
import os
import struct
import tempfile
import threading
import time
import warnings
from collections import OrderedDict
from collections.abc import Awaitable, Callable, Hashable
from contextlib import suppress
from dataclasses import dataclass
from pathlib import Path

MAX_AVATAR_BYTES = 5 * 1024 * 1024
Loader = Callable[[], Awaitable[bytes | None]]


def _valid_image(raw: bytes) -> bool:
    # 防止 HTTP 200 的错误页面、截断图片和超大图片污染缓存。
    from PIL import Image

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(raw)) as image:
                image.verify()
            # JPEG 的 verify() 不会解码像素；再加载首帧以拒绝截断的图像。
            with Image.open(io.BytesIO(raw)) as image:
                image.load()
        return True
    except Exception:
        return False


@dataclass
class _Entry:
    raw: bytes | None
    fetched_at: float
    retry_at: float = 0.0


class _DiskCache:
    """每个文件 = 8 字节下载时间 + 原图；文件 mtime 仅用于 LRU。"""

    def __init__(self, directory: Path, cache: AvatarCache, logger: Callable[[str], None]):
        self.directory = directory
        self.cache = cache
        self.logger = logger
        self.lock = threading.Lock()

    def _path(self, key: Hashable) -> Path:
        digest = hashlib.sha256(repr(key).encode("utf-8")).hexdigest()
        return self.directory / f"{digest}.avatar"

    def _prune(self) -> None:
        now = self.cache._clock()
        files = []
        for path in self.directory.glob("*.avatar"):
            stat = path.stat()
            with path.open("rb") as handle:
                header = handle.read(8)
            stamp = struct.unpack("!d", header)[0] if len(header) == 8 else float("nan")
            if (
                not math.isfinite(stamp)
                or not 0 <= now - stamp < self.cache.max_age
                or not 8 < stat.st_size <= MAX_AVATAR_BYTES + 8
            ):
                path.unlink(missing_ok=True)
            else:
                files.append((stat.st_mtime_ns, path, stat.st_size - 8))
        total = sum(size for _, _, size in files)
        count = len(files)
        for _, path, size in sorted(files):
            if count <= self.cache.max_entries and total <= self.cache.max_bytes:
                break
            path.unlink(missing_ok=True)
            total -= size
            count -= 1
        # 清理异常退出遗留的临时文件，不碰正在写入的文件。
        for path in self.directory.glob("avatar-*.tmp"):
            if now - path.stat().st_mtime > self.cache.max_age:
                path.unlink(missing_ok=True)

    def read(self, key: Hashable) -> _Entry | None:
        with self.lock:
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                self._prune()
                path = self._path(key)
                if not path.exists():
                    return None
                with path.open("rb") as handle:
                    payload = handle.read(MAX_AVATAR_BYTES + 9)
                stamp = struct.unpack("!d", payload[:8])[0]
                raw = payload[8:]
                if not _valid_image(raw):
                    path.unlink(missing_ok=True)
                    return None
                path.touch()
                return _Entry(raw, stamp)
            except (OSError, ValueError, struct.error) as error:
                self.logger(f"volt-toy: 头像缓存读取失败，改用下载: {error}")
                return None

    def write(self, key: Hashable, entry: _Entry) -> None:
        with self.lock:
            temporary = None
            try:
                self.directory.mkdir(parents=True, exist_ok=True)
                with tempfile.NamedTemporaryFile(
                    dir=self.directory, prefix="avatar-", suffix=".tmp", delete=False
                ) as handle:
                    temporary = Path(handle.name)
                    handle.write(struct.pack("!d", entry.fetched_at))
                    handle.write(entry.raw or b"")
                os.replace(temporary, self._path(key))
                self._prune()
            except OSError as error:
                self.logger(f"volt-toy: 头像缓存写入失败，仅使用内存: {error}")
            finally:
                if temporary is not None:
                    with suppress(OSError):
                        temporary.unlink(missing_ok=True)

    def cleanup(self) -> None:
        with self.lock:
            try:
                if self.directory.exists():
                    self._prune()
            except OSError as error:
                self.logger(f"volt-toy: 头像缓存清理失败: {error}")

    def touch(self, key: Hashable) -> None:
        with self.lock:
            try:
                path = self._path(key)
                if path.exists():
                    path.touch()
            except OSError:
                pass


class AvatarCache:
    """单事件循环使用；同 key 下载合并，单个等待者取消不影响其它等待者。

    fresh_ttl 内直读；超过后尝试刷新，失败时仅在 max_age 内沿用旧图。
    失败后 retry_delay 内不重复下载（含首次失败），且不会延长旧图寿命。
    """

    def __init__(
        self,
        *,
        fresh_ttl: float = 3600,
        max_age: float = 86400,
        retry_delay: float = 30,
        max_entries: int = 128,
        max_bytes: int = 32 * 1024 * 1024,
        clock: Callable[[], float] = time.time,
        directory: Path | None = None,
        logger: Callable[[str], None] | None = None,
    ) -> None:
        if not (0 <= fresh_ttl <= max_age and retry_delay >= 0):
            raise ValueError("invalid avatar cache TTL")
        if max_entries < 1 or max_bytes < 1:
            raise ValueError("avatar cache limits must be positive")
        self.fresh_ttl = fresh_ttl
        self.max_age = max_age
        self.retry_delay = retry_delay
        self.max_entries = max_entries
        self.max_bytes = max_bytes
        self._clock = clock
        self._entries: OrderedDict[Hashable, _Entry] = OrderedDict()
        self._inflight: dict[Hashable, asyncio.Task[bytes | None]] = {}
        self._size_bytes = 0
        self._disk = (
            _DiskCache(Path(directory), self, logger or (lambda _: None)) if directory else None
        )

    def __len__(self) -> int:
        return len(self._entries)

    @property
    def size_bytes(self) -> int:
        return self._size_bytes

    def _put(self, key: Hashable, entry: _Entry) -> None:
        previous = self._entries.pop(key, None)
        if previous is not None:
            self._size_bytes -= len(previous.raw or b"")
        size = len(entry.raw or b"")
        if size > self.max_bytes:
            return
        self._entries[key] = entry
        self._size_bytes += size
        while len(self._entries) > self.max_entries or self._size_bytes > self.max_bytes:
            _, removed = self._entries.popitem(last=False)
            self._size_bytes -= len(removed.raw or b"")

    def _usable(self, entry: _Entry, now: float) -> bytes | None:
        return entry.raw if 0 <= now - entry.fetched_at < self.max_age else None

    @staticmethod
    async def _download(loader: Loader) -> bytes | None:
        try:
            raw = await loader()
        except Exception:
            return None
        if not isinstance(raw, bytes) or not raw or len(raw) > MAX_AVATAR_BYTES:
            return None
        return raw if await asyncio.to_thread(_valid_image, raw) else None

    async def get(self, key: Hashable, loader: Loader, *, enabled: bool = True) -> bytes | None:
        if not enabled:
            return await self._download(loader)
        now = self._clock()
        entry = self._entries.get(key)
        if entry is not None:
            self._entries.move_to_end(key)
            if entry.raw is not None and 0 <= now - entry.fetched_at < self.fresh_ttl:
                if self._disk is not None:
                    await asyncio.to_thread(self._disk.touch, key)
                return entry.raw
            if now < entry.retry_at:
                return self._usable(entry, now)
        task = self._inflight.get(key)
        if task is None:
            task = asyncio.create_task(self._refresh(key, loader))
            self._inflight[key] = task
        return await asyncio.shield(task)

    async def _refresh(self, key: Hashable, loader: Loader) -> bytes | None:
        previous = self._entries.get(key)
        try:
            if previous is not None and self._disk is not None:
                await asyncio.to_thread(self._disk.cleanup)
            if previous is None and self._disk is not None:
                previous = await asyncio.to_thread(self._disk.read, key)
                if previous is not None:
                    self._put(key, previous)
                    if 0 <= self._clock() - previous.fetched_at < self.fresh_ttl:
                        return previous.raw
            raw = await self._download(loader)
            now = self._clock()
            if raw is not None:
                entry = _Entry(raw, now)
                self._put(key, entry)
                if self._disk is not None:
                    await asyncio.to_thread(self._disk.write, key, entry)
                return raw
            stale = self._usable(previous, now) if previous is not None else None
            fetched_at = previous.fetched_at if stale is not None else now
            self._put(key, _Entry(stale, fetched_at, now + self.retry_delay))
            return stale
        finally:
            self._inflight.pop(key, None)
