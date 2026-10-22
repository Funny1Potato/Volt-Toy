"""数据文件位置：由 nonebot-plugin-localstore 统一管理。

localstore 通过调用栈推断「是哪个插件在要文件」。导入期调用要求模块
已经被 nonebot 登记为插件；一旦插件是以普通模块方式被 import（例如
editable 安装时被其他 finder 抢先解析），这里就会抛
``Cannot detect caller plugin``。把解析推迟到 startup，两种加载方式都安全。
"""

from __future__ import annotations

from pathlib import Path

from nonebot import logger
from nonebot_plugin_localstore import get_plugin_data_file
from volt_toy_core.storage import JsonStore, JsonlLog

ACCOUNT_FILE: Path
LOG_FILE: Path
WHITELIST_FILE: Path

store: JsonStore
log: JsonlLog


def resolve() -> None:
    """在插件加载完成后调用一次，构造存储对象。"""
    global ACCOUNT_FILE, LOG_FILE, WHITELIST_FILE, store, log
    ACCOUNT_FILE = get_plugin_data_file("zap.json")
    LOG_FILE = get_plugin_data_file("zap_log.jsonl")
    WHITELIST_FILE = get_plugin_data_file("zap_whitelist.json")
    store = JsonStore(ACCOUNT_FILE, logger=logger.warning)
    log = JsonlLog(LOG_FILE)
