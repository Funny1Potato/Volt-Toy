"""插件配置定义。

字段名即环境变量名（大写），例如 `volt_receive_cap` → `VOLT_RECEIVE_CAP`。
"""

from nonebot import get_plugin_config
from pydantic import BaseModel, Field


class PluginConfig(BaseModel):
    volt_receive_cap: int = Field(
        25, description="单目标每日受电上限；超出只记次数与失败，不加电量（0 = 不限）"
    )
    volt_overload_window: int = Field(60, description="过载统计窗口（秒）")
    volt_overload_threshold: int = Field(10, description="窗口内最多施电次数，达到即跳闸")
    volt_overload_ban: int = Field(300, description="跳闸时长（秒）")

    volt_daily_quota: int = Field(0, description="每日施电额度（0 = 不限）")
    volt_cooldown: int = Field(0, description="同一目标冷却秒数（0 = 关闭）")

    volt_crit_prob: float = Field(0.15, description="暴击概率（0~1）")
    volt_self_efficiency: float = Field(0.8, description="电自己的效率倍率（0~1）")
    volt_price_per_kwh: float = Field(0.55, description="电价（元/度），只影响展示")

    volt_is_log: bool = Field(False, description="是否写逐条审计日志 zap_log.jsonl")
    volt_group_default: bool = Field(True, description="新群默认是否启用")
    volt_whitelist: list[str] = Field(default_factory=list, description="免电名单初始值（用户 id）")

    volt_show_avatar: bool = Field(True, description="成功施电后是否附带被电者头像（仅 QQ 系协议）")
    volt_avatar_timeout: float = Field(5.0, description="头像下载超时（秒），失败时只发文本")


__all__ = ["PluginConfig", "plugin_config"]

plugin_config: PluginConfig = get_plugin_config(PluginConfig)
