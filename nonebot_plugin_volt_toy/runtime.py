"""插件级单例：配置、状态、存储与服务。"""

from __future__ import annotations

from nonebot import get_driver, logger
from volt_toy_core.service import ZapService
from volt_toy_core.settings import Settings
from volt_toy_core.state import RuntimeState
from volt_toy_core.storage import JsonStore, read_json_list, write_json_list

from . import store as store_module
from .config import plugin_config as config

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

# store / service 在 startup 时才就绪（localstore 需要插件已加载才能推断调用方）。
service: ZapService


def get_store() -> JsonStore:
    return store_module.store


def load_whitelist() -> set[str]:
    stored = read_json_list(store_module.WHITELIST_FILE)
    if stored:
        return set(stored)
    return {str(item) for item in config.volt_whitelist}


def save_whitelist(items: set[str]) -> None:
    write_json_list(store_module.WHITELIST_FILE, sorted(items))


@get_driver().on_startup
async def _prepare() -> None:
    global service
    store_module.resolve()
    await store_module.store.load()
    state.whitelist = load_whitelist()
    service = ZapService(
        store=store_module.store,
        state=state,
        settings=settings,
        log=store_module.log,
    )
    logger.debug(f"Volt-Toy 账本: {store_module.ACCOUNT_FILE}")
