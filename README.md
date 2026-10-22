# Volt-Toy

群聊电击玩具。**v0.1 只做手动电**：群友互相电、电自己，记录次数、失败次数与度数，配一套「供电局」口吻的文案。图片检测留了挂点，暂不实现。

## 目录

```
main.py                     AstrBot 适配入口（仓库根目录即 AstrBot 插件目录）
metadata.yaml               AstrBot 插件元数据
_conf_schema.json           AstrBot 配置面板 Schema
volt_toy_core/              框架无关内核（纯标准库）
  model.py                  三步抽样：档位 → 能量 → 拆电压/电量
  records.py                受电账本：成功/失败/峰值/首电
  texts.py                  文案池与严格渲染
  storage.py                原子写 JSON 账本 + JSONL 日志
  state.py                  热状态：冷却/连击/额度/跳闸
  service.py                编排：校验 → 抽取 → 记账 → 文案
  rankings.py               榜单聚合
  render.py                 榜单/档案文本（两框架共用）
  settings.py               参数默认值
nonebot_plugin_volt_toy/    nonebot2 适配（Alconna + Uninfo + localstore）
  config.py                 pydantic 配置（volt_* 字段）
  runtime.py                配置/状态/服务单例
  store.py                  localstore 数据文件
  platform.py               跨协议会话：群 key / 名字 / 管理员 / 头像
  commands.py               Alconna 指令
tests/                      内核单测
doc/Agent_notes.md          开发笔记：决策、风险、待验证项
pyproject.toml              nonebot 插件发布用
```

## 快速开始（nonebot2）

```bash
pip install nonebot-plugin-volt-toy
# 或者从源码：
pip install .
```

在 bot 里加载插件：

```python
nonebot.load_plugin("nonebot_plugin_volt_toy")
```

依赖：`nonebot-plugin-alconna`（多协议指令解析）、`nonebot-plugin-uninfo`（跨协议会话信息）、`nonebot-plugin-localstore`（数据目录）。三个都会在插件加载时用 `require()` 声明。

## 快速开始（AstrBot）

整个仓库就是 AstrBot 插件：把它放到 AstrBot 的 `data/plugins/` 下，重载插件即可。`main.py` 与 `volt_toy_core` 同级，不需要额外安装依赖。

```bash
cd AstrBot/data/plugins
git clone https://github.com/Funny1Potato/Volt-Toy
```

配置项在 WebUI 的插件配置页中调整，由 `_conf_schema.json` 定义。

插件市场发布：仓库根目录已带 `metadata.yaml` 与 `main.py`，仓库体积约 50KB（远低于 16MB 上限），
可直接在 [AstrBot Cloud 发布页](https://cloud.astrbot.app/publish) 提交。
`metadata.yaml` 声明的支持平台是 QQ 系三个（aiocqhttp / qq_official / qq_official_webhook）；
文本指令在其它平台理论上可用，但未实测，故未声明。

## 命令

| 命令 | 别名 | 说明 |
| --- | --- | --- |
| `zap [@目标]` | `电` `电击` `雷` | 施电；不 @ 则电自己（0.8 倍） |
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

两边用同一套文件格式：

- `zap.json` —— 群用电账本（原子写）
- `zap_log.jsonl` —— 逐条审计（`volt_is_log` 为真时）
- `zap_whitelist.json` —— 免电名单

nonebot 版放在 localstore 插件数据目录；AstrBot 版放在 `data/plugin_data/<插件名>/`。
两边的账本可以直接对拷（群 key 的前缀不同，需要少量改名，见 `doc/Agent_notes.md`）。

## 开发

```bash
pip install -e ".[dev]"
pytest          # 32 个内核用例
```

冒烟测试需要真实的 nonebot 项目：把仓库根加进 `sys.path` 后
`nonebot.load_plugin("nonebot_plugin_volt_toy")` 即可（`/zap @某人` 实测通过）。
注意 **editable 安装的插件可能无法被 nonebot 识别**：PEP 660 的 finder 会绕过
nonebot 的 `PluginFinder`，模块因而没有 `__plugin__`。用普通安装、或把插件目录放进
`plugin_dirs`，或手动把仓库根加进 `sys.path`。

## 发布（PyPI）

版本号在 `nonebot_plugin_volt_toy/__init__.py` 的 `__version__`，打包用 hatchling：

```bash
python -m build        # 产出 dist/*.whl 与 dist/*.tar.gz
pip install dist/*.whl # 本地验证
```

推 `vX.Y.Z` tag 会触发 `.github/workflows/pypi-publish.yml`：校验 tag 与 `__version__`
一致、构建、检查 wheel 内容，再用 Trusted Publishing 上传（首次需在 PyPI 配一次 publisher）。

## 免责

这是熟人局玩具，不涉及任何真实惩罚。请勿用于骚扰陌生人。
