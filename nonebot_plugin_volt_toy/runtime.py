"""插件级单例：配置、状态、存储与服务。"""

from __future__ import annotations

from nonebot import get_driver, get_plugin_config
from volt_toy_core.service import ZapService
from volt_toy_core.settings import Settings
from volt_toy_core.state import RuntimeState
from volt_toy_core.storage import read_json_list, write_json_list

from .config import Config
from .store import WHITELIST_FILE, log, store

config = get_plugin_config(Config)

settings = Settings(
    receive_cap=config.volt_receive_cap,
    overload_window=config.volt_overload_window,
    overload_threshold=config.volt_overload_threshold,
    overload_ban=config.volt_overload_ban,
    daily_quota=config.volt_daily_quota,
    cooldown=config.volt_cooldown,
    crit_prob=config.volt_crit_prob,
    self_efficiency=config.volt_self_efficiency,
    price_per_kwh=config.volt_price_per_kwh,
    is_log=config.volt_is_log,
    group_default_enabled=config.volt_group_default,
)

state = RuntimeState()
service = ZapService(store=store, state=state, settings=settings, log=log)


def load_whitelist() -> set[str]:
    stored = read_json_list(WHITELIST_FILE)
    if stored:
        return set(stored)
    return {str(item) for item in config.volt_whitelist}


def save_whitelist(items: set[str]) -> None:
    write_json_list(WHITELIST_FILE, sorted(items))


@get_driver().on_startup
async def _prepare() -> None:
    await store.load()
    state.whitelist = load_whitelist()
