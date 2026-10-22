from __future__ import annotations

from volt_toy_core.model import Roll
from volt_toy_core.records import apply_zap, new_record, successes


def make_roll(kwh: float = 0.10, volt: int = 220, ah: float = 0.45) -> Roll:
    return Roll(volt=volt, ah=ah, kwh=kwh, tier="家用", crit=False, combo=0)


def test_new_record_shape() -> None:
    record = new_record()
    assert record["num"] == 0
    assert record["kwh"] == 0.0
    assert record["zap_by"] == {}


def test_successful_zap_accumulates() -> None:
    record = new_record()
    result = apply_zap(record, "a", make_roll(), cap=25, today="2026-10-22", now=1000.0)
    assert result.ok
    assert record["num"] == 1
    assert record["kwh"] == 0.10
    assert record["first_by"] == "a"
    assert record["zap_by"]["a"] == {"count": 1, "first": True, "peak": True}
    assert successes(record) == 1


def test_peak_moves_to_new_actor() -> None:
    record = new_record()
    apply_zap(record, "a", make_roll(0.10), cap=25, today="2026-10-22", now=1.0)
    apply_zap(record, "b", make_roll(0.50, 600, 0.83), cap=25, today="2026-10-22", now=2.0)
    assert record["peak"] == 0.50
    assert record["peak_volt"] == 600
    assert record["zap_by"]["a"]["peak"] is False
    assert record["zap_by"]["b"]["peak"] is True
    assert record["first_by"] == "a"


def test_over_cap_marks_failure_without_energy() -> None:
    record = new_record()
    for _ in range(2):
        apply_zap(record, "a", make_roll(), cap=2, today="2026-10-22", now=1.0)
    result = apply_zap(record, "b", make_roll(0.90, 900, 1.0), cap=2, today="2026-10-22", now=3.0)
    assert not result.ok
    assert result.reason == "over_cap"
    assert record["num"] == 3
    assert record["fail"] == 1
    assert record["day_fail"] == 1
    assert record["kwh"] == 0.20
    assert "b" not in record["zap_by"]


def test_day_rollover_resets_daily_counters() -> None:
    record = new_record()
    for _ in range(3):
        apply_zap(record, "a", make_roll(), cap=25, today="2026-10-22", now=1.0)
    assert record["day_num"] == 3
    apply_zap(record, "a", make_roll(), cap=25, today="2026-10-23", now=2.0)
    assert record["day_num"] == 1
    assert record["day_fail"] == 0
    assert record["num"] == 4
    assert record["kwh"] == 0.40
