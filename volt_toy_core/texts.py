"""文案池：一个场景一个池，随机取、最近三条去重、占位符严格渲染。"""

from __future__ import annotations

import random
import string
from collections import deque

TIER_TEXTS: dict[str, tuple[str, ...]] = {
    "静电": (
        "{actor} 递过去一个带电的门把手，{target} 指尖一麻，电表连一档都没跳。",
        "{actor} 蹭了蹭毛衣，给 {target} 来了 {v}V 的一下，{ah}Ah，约合手机充电的百分之一。",
        "值班室记录：{actor} 对 {target} 实施静电问候一次，功率不大，侮辱性极强。",
        "{target} 被电了 {v}V，反应是「啊」了半声，然后假装无事发生。",
        "这一下只有 {kwh} 度，{target} 甚至没抬头，{actor} 的尊严比电表先归零。",
        "{actor} 调了半天设备，最后输出 {v}V。{target} 说这是被蚊子叮了一下。",
        "{target} 被电完查了下电费，{kwh} 度，四舍五入等于没花钱。",
        "供电局回复：本次为静电级别，不予立案，建议 {actor} 先把地线接好。",
    ),
    "家用": (
        "{actor} 给 {target} 接上市电，{v}V，{kwh} 度——够电饭煲保温一小时。",
        "{target} 被电得踉跄两步，扶住了桌角，那是全场唯一还稳的东西。",
        "{actor} 一拉闸，{target} 头顶的灯闪了三下，人和灯一起暗了半秒。",
        "抄表员记了一笔：{actor} 在 {target} 身上用掉 {kwh} 度，电费记在施电方名下。",
        "{target} 被电完沉默两秒，说「还行」。{actor} 觉得这两秒里他想了很多。",
        "{actor} 出手很稳，{v}V 不多不少，{kwh} 度刚好够 {target} 把嘴里的水喷出来。",
        "线路正常，{kwh} 度。{target} 的惨叫符合家用电器标准。",
        "{target} 事后表示有点麻但能接受。{actor} 表示那正好，一度电还没用完。",
    ),
    "工业": (
        "三相电接通。{actor} 把 {target} 送上 380V 的工位，{ah}Ah，{kwh} 度，够洗衣机转完一桶。",
        "{target} 抖得整条手臂都在响，{actor} 在旁边记数据：{v}V，{kwh} 度，表现良好。",
        "{actor} 推上车间总闸，{target} 的椅子原地转了半圈，人还坐着，魂已经下班了。",
        "{v}V。{target} 的头发彻底站起来，像刚被雷劈过的蒲公英，这一下 {kwh} 度。",
        "{target} 事后说，那一刻他看见了小时候的院子。{actor} 说下次带他去，反正 {kwh} 度也不贵。",
        "工业级放电。{target} 被电出重影，群里同时出现两个他，其中一个在道歉。",
        "{target} 说不出话，{actor} 顺手把电费截图发了出来：{kwh} 度，请查收。",
        "车间主任远远看了一眼：{v}V 打在人身上还能站着，这个月给他加钱。",
    ),
    "高压": (
        "{actor} 把 {target} 接上高压线，{v}V，{ah}Ah，{kwh} 度——够空调开小半天。",
        "高压放电。{target} 从椅子上弹起来，落地时还保持着坐姿。",
        "{actor} 推上闸刀，{target} 整个人亮了一下，像被按了截图键，电表狂转 {kwh} 度。",
        "{target} 被电得失语，只剩手指在抽。{actor} 看了眼读数：{kwh} 度，没超载。",
        "供电局紧急通告：{actor} 在 {target} 身上做了一次未报备的高压实验。",
        "{v}V 下去，{target} 的影子都抖了一下。{actor} 称之为物理点名，耗电 {kwh} 度。",
        "{target} 现在对 {actor} 的任何动作都有应激反应，包括递水。",
        "高压档。{target} 的瞳孔收缩了三次，{actor} 的记录本上又添一行 {kwh} 度。",
    ),
    "雷击": (
        "雷击。{actor} 这一下 {kwh} 度，够给电动车充满一次，{target} 被焊在原地。",
        "{v}V / {ah}Ah / {kwh} 度。{target} 从群里消失两分钟，回来时名字后面带着焦味。",
        "这不是电击，是天罚。{target} 抬头看天，发现天上只有 {actor} 在笑。",
        "{actor} 的 {kwh} 度让全群的灯暗了一下，{target} 是唯一还亮着的物体。",
        "雷击级别。{target} 的头发、眉毛，以及刚建立的自信心，一起没了。",
        "群安静了四秒。第五秒，{actor} 发了句「手滑」。",
        "供电局连夜开会：{actor} 在 {target} 身上复现了雷暴，耗电 {kwh} 度，超出本群经营范围。",
        "{target} 被电到只剩一个轮廓。{actor} 补充：{v}V，还有提升空间，电费回头再算。",
    ),
}

POOLS: dict[str, tuple[str, ...]] = {
    "combo": (
        "连击，电表开始发烫。",
        "又是同一个目标，线路已经开始发热。",
        "这一下接得很快，快到没人反应过来。",
        "电表已经懒得跳了。",
        "熟练得让人心疼。",
        "节奏起来了。",
        "群里已经有人在数了。",
        "第二下比第一下还要顺手。",
    ),
    "crit": (
        "暴击，档位直接往上跳了一级。",
        "追加判定通过，这一下翻档。",
        "手抖了一下，运气来了。",
        "表盘多转了一圈，谁也没料到。",
        "风机跟着起哄。",
        "设备过载，没来得及收手。",
    ),
    "self": (
        "{actor} 把插头插进了自己身上，{v}V，{kwh} 度。没人拦，因为没人想拦。",
        "{actor} 对自己下手，0.8 倍效率。供电局称之为自我批评。",
        "{actor} 对着镜子按下开关，{kwh} 度，镜子里的人比他还惊讶。",
        "自罚成功。{actor} 终于明白为什么没人电自己。",
        "{actor} 把电自己当成了打卡，今天第 {n} 次，累计 {total} 度。",
    ),
    "over_cap": (
        "{target} 今天已经被电了 {cap} 次，电表封顶。这一下只记次数，记为失败。",
        "{target} 的电量已满，{actor} 这一下空转，计为一次失败记录。",
        "超过单日上限。{target} 没有再掉一滴电，{actor} 的记录上多了一次失败。",
        "{target} 已经焦了，这一下不计电量，只记一次失败——供电局称之为无效作业。",
        "上限已满，{actor} 的插头插进去，电表纹丝不动。本次记为失败。",
    ),
    "immune": (
        "{target} 是绝缘体，电不进去。这是名单，不是建议。",
        "供电局为 {target} 贴了封条：本户不参与本群用电业务。",
        "{target} 全身包了绝缘胶，{actor} 白忙一场，电表一格没走。",
        "名单上的人不导电，{actor} 的插头插在了空气里。",
        "你可以电任何人，除了 {target}。这不是能力问题，是规则。",
    ),
    "overload": (
        "你已经连续电了太多次，总闸跳了，{m} 分 {s} 秒后恢复供电。",
        "供电局拉黑了你的电表：60 秒内 10 次，属于违规用电。",
        "跳闸。{actor} 摸黑站在原地，第一次体会到「没电」的分量。",
        "你被拉闸了。冷静期 {m} 分 {s} 秒，请勿拍打电表。",
        "值班室挂上了你的名字，理由是「用电过于热情」。",
    ),
    "quota": (
        "你的用电额度用完了（{used}/{quota}），供电局建议你明天再发作。",
        "今日额度清零。{actor} 举着插头站在墙边，第一次感到电是有限的。",
        "额度用完。你可以选择理性，也可以明天再来。",
    ),
    "cooldown": (
        "{target} 还在冒烟，{s} 秒后才能再电。",
        "线路保护中，{target} 需要 {s} 秒冷却。你等得起，他未必。",
        "{target} 刚被电过，保险丝还没换回来，再等 {s} 秒。",
        "别急，{target} 现在处于「人还在，魂未归」的状态，{s} 秒后再说。",
    ),
    "bot": (
        "你电了机器人。它沉默一秒，把你列进了今天的检修名单。",
        "{actor} 把插头对准机器人。机器人反问：「你确定？」",
        "机器人没有痛觉，但它有日志。{actor} 被记在了第 3 行。",
        "电流经过机器人，绕了一圈，从 {actor} 的鞋底回去了。",
    ),
    "empty": (
        "本群还没有人被电过。这是最后的和平。",
        "没有任何电流通过这里，安静得有点可疑。",
        "还没有人开过闸。供电局已经把电费单准备好了。",
    ),
    "clear": (
        "已清除 {name} 的全部用电记录，相关数据重新校准。从今天起他重新做人。",
        "{name} 的电表被摘了，历史归零，痛感保留。",
        "记录已删除。但群里记得，{actor} 也记得。",
    ),
}

RANK_TITLES: dict[str, str] = {
    "kwh": "度数榜 TOP{limit} · 本群用电巨头",
    "top": "被电榜 TOP{limit} · 谁最耐电",
    "max": "峰值榜 TOP{limit} · 谁一次性挨得最狠",
    "king": "电王榜 TOP{limit} · 谁最爱上手",
}

INFO_TEXT = (
    "{name}：共 {n} 次，其中 {fail} 次失败；今日 {day_n} 次（失败 {day_fail}）；"
    "实际计量 {total} 度，约 {fee} 元。"
)

MISSING_TEXT = "没有查到 {name} 的用电记录。"

_FORMATTER = string.Formatter()
_RECENT: dict[str, deque[str]] = {}


def render(template: str, **values: object) -> str:
    """严格渲染：模板里有而 values 里没有的占位符直接报错。"""
    missing = sorted(
        {field for _, field, _, _ in _FORMATTER.parse(template) if field and field not in values}
    )
    if missing:
        raise KeyError(f"文案缺少占位符: {', '.join(missing)}")
    return template.format(**values)


def pick(name: str, *, rng: random.Random | None = None, scope: str = "") -> str:
    """从池中取一条，跳过该作用域最近用过的三条。"""
    rng = rng or random
    if name in TIER_TEXTS:
        pool = TIER_TEXTS[name]
    else:
        pool = POOLS[name]
    if len(_RECENT) > 4096:
        _RECENT.clear()
    key = f"{scope}:{name}"
    recent = _RECENT.setdefault(key, deque(maxlen=3))
    candidates = [item for item in pool if item not in recent]
    if not candidates:
        candidates = list(pool)
    chosen = rng.choice(candidates)
    recent.append(chosen)
    return chosen


def pick_tier(tier: str, *, rng: random.Random | None = None, scope: str = "") -> str:
    return pick(tier, rng=rng, scope=scope)


def reset_recent() -> None:
    """测试用：清空去重历史。"""
    _RECENT.clear()
