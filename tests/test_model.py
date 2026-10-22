from __future__ import annotations

import random
from collections import Counter

from volt_toy_core.model import TIERS, settle, tier_index, tier_of


def test_roll_fields_are_consistent() -> None:
    rng = random.Random(42)
    for _ in range(500):
        roll = settle(rng=rng)
        assert abs(roll.volt * roll.ah / 1000 - roll.kwh) <= 0.006
        assert 0.0 < roll.kwh <= 2.7
        assert roll.tier in {tier.name for tier in TIERS}
        assert 100 <= roll.volt <= 1000


def test_tier_distribution_matches_weights() -> None:
    rng = random.Random(7)
    total = 20000
    counts = Counter(settle(crit=False, rng=rng).tier for _ in range(total))
    expected = {tier.name: tier.weight / 100 for tier in TIERS}
    for name, ratio in expected.items():
        assert abs(counts[name] / total - ratio) < 0.02, (name, counts[name] / total)


def test_crit_promotes_one_tier() -> None:
    base = settle(crit=False, rng=random.Random(5))
    crit = settle(crit=True, rng=random.Random(5))
    assert tier_index(crit.tier) == min(len(TIERS) - 1, tier_index(base.tier) + 1)


def test_combo_promotes_every_two_hits() -> None:
    top = len(TIERS) - 1
    one = settle(combo=1, crit=False, rng=random.Random(11))
    two = settle(combo=2, crit=False, rng=random.Random(11))
    four = settle(combo=4, crit=False, rng=random.Random(11))
    assert tier_index(two.tier) == min(top, tier_index(one.tier) + 1)
    assert tier_index(four.tier) == min(top, tier_index(one.tier) + 2)


def test_self_zap_scales_by_efficiency() -> None:
    normal = settle(crit=False, rng=random.Random(3))
    selfzap = settle(crit=False, self_zap=True, rng=random.Random(3))
    assert abs(selfzap.kwh - normal.kwh * 0.8) <= 0.02
    assert selfzap.volt == normal.volt


def test_tier_of_boundaries() -> None:
    assert tier_of(0.02) == "静电"
    assert tier_of(0.10) == "家用"
    assert tier_of(0.20) == "工业"
    assert tier_of(0.50) == "高压"
    assert tier_of(1.50) == "雷击"
