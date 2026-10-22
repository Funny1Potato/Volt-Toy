"""数据文件位置：由 nonebot-plugin-localstore 统一管理。"""

from __future__ import annotations

from nonebot import logger
from nonebot_plugin_localstore import get_plugin_data_file
from volt_toy_core.storage import JsonStore, JsonlLog

ACCOUNT_FILE = get_plugin_data_file("zap.json")
LOG_FILE = get_plugin_data_file("zap_log.jsonl")
WHITELIST_FILE = get_plugin_data_file("zap_whitelist.json")

store = JsonStore(ACCOUNT_FILE, logger=logger.warning)
log = JsonlLog(LOG_FILE)
