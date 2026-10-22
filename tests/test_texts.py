from __future__ import annotations

import random
import string

import pytest

from volt_toy_core import texts
from volt_toy_core.texts import INFO_TEXT, MISSING_TEXT, POOLS, RANK_TITLES, TIER_TEXTS, pick, render

ALLOWED = {
    "actor", "target", "v", "ah", "kwh", "n", "total", "fail", "combo",
    "cap", "s", "m", "fee", "first", "rank", "peak", "name",
    "day_n", "day_fail", "used", "quota", "limit",
}


def all_templates() -> list[str]:
    items: list[str] = [INFO_TEXT, MISSING_TEXT]
    for pool in TIER_TEXTS.values():
        items.extend(pool)
    for pool in POOLS.values():
        items.extend(pool)
    items.extend(RANK_TITLES.values())
    return items


def fields_of(template: str) -> set[str]:
    return {field for _, field, _, _ in string.Formatter().parse(template) if field}


def test_every_placeholder_is_known() -> None:
    for template in all_templates():
        unknown = fields_of(template) - ALLOWED
        assert not unknown, f"未知占位符 {unknown}: {template}"


def test_every_pool_renders() -> None:
    values = {name: "x" for name in ALLOWED}
    for template in all_templates():
        assert render(template, **values)


def test_render_rejects_missing_field() -> None:
    with pytest.raises(KeyError):
        render("{actor} 电了 {target}", actor="A")


def test_pick_avoids_recent_three() -> None:
    texts.reset_recent()
    rng = random.Random(1)
    picks = [pick("combo", rng=rng) for _ in range(3)]
    assert len(set(picks)) == 3


def test_tier_pool_lookup() -> None:
    texts.reset_recent()
    assert pick("雷击") in TIER_TEXTS["雷击"]

def test_appendix_pools_have_no_placeholders() -> None:
    """连击/暴击是附加句，数据由主句负责，模板里不应出现占位符。"""
    for name in ("combo", "crit"):
        for template in POOLS[name]:
            assert not fields_of(template), (name, template)
