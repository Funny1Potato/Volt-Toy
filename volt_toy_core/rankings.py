"""榜单聚合：输入一个群的记录，输出排好序的列表。

展示层只负责把 (名字, 数值) 拼成文本，不参与计算。
"""

from __future__ import annotations

from typing import Any

from .records import Record


def _name(uid: str, record: Record | None) -> str:
    if record:
        name = record.get("name")
        if name:
            return str(name)
    return uid


def top(
    records: dict[str, Record],
    key: str,
    limit: int = 5,
) -> list[tuple[str, str, float]]:
    """按记录字段排序，返回 [(uid, 显示名, 数值)]。"""
    items: list[tuple[str, str, float]] = []
    for uid, record in records.items():
        try:
            value = float(record.get(key, 0))
        except (TypeError, ValueError):
            continue
        items.append((uid, _name(uid, record), value))
    items.sort(key=lambda item: item[2], reverse=True)
    return items[:limit]


def kings(records: dict[str, Record], limit: int = 5) -> list[tuple[str, str, int]]:
    """电王榜：成功施电次数 + 首电次数 × 2。失败不进榜。"""
    stats: dict[str, dict[str, Any]] = {}
    for record in records.values():
        for actor, entry in (record.get("zap_by") or {}).items():
            stat = stats.setdefault(actor, {"count": 0, "first": 0, "name": ""})
            stat["count"] += int(entry.get("count", 0) or 0)
            if entry.get("first"):
                stat["first"] += 1
            name = entry.get("name")
            if name:
                stat["name"] = str(name)
    result = [
        (actor, str(stat["name"] or actor), int(stat["count"]) + int(stat["first"]) * 2)
        for actor, stat in stats.items()
    ]
    result.sort(key=lambda item: item[2], reverse=True)
    return result[:limit]
