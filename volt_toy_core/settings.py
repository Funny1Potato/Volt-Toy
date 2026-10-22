"""可调参数。适配层负责把它们映射到各自的配置系统。"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class Settings:
    """默认值即产品默认：额度不限、冷却关闭、过载 10 次/60 秒。"""

    receive_cap: int = 25
    """单目标每日受电上限；超出只记次数与失败，不加电量。"""

    overload_window: int = 60
    overload_threshold: int = 10
    overload_ban: int = 300

    daily_quota: int = 0
    """每日施电额度，0 表示不限。"""

    cooldown: int = 0
    """同一目标冷却秒数，0 表示关闭。"""

    crit_prob: float = 0.15
    self_efficiency: float = 0.8
    price_per_kwh: float = 0.55

    is_log: bool = False
    group_default_enabled: bool = True

    def fee(self, kwh: float) -> float:
        return round(kwh * self.price_per_kwh, 2)
