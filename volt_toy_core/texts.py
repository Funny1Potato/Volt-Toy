"""文案池：一个场景一个池，随机取、最近三条去重、占位符严格渲染。

约定：
- 档位主句、状态、清档等池子每条至少带一个数据占位符；
- 连击 / 暴击是附加句，只跟在主句后面，不带占位符（数据由主句负责）。
"""

from __future__ import annotations

import random
import string
from collections import deque

TIER_TEXTS: dict[str, tuple[str, ...]] = {
    "静电": (
        "{actor} 只是碰了下门把手，{target} 就被 {v}V 的静电弹了一下，电表连一档都没跳。",
        "供电局通报：{actor} 对 {target} 实施静电问候一次，{v}V、{kwh} 度，功率不大，伤害性极强。",
        "{target} 挨了 {v}V，{ah}Ah 从指尖过了一遍，反应是「啊」了半声，然后假装无事发生。",
        "这一下只有 {kwh} 度，约合手机充电的百分之一；{target} 没抬头，{actor} 的尊严先归零。",
        "{actor} 蹭了半天毛衣，最后输出 {v}V；{target} 说这是被蚊子叮了，要求赔偿。",
        "抄表员路过看了一眼：{kwh} 度，表盘都没转完一圈，{target} 表示拒绝配合调查。",
        "{target} 被 {actor} 电了 {v}V、{ah}Ah，医学上叫静电，社交上叫冒犯。",
        "值班室回复：本次 {v}V / {kwh} 度，属静电级别，不予立案，建议 {actor} 先把地线接好。",
        "{actor} 认真调了半小时设备，最后输出 {v}V；{target} 的评价是「不如蚊子」。",
        "电压 {v}V、电量 {ah}Ah，功率低到 {target} 以为是自己静电了 {actor}。",
    ),
    "家用": (
        "{actor} 给 {target} 接上市电，{v}V、{kwh} 度，刚好够电饭煲保温一小时。",
        "{target} 被 {v}V 电得踉跄两步，扶住桌角——那是全场唯一还稳的东西，{ah}Ah 已经过身。",
        "{actor} 一拉闸，{target} 头顶的灯闪了三下，人和灯一起暗了半秒，这次用了 {kwh} 度。",
        "抄表员记了一笔：{actor} 在 {target} 身上用掉 {kwh} 度，电费记在施电方名下，{target} 提出异议。",
        "{target} 被 {kwh} 度电完沉默两秒，说了句「还行」；{actor} 觉得这两秒里他想了很多。",
        "{actor} 出手很稳，{v}V 不多不少，{kwh} 度刚好够 {target} 把嘴里的水喷出来。",
        "线路正常，{v}V / {kwh} 度；{target} 的惨叫符合家用电器标准，邻居表示理解。",
        "{target} 事后说有点麻但能接受，{actor} 说那正好，{kwh} 度还没到阶梯电价。",
        "这一下 {kwh} 度，折合 {fee} 元，{target} 说这是他本月最不值的一笔支出。",
        "{actor} 把 {v}V 的插头递过去，{target} 接得很快，{kwh} 度就这样没了。",
    ),
    "工业": (
        "三相电接通：{actor} 把 {target} 送上 380V 工位，{ah}Ah、{kwh} 度，够洗衣机转完一桶。",
        "{target} 抖得整条手臂都在响，{actor} 在旁边记数据：{v}V、{kwh} 度，表现良好。",
        "{actor} 推上车间总闸，{target} 的椅子转了半圈，人还坐着，魂已经下班，耗电 {kwh} 度。",
        "{v}V、{kwh} 度。{target} 的头发彻底站起来，像刚被雷劈过的蒲公英。",
        "{target} 事后说，那一刻他看见了小时候的院子；{actor} 说下次带他去，反正 {kwh} 度不贵。",
        "工业级放电，{kwh} 度。{target} 被电出重影，群里同时出现两个他，其中一个在道歉。",
        "{target} 说不出话，{actor} 顺手把电费截图发出来：{kwh} 度，约 {fee} 元，请查收。",
        "车间主任远远看了一眼：{v}V 打在人身上还能站着，这个月给他加钱，电费走公账。",
    ),
    "高压": (
        "{actor} 把 {target} 接上高压线，{v}V、{ah}Ah、{kwh} 度——够空调开小半天。",
        "高压放电：{target} 从椅子上弹起来，落地时还保持着坐姿，这一次 {kwh} 度。",
        "{actor} 推上闸刀，{target} 整个人亮了一下，像被按了截图键，电表狂转 {kwh} 度。",
        "{target} 被 {v}V 电得失语，只剩手指在抽；{actor} 看了眼读数：{kwh} 度，没超载。",
        "供电局紧急通告：{actor} 在 {target} 身上做了一次未报备的高压实验，峰值 {v}V。",
        "{v}V 下去，{target} 的影子都抖了一下；{actor} 称之为物理点名，耗电 {kwh} 度。",
        "{target} 现在对 {actor} 的任何动作都有应激反应，包括递水——上次 {kwh} 度的后遗症。",
        "高压档，{kwh} 度。{target} 的瞳孔收缩了三次，{actor} 的记录本上又添一行。",
    ),
    "雷击": (
        "雷击：{actor} 这一下 {kwh} 度，够给电动车充满一次，{target} 被焊在原地。",
        "{v}V / {ah}Ah / {kwh} 度。{target} 从群里消失两分钟，回来时名字后面带着焦味。",
        "这不是电击，是天罚——{kwh} 度。{target} 抬头看天，发现天上只有 {actor} 在笑。",
        "{actor} 的 {kwh} 度让全群的灯暗了一下，{target} 是唯一还亮着的物体。",
        "雷击级别，{v}V。{target} 的头发、眉毛以及刚建立的自信心，一起没了。",
        "群安静了四秒。第五秒 {actor} 发了句「手滑」，此时 {target} 已经吃了 {kwh} 度。",
        "供电局连夜开会：{actor} 在 {target} 身上复现了雷暴，{kwh} 度，超出本群经营范围。",
        "{target} 被电到只剩一个轮廓，{v}V / {kwh} 度；{actor} 补充：还有提升空间，电费回头算。",
    ),
}

POOLS: dict[str, tuple[str, ...]] = {
    # 附加句：跟在主句后面，不带占位符
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
        "{actor} 把插头插进了自己身上，{v}V、{kwh} 度。没人拦，因为没人想拦。",
        "{actor} 对自己下手，0.8 倍效率，{kwh} 度。供电局称之为自我批评。",
        "{actor} 对着镜子按下开关，{kwh} 度，镜子里的人比他还惊讶。",
        "自罚成功，{kwh} 度。{actor} 终于明白为什么没人电自己。",
        "{actor} 把电自己当成打卡，今天第 {n} 次，累计 {total} 度，{v}V 一次没落。",
        "{actor} 电完自己，表情平静得像刚喝了口水；电表显示 {kwh} 度，比上次少。",
    ),
    "over_cap": (
        "{target} 今天已被电 {cap} 次，电表封顶；这一下只记次数，{n} 次里再多一次失败。",
        "{target} 的电量已满（{total} 度），{actor} 这一下空转，计为一次失败记录。",
        "超过单日上限 {cap} 次：{target} 没再掉一滴电，{actor} 的记录上多了一次失败。",
        "{target} 已经焦了，{total} 度封顶；这一下不计电量，只记一次失败，供电局称之为无效作业。",
        "上限已满，{actor} 的插头插进去，电表纹丝不动——{cap} 次用尽，本次记为失败。",
        "第 {n} 次受电、第 {fail} 次失败：{target} 的电表已经不允许再进一寸。",
    ),
    "immune": (
        "{target} 是绝缘体，电不进去；单日 {cap} 次的受电上限，与 ta 无关。",
        "供电局为 {target} 贴了封条：本户不参与本群 {cap} 次/日的用电业务。",
        "{target} 全身包了绝缘胶，{actor} 白忙一场，电表停在 0.00 度。",
        "名单上的人不导电——{actor} 的插头连 0.01 度都没送进去。",
        "你可以电任何人，除了 {target}；这是规则，不是那 {cap} 次额度的问题。",
        "{target} 今天有保护令，{actor} 的电压全部落在了空气里，读数 0.00。",
    ),
    "overload": (
        "你已经连续电了太多次，总闸跳了，{m} 分 {s} 秒后恢复供电。",
        "供电局拉黑了你的电表：60 秒内 10 次，违规用电，{m} 分 {s} 秒后再说。",
        "跳闸，剩余 {m} 分 {s} 秒。{actor} 摸黑站在原地，第一次体会到没电的分量。",
        "你被拉闸了，冷静期 {m} 分 {s} 秒，请勿拍打电表。",
        "值班室挂上了你的名字，理由是用电过于热情，{m} 分 {s} 秒后自动销案。",
        "总闸替你做了决定：{m} 分 {s} 秒内，这个群没有你的电。",
    ),
    "quota": (
        "你的用电额度用完了（{used}/{quota}），供电局建议你明天再发作。",
        "今日 {quota} 次额度清零，{actor} 举着插头站在墙边，第一次感到电是有限的。",
        "{used}/{quota}，额度用完；你可以选择理性，也可以等明天。",
        "抄表员合上本子：今天的 {quota} 次已经用尽，再电就是偷电了。",
    ),
    "cooldown": (
        "{target} 还在冒烟，{s} 秒后才能再电。",
        "线路保护中，{target} 需要 {s} 秒冷却；你等得起，他未必。",
        "{target} 刚被电过，保险丝还没换回来，再等 {s} 秒。",
        "别急，{target} 现在处于「人还在，魂未归」的状态，{s} 秒后再说。",
        "冷却还剩 {s} 秒；{actor} 的插头已经在空气里举了半天。",
    ),
    "bot": (
        "你电了机器人。它额定功率 5W，把你的电流原路退回，顺便把你列进了检修名单。",
        "{actor} 把插头对准机器人，机器人反问：「你确定？我这边记着 0.0001 度的账。」",
        "机器人没有痛觉，但它有日志：{actor} 被记在了第 3 行，时间精确到毫秒。",
        "电流经过机器人，绕了一圈，从 {actor} 的鞋底回去了，损耗 0%。",
        "机器人沉默 2 秒，回复了一句「已记录」，{actor} 开始后悔。",
    ),
    "empty": (
        "本群还没有人被电过，累计 0 度，这是最后的和平。",
        "没有任何电流通过这里，电表读数停在 0.00，安静得有点可疑。",
        "还没有人开过闸，供电局的电费单上写着 0 元。",
        "榜首暂时空缺，0 次、0 度，谁先来谁就是历史第一。",
    ),
    "clear": (
        "已清除 {name} 的全部用电记录：{n} 次、{total} 度归零，相关数据重新校准。",
        "{name} 的电表被摘了，{n} 次历史与 {total} 度一起清零，痛感保留。",
        "{name} 的 {total} 度用电史已删除；{actor} 说，群里记得就行。",
        "记录已删除，{n} 次受电、{total} 度电量不再计入榜单，从今天起重新做人。",
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

MISSING_TEXT = "没有查到 {name} 的用电记录；电表读数 0 度，可能只是还没被想起来。"

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
