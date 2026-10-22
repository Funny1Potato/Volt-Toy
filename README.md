# Volt-Toy

群聊电击玩具。**v0.1 只做手动电**：群友互相电、电自己，记录次数、失败次数与度数，配一套「供电局」口吻的文案。图片检测留了挂点，暂不实现。

## 目录

```
volt_toy_core/              框架无关内核（纯标准库）
  model.py                  三步抽样：档位 → 能量 → 拆电压/电量
  records.py                受电账本：成功/失败/峰值/首电
  texts.py                  文案池与严格渲染
  storage.py                原子写 JSON 账本 + JSONL 日志
  state.py                  热状态：冷却/连击/额度/跳闸
  service.py                编排：校验 → 抽取 → 记账 → 文案
  rankings.py               榜单聚合
  settings.py               参数默认值
nonebot_plugin_volt_toy/    nonebot2 适配（Alconna + Uninfo + localstore）
  config.py                 pydantic 配置（volt_* 字段）
  runtime.py                配置/状态/服务单例
  store.py                  localstore 数据文件
  platform.py               跨协议会话：群 key / 名字 / 管理员 / 头像
  commands.py               Alconna 指令
astrbot_plugin_volt_toy/    AstrBot 适配（未开始，见其 README）
tests/                      内核单测
doc/Agent_notes.md          开发笔记：决策、风险、待验证项
```

## 快速开始（nonebot2）

```bash
pip install -e .
```

在 bot 里加载插件：

```python
nonebot.load_plugin("nonebot_plugin_volt_toy")
```

依赖：`nonebot-plugin-alconna`（多协议指令解析）、`nonebot-plugin-uninfo`（跨协议会话信息）、`nonebot-plugin-localstore`（数据目录）。三个都会在插件加载时用 `require()` 声明。

## 命令

| 命令 | 别名 | 说明 |
| --- | --- | --- |
| `zap [@目标] [理由]` | `电` `电击` `雷` | 施电；不 @ 则电自己（0.8 倍） |
| `zapkwh` | `度数榜` `电费榜` | 累计度数 TOP5 |
| `zaptop` | `被电榜` | 受电次数 TOP5（括号标失败数） |
| `zapmax` | `峰值榜` | 单次最高度数 TOP5 |
| `zapking` | `电王榜` | 成功施电次数 + 首电 × 2 |
| `zapinfo [@目标]` | `电档` | 总次数 / 失败次数 / 今日 / 累计度 |
| `zapclear [@目标]` | — | 清除记录（管理员） |
| `zapnodo [@目标]` | `绝缘` | 免电名单开关（管理员） |
| `zapon` / `zapoff` | — | 群内启停（管理员） |

## 规则

- 单目标每日上限 **25 次**：超出不拒绝，只记次数与失败，不加电量。
- 过载：**60 秒内 10 次** → 跳闸 **300 秒**。
- 每日施电额度默认 **不限**（`0`）；冷却默认 **关闭**（`0`）。
- 统计口径：**度（kWh）**；单次同时展示电压 V 与电量 Ah。
- 电自己：0.8 倍效率，不额外占额度。

## 配置

字段名转大写下划线即环境变量，例如 `VOLT_RECEIVE_CAP=25`。

| 字段 | 默认 | 说明 |
| --- | --- | --- |
| `volt_receive_cap` | 25 | 单目标每日受电上限，0 不限 |
| `volt_overload_window` | 60 | 过载窗口（秒） |
| `volt_overload_threshold` | 10 | 窗口内最多施电次数 |
| `volt_overload_ban` | 300 | 跳闸时长（秒） |
| `volt_daily_quota` | 0 | 每日施电额度，0 不限 |
| `volt_cooldown` | 0 | 同目标冷却秒数，0 关闭 |
| `volt_crit_prob` | 0.15 | 暴击概率 |
| `volt_self_efficiency` | 0.8 | 电自己的效率 |
| `volt_price_per_kwh` | 0.55 | 电价，仅影响展示 |
| `volt_is_log` | false | 写逐条日志 |
| `volt_whitelist` | `[]` | 免电名单初始值 |

## 数据

放在 localstore 插件数据目录：

- `zap.json` —— 群用电账本（原子写）
- `zap_log.jsonl` —— 逐条审计（`VOLT_IS_LOG=true` 时）
- `zap_whitelist.json` —— 免电名单

## 开发

```bash
pip install -e ".[dev]"
pytest
```

当前环境未跑过测试（本机 Python 环境临时故障），见 `doc/Agent_notes.md` 的待验证清单。

## 免责

这是熟人局玩具，不涉及任何真实惩罚。请勿用于骚扰陌生人。
