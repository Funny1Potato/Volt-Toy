"""Volt-Toy —— 电击群友。

v0.1 只做手动电：施电、记账、榜单、管理。
图片检测留了挂点，暂不实现。
"""

from nonebot import require
from nonebot.plugin import PluginMetadata

require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")

from .config import Config  # noqa: E402

__plugin_meta__ = PluginMetadata(
    name="Volt-Toy 电击群友",
    description="用指令电群友：电压 / 电量 / 度数记账，失败计数，供电局文案。",
    usage=(
        "zap [@目标] [理由] —— 施电，不 @ 则电自己\n"
        "zapkwh / zaptop / zapmax / zapking —— 度数 / 次数 / 峰值 / 电王榜\n"
        "zapinfo [@目标] —— 个人用电档案\n"
        "zapclear / zapnodo / zapon / zapoff —— 管理"
    ),
    type="application",
    homepage="https://github.com/your-name/Volt-Toy",
    config=Config,
    supported_adapters=None,
)

from . import commands as _commands  # noqa: E402,F401
