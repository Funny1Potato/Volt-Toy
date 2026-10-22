"""榜单与档案的文本渲染，两个框架共用，避免两边文案各写一份。"""

from __future__ import annotations

from . import texts
from .fmt import kwh_text
from .records import Record
from .settings import Settings
from .rankings import kings, top


def _fee(settings: Settings, kwh: float) -> str:
    return f"{settings.fee(kwh):.2f}"


def rank_kwh(records: dict[str, Record], settings: Settings, *, limit: int = 5, scope: str = "") -> str:
    items = top(records, "kwh", limit)
    if not items:
        return texts.pick("empty", scope=scope)
    lines = [texts.render(texts.RANK_TITLES["kwh"], limit=limit)]
    for index, (uid, name, value) in enumerate(items, 1):
        lines.append(f"{index}. {name or uid} {kwh_text(value)} 度 · 约 {_fee(settings, value)} 元")
    return "\n".join(lines)


def rank_top(records: dict[str, Record], *, limit: int = 5, scope: str = "") -> str:
    items = top(records, "num", limit)
    if not items:
        return texts.pick("empty", scope=scope)
    lines = [texts.render(texts.RANK_TITLES["top"], limit=limit)]
    for index, (uid, name, value) in enumerate(items, 1):
        record = records.get(uid, {})
        lines.append(f"{index}. {name or uid} {int(value)} 次（{int(record.get('fail', 0))} 失败）")
    return "\n".join(lines)


def rank_max(records: dict[str, Record], *, limit: int = 5, scope: str = "") -> str:
    items = top(records, "peak", limit)
    if not items:
        return texts.pick("empty", scope=scope)
    lines = [texts.render(texts.RANK_TITLES["max"], limit=limit)]
    for index, (uid, name, value) in enumerate(items, 1):
        record = records.get(uid, {})
        lines.append(
            f"{index}. {name or uid} {kwh_text(value)} 度"
            f"（{int(record.get('peak_volt', 0))}V / {float(record.get('peak_ah', 0)):.2f}Ah）"
        )
    return "\n".join(lines)


def rank_king(records: dict[str, Record], *, limit: int = 5, scope: str = "") -> str:
    items = kings(records, limit)
    if not items:
        return texts.pick("empty", scope=scope)
    lines = [texts.render(texts.RANK_TITLES["king"], limit=limit)]
    for index, (uid, name, value) in enumerate(items, 1):
        lines.append(f"{index}. {name or uid} 电王值 {value}")
    return "\n".join(lines)


def info_text(record: Record, settings: Settings, *, name: str = "") -> str:
    total = float(record.get("kwh", 0.0))
    return texts.render(
        texts.INFO_TEXT,
        name=record.get("name") or name or record.get("id", "?"),
        n=int(record.get("num", 0)),
        fail=int(record.get("fail", 0)),
        day_n=int(record.get("day_num", 0)),
        day_fail=int(record.get("day_fail", 0)),
        total=kwh_text(total),
        fee=_fee(settings, total),
    )
