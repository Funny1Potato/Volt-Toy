"""框架无关的 JSON 存储：原子写、按群加锁、损坏可恢复。

调用方只负责给出文件路径（nonebot 用 localstore，astrbot 用 data 目录）
和「今天」的日期字符串。
"""

from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from typing import Any, Callable

from .model import Roll
from .records import Record, Result, apply_zap, new_record


def today_str(now: float | None = None) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(time.time() if now is None else now))


class JsonStore:
    """群用电账本。数据形状：{"v": 1, "groups": {gid: {uid: record}}}。"""

    VERSION = 1

    def __init__(self, path: str | Path, *, logger: Callable[[str], None] | None = None) -> None:
        self.path = Path(path)
        self._logger = logger or (lambda _msg: None)
        self._data: dict[str, Any] = {"v": self.VERSION, "groups": {}}
        self._locks: dict[str, asyncio.Lock] = {}
        self._loaded = False

    # ---------- 生命周期 ----------

    async def load(self) -> None:
        if self._loaded:
            return
        self.path.parent.mkdir(parents=True, exist_ok=True)
        raw = await asyncio.to_thread(self._read_text, self.path)
        if raw is None:
            data = None
        else:
            data = self._parse(raw)
            if data is None:
                data = await self._recover()
        self._data = data or {"v": self.VERSION, "groups": {}}
        self._loaded = True

    def _read_text(self, path: Path) -> str | None:
        try:
            return path.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def _parse(self, raw: str) -> dict[str, Any] | None:
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as error:
            self._logger(f"账本解析失败: {error}")
            return None
        if not isinstance(data, dict) or not isinstance(data.get("groups"), dict):
            self._logger("账本结构异常，按空账本处理")
            return None
        return data

    async def _recover(self) -> dict[str, Any] | None:
        bak = self.path.with_name(self.path.name + ".bak")
        raw = await asyncio.to_thread(self._read_text, bak)
        data = self._parse(raw) if raw else None
        if data is not None:
            self._logger(f"已从备份恢复账本: {bak}")
            return data
        corrupt = self.path.with_name(f"{self.path.name}.corrupt-{int(time.time())}")
        try:
            await asyncio.to_thread(os.replace, self.path, corrupt)
            self._logger(f"账本损坏，已保留为 {corrupt}，以空账本启动")
        except OSError as error:
            self._logger(f"保留损坏账本失败: {error}")
        return None

    def _lock(self, gid: str) -> asyncio.Lock:
        lock = self._locks.get(gid)
        if lock is None:
            lock = asyncio.Lock()
            self._locks[gid] = lock
        return lock

    # ---------- 读写 ----------

    def records(self, gid: str) -> dict[str, Record]:
        groups = self._data["groups"]
        group = groups.get(gid)
        if not isinstance(group, dict):
            group = {}
            groups[gid] = group
        return group

    def record(self, gid: str, uid: str) -> Record:
        group = self.records(gid)
        record = group.get(uid)
        if not isinstance(record, dict):
            record = new_record()
            group[uid] = record
        return record

    async def apply(
        self,
        gid: str,
        uid: str,
        actor: str,
        roll: Roll,
        *,
        cap: int,
        today: str | None = None,
        now: float | None = None,
        actor_name: str = "",
        target_name: str = "",
    ) -> Result:
        today = today or today_str(now)
        async with self._lock(gid):
            record = self.record(gid, uid)
            result = apply_zap(
                record,
                actor,
                roll,
                cap=cap,
                today=today,
                now=now,
                actor_name=actor_name,
                target_name=target_name,
            )
            await self._flush_group(gid)
            return result

    async def clear(self, gid: str, uid: str) -> bool:
        async with self._lock(gid):
            group = self.records(gid)
            if uid not in group:
                return False
            del group[uid]
            await self._flush_group(gid)
            return True

    async def snapshot(self) -> dict[str, Any]:
        return json.loads(json.dumps(self._data, ensure_ascii=False))

    # ---------- 落盘 ----------

    async def _flush_group(self, gid: str) -> None:
        payload = json.dumps(self._data, ensure_ascii=False, indent=1)
        await asyncio.to_thread(self._write_atomic, self.path, payload)

    def _write_atomic(self, path: Path, payload: str) -> None:
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(payload, encoding="utf-8")
        os.replace(tmp, path)


class JsonlLog:
    """逐条审计日志，一行一条，追加写。"""

    def __init__(self, path: str | Path) -> None:
        self.path = Path(path)

    async def append(self, event: dict[str, Any]) -> None:
        line = json.dumps(event, ensure_ascii=False, separators=(",", ":"))
        await asyncio.to_thread(self._append_sync, line)

    def _append_sync(self, line: str) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")

    async def tail(self, limit: int = 5) -> list[dict[str, Any]]:
        if not self.path.exists():
            return []
        lines = await asyncio.to_thread(self.path.read_text, "utf-8")
        items: list[dict[str, Any]] = []
        for line in lines.splitlines()[-limit:]:
            try:
                items.append(json.loads(line))
            except json.JSONDecodeError:
                continue
        return items


def read_json_list(path: str | Path) -> list[str]:
    try:
        data = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return []
    if isinstance(data, list):
        return [str(item) for item in data]
    return []


def write_json_list(path: str | Path, items: list[str]) -> None:
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(items, ensure_ascii=False, indent=1)
    tmp = target.with_name(target.name + ".tmp")
    tmp.write_text(payload, encoding="utf-8")
    os.replace(tmp, target)
