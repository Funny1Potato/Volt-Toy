"""热状态：冷却、连击、额度、跳闸。重启清空可以接受。"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field

from .storage import today_str


@dataclass
class RuntimeState:
    enabled: dict[str, bool] = field(default_factory=dict)
    cooldown_at: dict[tuple[str, str], float] = field(default_factory=dict)
    combo: dict[tuple[str, str], deque[float]] = field(default_factory=dict)
    overload: dict[tuple[str, str], deque[float]] = field(default_factory=dict)
    ban_until: dict[tuple[str, str], float] = field(default_factory=dict)
    quota: dict[tuple[str, str], tuple[str, int]] = field(default_factory=dict)
    whitelist: set[str] = field(default_factory=set)

    def group_enabled(self, gid: str, default: bool) -> bool:
        return self.enabled.get(gid, default)

    def set_group_enabled(self, gid: str, value: bool) -> None:
        self.enabled[gid] = value

    def combo_count(self, gid: str, uid: str, now: float, window: float = 600.0) -> int:
        bucket = self.combo.setdefault((gid, uid), deque())
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        return len(bucket)

    def mark_combo(self, gid: str, uid: str, now: float) -> None:
        self.combo.setdefault((gid, uid), deque()).append(now)

    def cooldown_left(self, gid: str, uid: str, now: float, seconds: int) -> float:
        if seconds <= 0:
            return 0.0
        last = self.cooldown_at.get((gid, uid), 0.0)
        return max(0.0, seconds - (now - last))

    def overload_left(self, gid: str, actor: str, now: float) -> float:
        return max(0.0, self.ban_until.get((gid, actor), 0.0) - now)

    def note_action(
        self, gid: str, actor: str, now: float, window: int, threshold: int, ban: int
    ) -> None:
        bucket = self.overload.setdefault((gid, actor), deque())
        while bucket and now - bucket[0] > window:
            bucket.popleft()
        bucket.append(now)
        if threshold > 0 and len(bucket) >= threshold:
            self.ban_until[(gid, actor)] = now + ban
            bucket.clear()

    def quota_left(self, gid: str, actor: str, now: float, limit: int) -> int:
        if limit <= 0:
            return -1
        day = today_str(now)
        stored_day, used = self.quota.get((gid, actor), (day, 0))
        if stored_day != day:
            used = 0
        return max(0, limit - used)

    def consume_quota(self, gid: str, actor: str, now: float, limit: int) -> None:
        if limit <= 0:
            return
        day = today_str(now)
        stored_day, used = self.quota.get((gid, actor), (day, 0))
        if stored_day != day:
            used = 0
        self.quota[(gid, actor)] = (day, used + 1)
