from __future__ import annotations

from volt_toy_core.rankings import kings, top
from volt_toy_core.records import new_record


def record_with(name: str, kwh: float, actor: str, count: int = 1, first: bool = False) -> dict:
    record = new_record()
    record["name"] = name
    record["kwh"] = kwh
    record["num"] = count
    record["peak"] = kwh
    record["zap_by"] = {actor: {"count": count, "first": first, "peak": True, "name": actor}}
    return record


def test_top_sorts_and_limits() -> None:
    records = {
        "u1": record_with("甲", 1.0, "a"),
        "u2": record_with("乙", 3.0, "b"),
        "u3": record_with("丙", 2.0, "c"),
    }
    items = top(records, "kwh", limit=2)
    assert [name for _, name, _ in items] == ["乙", "丙"]


def test_kings_counts_first_bonus() -> None:
    records = {
        "u1": record_with("甲", 1.0, "a", count=2, first=True),
        "u2": record_with("乙", 1.0, "b", count=3, first=False),
    }
    items = kings(records, limit=5)
    assert items[0][0] == "a"
    assert items[0][2] == 4  # 2 次 + 首电 ×2
