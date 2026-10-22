"""受电账本：一条记录 = 一个群里的一个被电者。

记录用普通 dict 保存，方便直接序列化成 JSON；字段含义见 ``new_record``。
"""

from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any

from .model import Roll

Record = dict[str, Any]


@dataclass(frozen=True, slots=True)
class Result:
    ok: bool
    reason: str
    kwh: float = 0.0
    tier: str = ""

    @property
    def failed(self) -> bool:
        return not self.ok


def new_record() -> Record:
    return {
        "num": 0,        # 受电总次数（含失败）
        "fail": 0,       # 其中因超出上限而失败的数量
        "kwh": 0.0,      # 成功部分累计度数
        "peak": 0.0,
        "peak_volt": 0.0,
        "peak_ah": 0.0,
        "day": "",       # 今日计数所属日期
        "day_num": 0,
        "day_fail": 0,
        "first_by": "",  # 首个成功施电者
        "first_ts": 0.0,
        "last": 0.0,
        "zap_by": {},    # {施电者: {count, first, peak}}
    }


def roll_day(record: Record, today: str) -> None:
    """跨日就把今日计数清零；由读取方顺带调用，不需要定时任务。"""
    if record.get("day") != today:
        record["day"] = today
        record["day_num"] = 0
        record["day_fail"] = 0


def _zap_by(record: Record, actor: str, actor_name: str = "") -> dict[str, Any]:
    entry = record.setdefault("zap_by", {}).get(actor)
    if not isinstance(entry, dict):
        entry = {"count": 0, "first": False, "peak": False}
        record["zap_by"][actor] = entry
    if actor_name:
        entry["name"] = actor_name
    return entry


def _mark_peak(record: Record, actor: str) -> None:
    for entry in record.get("zap_by", {}).values():
        if isinstance(entry, dict):
            entry["peak"] = False
    _zap_by(record, actor)["peak"] = True


def apply_zap(
    record: Record,
    actor: str,
    roll: Roll,
    *,
    cap: int,
    today: str,
    now: float | None = None,
    actor_name: str = "",
    target_name: str = "",
) -> Result:
    """把一次抽取写进记录。

    超出单目标每日上限时不拒绝，只记次数与失败：失败不加电量、
    不更新峰值、不计入施电者战绩。
    """
    now = time.time() if now is None else now
    roll_day(record, today)
    if target_name:
        record["name"] = target_name

    record["num"] = int(record.get("num", 0)) + 1
    record["day_num"] = int(record.get("day_num", 0)) + 1
    record["last"] = now

    if cap > 0 and record["day_num"] > cap:
        record["fail"] = int(record.get("fail", 0)) + 1
        record["day_fail"] = int(record.get("day_fail", 0)) + 1
        return Result(ok=False, reason="over_cap", kwh=0.0, tier=roll.tier)

    entry = _zap_by(record, actor, actor_name)
    entry["count"] = int(entry.get("count", 0)) + 1

    if not record.get("first_by"):
        record["first_by"] = actor
        record["first_ts"] = now
        entry["first"] = True

    record["kwh"] = round(float(record.get("kwh", 0.0)) + roll.kwh, 2)

    if roll.kwh > float(record.get("peak", 0.0)):
        record["peak"] = roll.kwh
        record["peak_volt"] = float(roll.volt)
        record["peak_ah"] = roll.ah
        _mark_peak(record, actor)

    return Result(ok=True, reason="ok", kwh=roll.kwh, tier=roll.tier)


def successes(record: Record) -> int:
    return int(record.get("num", 0)) - int(record.get("fail", 0))
