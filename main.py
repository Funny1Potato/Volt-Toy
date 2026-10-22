"""Volt-Toy 的 AstrBot 适配。

目录约定：本文件位于仓库根目录，AstrBot 把整个仓库克隆到 data/plugins/ 下即可加载；
`volt_toy_core` 与它同级，无需另装依赖。

官方依据：
- 插件结构：metadata.yaml + main.py + _conf_schema.json
- 事件：AstrMessageEvent.get_sender_id / get_sender_name / get_group_id /
  unified_msg_origin / get_messages / is_admin / plain_result / chain_result
- 组件：astrbot.api.message_components 的 At / Plain / Image.fromURL
- 配置：__init__(self, context, config: AstrBotConfig)
- 数据目录：data/plugin_data/<插件名>/
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))

from astrbot.api import AstrBotConfig, logger
from astrbot.api.event import AstrMessageEvent, filter
from astrbot.api.message_components import At, Image, Plain
from astrbot.api.star import Context, Star

from volt_toy_core import texts
from volt_toy_core.render import info_text, rank_king, rank_kwh, rank_max, rank_top
from volt_toy_core.service import ZapRequest, ZapService
from volt_toy_core.settings import Settings
from volt_toy_core.state import RuntimeState
from volt_toy_core.storage import JsonStore, JsonlLog, read_json_list, write_json_list

PLUGIN_NAME = "astrbot_plugin_volt_toy"
QQ_PLATFORMS = {"aiocqhttp", "qq_official", "qq_official_webhook"}
AVATAR_URL = "https://q4.qlogo.cn/headimg_dl?dst_uin={uid}&spec=640"


def _data_dir(name: str) -> Path:
    try:
        from astrbot.core.utils.astrbot_path import get_astrbot_data_path

        return Path(get_astrbot_data_path()) / "plugin_data" / name
    except Exception as error:  # 老版本没有这个工具函数时退回插件目录
        logger.warning(f"volt-toy: 取 AstrBot 数据目录失败，改用插件目录: {error}")
        return _ROOT / "data"


def _settings(config: AstrBotConfig | dict | None) -> Settings:
    data = config or {}

    def get(key: str, default: object) -> object:
        value = data.get(key, default)
        return default if value is None else value

    return Settings(
        receive_cap=int(get("volt_receive_cap", 25)),
        overload_window=int(get("volt_overload_window", 60)),
        overload_threshold=int(get("volt_overload_threshold", 10)),
        overload_ban=int(get("volt_overload_ban", 300)),
        daily_quota=int(get("volt_daily_quota", 0)),
        cooldown=int(get("volt_cooldown", 0)),
        crit_prob=float(get("volt_crit_prob", 0.15)),
        self_efficiency=float(get("volt_self_efficiency", 0.8)),
        price_per_kwh=float(get("volt_price_per_kwh", 0.55)),
        is_log=bool(get("volt_is_log", False)),
        group_default_enabled=bool(get("volt_group_default", True)),
    )


class VoltToy(Star):
    def __init__(self, context: Context, config: AstrBotConfig | None = None):
        super().__init__(context)
        self.config = config or {}
        self.settings = _settings(self.config)
        self.state = RuntimeState()

        base = _data_dir(getattr(self, "name", PLUGIN_NAME))
        self._store = JsonStore(base / "zap.json", logger=logger.warning)
        self._log = JsonlLog(base / "zap_log.jsonl")
        self._whitelist_path = base / "zap_whitelist.json"
        self.service = ZapService(self._store, self.state, self.settings, log=self._log)

        self._ready = False
        self._ready_lock = asyncio.Lock()

    async def _ensure(self) -> None:
        if self._ready:
            return
        async with self._ready_lock:
            if self._ready:
                return
            await self._store.load()
            self.state.whitelist = self._load_whitelist()
            self._ready = True

    def _load_whitelist(self) -> set[str]:
        stored = read_json_list(self._whitelist_path)
        if stored:
            return set(stored)
        initial = self.config.get("volt_whitelist", []) if self.config else []
        return {str(item) for item in (initial or [])}

    def _save_whitelist(self) -> None:
        write_json_list(self._whitelist_path, sorted(self.state.whitelist))

    # ---------- 事件适配 ----------

    @staticmethod
    def _uid(event: AstrMessageEvent) -> str:
        return str(event.get_sender_id() or "")

    def _name(self, event: AstrMessageEvent) -> str:
        return str(event.get_sender_name() or self._uid(event))

    @staticmethod
    def _gid(event: AstrMessageEvent) -> str:
        # platform:message_type:session_id，天然区分群聊/私聊/频道
        return str(event.unified_msg_origin)

    @staticmethod
    def _at_target(event: AstrMessageEvent) -> tuple[str, str] | None:
        for component in event.get_messages():
            if isinstance(component, At):
                qq = str(getattr(component, "qq", "") or "")
                if qq and qq != "all":
                    return qq, str(getattr(component, "name", "") or qq)
        return None

    def _avatar(self, event: AstrMessageEvent, uid: str) -> str:
        if not self.config.get("volt_show_avatar", True):
            return ""
        if event.get_platform_name() not in QQ_PLATFORMS or not uid.isdigit():
            return ""
        return AVATAR_URL.format(uid=uid)

    async def _resolve_target(self, event: AstrMessageEvent) -> tuple[str, str, bool]:
        at = self._at_target(event)
        if at is None:
            return self._uid(event), self._name(event), True
        return at[0], at[1], at[0] == self._uid(event)

    # ---------- 指令 ----------

    @filter.command("zap", alias={"电", "电击", "雷"})
    async def zap(self, event: AstrMessageEvent):
        """电击群友：/zap @某人，或 /zap 电自己。"""
        await self._ensure()
        gid = self._gid(event)
        actor = self._uid(event)
        actor_name = self._name(event)
        target, target_name, self_zap = await self._resolve_target(event)

        if target and target == str(event.get_self_id() or ""):
            yield event.plain_result(
                texts.render(texts.pick("bot", scope=gid), actor=actor_name, target=target_name)
            )
            return

        outcome = await self.service.zap(
            ZapRequest(
                gid=gid,
                actor=actor,
                target=target,
                actor_name=actor_name,
                target_name=target_name or target,
                self_zap=self_zap,
                privileged=bool(event.is_admin()),
            )
        )

        avatar = self._avatar(event, target) if outcome.ok else ""
        if avatar:
            # 顺序固定：被电文案 → 头像 → 统计
            yield event.chain_result(
                [
                    Plain(outcome.main_text),
                    Image.fromURL(avatar),
                    Plain(outcome.stats_text),
                ]
            )
        else:
            yield event.plain_result(outcome.text)

    @filter.command("zapkwh", alias={"度数榜", "电费榜"})
    async def zapkwh(self, event: AstrMessageEvent):
        """累计度数榜。"""
        await self._ensure()
        gid = self._gid(event)
        yield event.plain_result(rank_kwh(self._store.records(gid), self.settings, scope=gid))

    @filter.command("zaptop", alias={"被电榜"})
    async def zaptop(self, event: AstrMessageEvent):
        """受电次数榜。"""
        await self._ensure()
        gid = self._gid(event)
        yield event.plain_result(rank_top(self._store.records(gid), scope=gid))

    @filter.command("zapmax", alias={"峰值榜"})
    async def zapmax(self, event: AstrMessageEvent):
        """单次最高度数榜。"""
        await self._ensure()
        gid = self._gid(event)
        yield event.plain_result(rank_max(self._store.records(gid), scope=gid))

    @filter.command("zapking", alias={"电王榜"})
    async def zapking(self, event: AstrMessageEvent):
        """施电次数榜。"""
        await self._ensure()
        gid = self._gid(event)
        yield event.plain_result(rank_king(self._store.records(gid), scope=gid))

    @filter.command("zapinfo", alias={"电档"})
    async def zapinfo(self, event: AstrMessageEvent):
        """个人用电档案。"""
        await self._ensure()
        gid = self._gid(event)
        target, target_name, _ = await self._resolve_target(event)
        record = self._store.records(gid).get(target)
        if not record:
            yield event.plain_result(texts.render(texts.MISSING_TEXT, name=target_name or target))
            return
        yield event.plain_result(info_text(record, self.settings, name=target_name))

    @filter.command("zapclear")
    async def zapclear(self, event: AstrMessageEvent):
        """清除某人的用电记录（管理员）。"""
        await self._ensure()
        if not event.is_admin():
            yield event.plain_result("无权限使用此命令。")
            return
        gid = self._gid(event)
        target, target_name, _ = await self._resolve_target(event)
        if not await self._store.clear(gid, target):
            yield event.plain_result(f"没有查到 {target_name or target} 的用电记录。")
            return
        yield event.plain_result(
            texts.render(texts.pick("clear", scope=gid), name=target_name or target, actor=self._name(event))
        )

    @filter.command("zapnodo", alias={"绝缘"})
    async def zapnodo(self, event: AstrMessageEvent):
        """切换免电名单（管理员）。"""
        await self._ensure()
        if not event.is_admin():
            yield event.plain_result("无权限使用此命令。")
            return
        target, target_name, _ = await self._resolve_target(event)
        if target in self.state.whitelist:
            self.state.whitelist.discard(target)
            self._save_whitelist()
            yield event.plain_result(f"已解除 {target_name or target} 的免电保护。")
        else:
            self.state.whitelist.add(target)
            self._save_whitelist()
            yield event.plain_result(f"已将 {target_name or target} 加入免电名单。")

    @filter.command("zapon")
    async def zapon(self, event: AstrMessageEvent):
        """恢复本群用电业务（管理员）。"""
        await self._ensure()
        if not event.is_admin():
            yield event.plain_result("无权限使用此命令。")
            return
        self.state.set_group_enabled(self._gid(event), True)
        yield event.plain_result("本群用电业务已恢复。")

    @filter.command("zapoff")
    async def zapoff(self, event: AstrMessageEvent):
        """停止本群用电业务（管理员）。"""
        await self._ensure()
        if not event.is_admin():
            yield event.plain_result("无权限使用此命令。")
            return
        self.state.set_group_enabled(self._gid(event), False)
        yield event.plain_result("本群用电业务已停止。")

    async def terminate(self):
        """插件被停用时的清理钩子。"""
        self._ready = False
