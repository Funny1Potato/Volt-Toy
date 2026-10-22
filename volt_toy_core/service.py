"""业务编排：一次 zap 从校验到出文案，框架适配层只负责收发。

这样 nonebot 与 astrbot 的差异只剩「谁在哪个群、叫什么名字、怎么发消息」。
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from . import texts
from .fmt import fee_text, kwh_text, span_text
from .model import Roll, settle
from .settings import Settings
from .state import RuntimeState
from .storage import JsonStore, JsonlLog, today_str


@dataclass(frozen=True, slots=True)
class ZapRequest:
    gid: str
    actor: str
    target: str
    actor_name: str = ""
    target_name: str = ""
    self_zap: bool = False
    privileged: bool = False
    now: float | None = None


@dataclass(slots=True)
class Outcome:
    ok: bool
    reason: str
    text: str
    """完整文本（main_text + stats_text），供不能插图或不需要分段的场景使用。"""
    main_text: str = ""
    """被电文案（档位 + 连击/暴击附加），发送时放在头像前面。"""
    stats_text: str = ""
    """统计行，发送时放在头像后面。"""
    roll: Roll | None = None
    target: str = ""
    kwh: float = 0.0
    total: float = 0.0
    fails: int = 0
    count: int = 0
    extra: dict[str, object] = field(default_factory=dict)


class ZapService:
    def __init__(
        self,
        store: JsonStore,
        state: RuntimeState,
        settings: Settings,
        *,
        log: JsonlLog | None = None,
    ) -> None:
        self.store = store
        self.state = state
        self.settings = settings
        self.log = log

    # ---------- 文案辅助 ----------

    def _values(self, req: ZapRequest, **extra: object) -> dict[str, object]:
        values: dict[str, object] = {
            "actor": req.actor_name or req.actor,
            "target": req.target_name or req.target,
            "n": 0,
            "total": "0.00",
            "fail": 0,
            "fee": "0.00",
            "cap": self.settings.receive_cap,
            "name": req.target_name or req.target,
        }
        values.update(extra)
        return values

    def _blocked(self, reason: str, pool: str, req: ZapRequest, **extra: object) -> Outcome:
        text = texts.render(texts.pick(pool, scope=req.gid), **self._values(req, **extra))
        return Outcome(ok=False, reason=reason, text=text, target=req.target)

    # ---------- 主流程 ----------

    async def zap(self, req: ZapRequest) -> Outcome:
        now = time.time() if req.now is None else req.now
        settings = self.settings

        if not self.state.group_enabled(req.gid, settings.group_default_enabled):
            return Outcome(ok=False, reason="disabled", text="本群已关闭用电业务。", target=req.target)

        if req.target in self.state.whitelist and not req.privileged:
            return self._blocked("immune", "immune", req)

        ban_left = self.state.overload_left(req.gid, req.actor, now)
        if ban_left > 0:
            minutes, seconds = span_text(ban_left)
            return self._blocked("overload", "overload", req, m=minutes, s=seconds)

        cooldown_left = self.state.cooldown_left(req.gid, req.target, now, settings.cooldown)
        if cooldown_left > 0:
            return self._blocked("cooldown", "cooldown", req, s=int(cooldown_left) + 1)

        quota_left = self.state.quota_left(req.gid, req.actor, now, settings.daily_quota)
        if quota_left == 0:
            return self._blocked(
                "quota", "quota", req, used=settings.daily_quota, quota=settings.daily_quota
            )

        combo = self.state.combo_count(req.gid, req.target, now)
        roll = settle(
            combo=combo,
            self_zap=req.self_zap,
            crit_prob=settings.crit_prob,
            self_efficiency=settings.self_efficiency,
        )

        result = await self.store.apply(
            req.gid,
            req.target,
            req.actor,
            roll,
            cap=settings.receive_cap,
            now=now,
            actor_name=req.actor_name,
            target_name=req.target_name,
        )
        record = self.store.record(req.gid, req.target)

        self.state.mark_combo(req.gid, req.target, now)
        self.state.note_action(
            req.gid,
            req.actor,
            now,
            settings.overload_window,
            settings.overload_threshold,
            settings.overload_ban,
        )
        self.state.consume_quota(req.gid, req.actor, now, settings.daily_quota)
        self.state.cooldown_at[(req.gid, req.target)] = now

        total = float(record.get("kwh", 0.0))
        values = self._values(
            req,
            v=roll.volt,
            ah=roll.ah,
            kwh=kwh_text(roll.kwh),
            n=record.get("num", 0),
            total=kwh_text(total),
            fail=record.get("fail", 0),
            fee=fee_text(settings.fee(total)),
            combo=combo + 1,
        )

        if not result.ok:
            head = texts.render(texts.pick("over_cap", scope=req.gid), **values)
            tail = (
                f"「{values['target']}」共被电 {values['n']} 次，"
                f"其中 {values['fail']} 次失败，实际计量 {values['total']} 度。"
            )
            await self._write_log(req, roll, False, now)
            return Outcome(
                ok=False,
                reason=result.reason,
                text=head + "\n" + tail,
                main_text=head,
                stats_text=tail,
                roll=roll,
                target=req.target,
                total=total,
                fails=int(values["fail"]),
                count=int(values["n"]),
            )

        if req.self_zap:
            head = texts.render(texts.pick("self", scope=req.gid), **values)
        else:
            head = texts.render(texts.pick_tier(roll.tier, scope=req.gid), **values)

        parts = [head]
        if combo + 1 >= 2:
            parts.append(texts.render(texts.pick("combo", scope=req.gid), **values))
        if roll.crit:
            parts.append(texts.render(texts.pick("crit", scope=req.gid), **values))
        main_text = "\n".join(parts)
        stats_text = (
            f"「{values['target']}」第 {values['n']} 次受电，累计 {values['total']} 度"
            f"（约 {values['fee']} 元），失败 {values['fail']} 次。"
        )

        await self._write_log(req, roll, result.ok, now)

        return Outcome(
            ok=True,
            reason=result.reason,
            text=main_text + "\n" + stats_text,
            main_text=main_text,
            stats_text=stats_text,
            roll=roll,
            target=req.target,
            kwh=roll.kwh,
            total=total,
            fails=int(values["fail"]),
            count=int(values["n"]),
            extra={"tier": roll.tier},
        )

    async def _write_log(self, req: ZapRequest, roll: Roll, ok: bool, now: float) -> None:
        if not self.settings.is_log or self.log is None:
            return
        await self.log.append(
            {
                "ts": round(now, 3),
                "gid": req.gid,
                "actor": req.actor,
                "target": req.target,
                "v": roll.volt,
                "ah": roll.ah,
                "kwh": roll.kwh,
                "tier": roll.tier,
                "crit": roll.crit,
                "combo": roll.combo,
                "result": "ok" if ok else "fail",
                "date": today_str(now),
            }
        )
