"""nonebot 侧配置。环境变量名即字段名的大写形式。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class Config(BaseModel):
    volt_receive_cap: int = 25
    """单目标每日受电上限；0 表示不限。"""

    volt_overload_window: int = 60
    volt_overload_threshold: int = 10
    volt_overload_ban: int = 300

    volt_daily_quota: int = 0
    """每日施电额度，0 表示不限。"""

    volt_cooldown: int = 0
    """同一目标冷却秒数，0 表示关闭。"""

    volt_crit_prob: float = 0.15
    volt_self_efficiency: float = 0.8
    volt_price_per_kwh: float = 0.55

    volt_is_log: bool = False
    volt_group_default: bool = True
    volt_whitelist: list[str] = Field(default_factory=list)

    volt_show_avatar: bool = True
    """是否在成功施电后附带被电者头像。"""

    volt_avatar_timeout: float = 5.0
