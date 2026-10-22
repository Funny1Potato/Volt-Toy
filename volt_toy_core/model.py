"""三步抽样：抽档位 → 档内抽能量 → 拆成电压与电量。

第 3 步默认保证 ``V * Ah / 1000 == kWh``（在舍入误差内），
因此电量不需要单独封顶，也不会出现堆在边界的固定值。
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Tier:
    name: str
    weight: int
    e_min: float
    e_max: float
    v_min: float
    v_max: float


TIERS: tuple[Tier, ...] = (
    Tier("静电", 40, 0.01, 0.05, 120, 180),
    Tier("家用", 30, 0.05, 0.15, 180, 240),
    Tier("工业", 18, 0.15, 0.35, 240, 380),
    Tier("高压", 9, 0.35, 0.80, 380, 800),
    Tier("雷击", 3, 0.80, 2.60, 800, 1000),
)

_TOP = len(TIERS) - 1


@dataclass(frozen=True, slots=True)
class Roll:
    volt: int
    ah: float
    kwh: float
    tier: str
    crit: bool
    combo: int

    @property
    def energy_wh(self) -> float:
        return self.volt * self.ah


def tier_index(name: str) -> int:
    for index, tier in enumerate(TIERS):
        if tier.name == name:
            return index
    raise KeyError(f"未知档位: {name}")


def tier_of(kwh: float) -> str:
    """按度数反查档位；用于展示或迁移旧数据。"""
    for tier in TIERS:
        if kwh <= tier.e_max:
            return tier.name
    return TIERS[-1].name


def _pick_tier(rng: random.Random) -> int:
    total = sum(tier.weight for tier in TIERS)
    point = rng.random() * total
    acc = 0.0
    for index, tier in enumerate(TIERS):
        acc += tier.weight
        if point < acc:
            return index
    return _TOP


def settle(
    *,
    combo: int = 0,
    crit: bool | None = None,
    self_zap: bool = False,
    crit_prob: float = 0.15,
    self_efficiency: float = 0.8,
    rng: random.Random | None = None,
) -> Roll:
    """掷一次电击。

    ``combo`` 为同一目标 10 分钟内的受电次数；每满 2 次升一档，
    暴击再升一档，最高到雷击档。
    """
    rng = rng or random
    is_crit = rng.random() < crit_prob if crit is None else crit
    index = _pick_tier(rng)
    index = min(_TOP, index + combo // 2 + int(is_crit))
    tier = TIERS[index]

    log_lo = math.log10(tier.e_min)
    log_hi = math.log10(tier.e_max)
    energy = 10 ** (log_lo + rng.random() * (log_hi - log_lo))
    volt = rng.uniform(tier.v_min, tier.v_max)
    ah = energy * 1000 / volt

    if self_zap:
        energy *= self_efficiency
        ah *= self_efficiency

    volt_i = int(round(volt))
    ah_r = round(ah, 2)
    kwh = round(volt_i * ah_r / 1000, 2)
    return Roll(volt=volt_i, ah=ah_r, kwh=kwh, tier=tier.name, crit=is_crit, combo=combo)
