"""Volt-Toy —— 电击群友。

v0.1 只做手动电：施电、记账、榜单、管理。
图片检测留了挂点，暂不实现。
"""

__version__ = "0.1.5"

from nonebot import require

# require 必须先于任何 import：否则这两个库会以「被普通 import」的方式装载，
# require 会判定它们不是插件并抛错。
require("nonebot_plugin_localstore")
require("nonebot_plugin_alconna")
require("nonebot_plugin_uninfo")

from nonebot.plugin import PluginMetadata, inherit_supported_adapters  # noqa: E402

from .config import PluginConfig  # noqa: E402

__plugin_meta__ = PluginMetadata(
    name="Volt-Toy 电击群友",
    description="用指令电群友的群聊玩具：电压、电量、度数记账，带连击、暴击与供电局文案。",
    usage=(
        "zap [@目标] —— 施电，不 @ 则电自己\n"
        "zapkwh / zaptop / zapmax / zapking —— 度数 / 次数 / 峰值 / 电王榜\n"
        "zapinfo [@目标] —— 个人用电档案\n"
        "zapclear / zapnodo / zapon / zapoff —— 管理"
    ),
    type="application",
    config=PluginConfig,
    # 收发走 alconna 的 uniseg、会话信息走 uninfo，因此声明两者共同支持的适配器
    supported_adapters=inherit_supported_adapters(
        "nonebot_plugin_alconna",
        "nonebot_plugin_uninfo",
    ),
    homepage="https://github.com/Funny1Potato/Volt-Toy",
    extra={"License": "MIT", "Author": "Funny1Potato"},
)

from nonebot import logger  # noqa: E402

logger.info(f"Volt-Toy {__version__} loaded from {__file__}")

from . import commands as _commands  # noqa: E402,F401
