<div align="center">

# ⚡ Volt-Toy 电击群友 ⚡

用指令电群友的群聊玩具：电压、电量、度数记账，带连击、暴击与供电局文案。

<p>
    <img src="https://img.shields.io/badge/python-3.12+-blue?style=flat-square&logo=python&logoColor=white" alt="python">
    <img src="https://img.shields.io/badge/nonebot-2.5+-red?style=flat-square" alt="nonebot">
    <img src="https://img.shields.io/badge/AstrBot-4.5%2B-6f42c1?style=flat-square" alt="astrbot">
    <img src="https://img.shields.io/badge/license-MIT-green?style=flat-square" alt="license">
</p>

</div>

## 📖 介绍

群里发一句 `/电 @某人`，对方就被电一下：一次同时掷出电压（V）与电量（Ah），按 **度（kWh）** 累计，顺手折算电费。被电的人有次数、失败数、单次峰值与总用电量，群里有四张榜单。

- **一次电击三个数**：电压、电量、功率；统计只认度数
- **档位**：静电 → 家用 → 工业 → 高压 → 雷击，连击与暴击会升档
- **风控**：单目标每日上限、施电过载跳闸、免电名单、群内启停
- **失败也记账**：超出每日上限不拒绝，只记一次「失败」，电量不再增加
- **两套框架**：NoneBot2 与 AstrBot 共用同一份数据格式与文案

## 💿 安装

<details>
<summary>NoneBot2 · nb-cli（未上架 NoneBot 商店，可先用下面的包管理器安装）</summary>

```bash
nb plugin install nonebot-plugin-volt-toy
```

依赖 `nonebot-plugin-alconna`、`nonebot-plugin-uninfo`、`nonebot-plugin-localstore`，会随插件自动安装。

</details>

<details>
<summary>NoneBot2 · 包管理器</summary>

```bash
pip install nonebot-plugin-volt-toy
```

在 `pyproject.toml` 中确认插件已启用：

```toml
[tool.nonebot]
plugins = ["nonebot_plugin_volt_toy"]
```

依赖 `nonebot-plugin-alconna`、`nonebot-plugin-uninfo`、`nonebot-plugin-localstore`，会随插件自动安装。

</details>

<details>
<summary>AstrBot</summary>

仓库根目录同时是 AstrBot 插件。二选一：

- 在 AstrBot WebUI 的插件市场搜索安装（还未上架）
- 或把仓库克隆到 `data/plugins/`：

```bash
cd AstrBot/data/plugins
git clone https://github.com/Funny1Potato/Volt-Toy
```

无需额外安装依赖，内核随仓库提供。

</details>

## 🎉 使用

| 指令 | 别名 | 说明 |
| --- | --- | --- |
| `zap [@目标]` | `电` `电击` `雷` | 电目标；不 @ 则电自己（0.8 倍） |
| `zapkwh` | `度数榜` `电费榜` | 累计度数 TOP5，附折算电费 |
| `zaptop` | `被电榜` | 被电次数 TOP5，括号里是失败数 |
| `zapmax` | `峰值榜` | 单次最高度数 TOP5 |
| `zapking` | `电王榜` | 施电次数 + 首电加权 |
| `zapinfo [@目标]` | `电档` | 个人用电档案 |
| `zapclear [@目标]` | — | 清除记录（管理员） |
| `zapnodo [@目标]` | `绝缘` | 免电名单开关（管理员） |
| `zapon` / `zapoff` | — | 群内启停（管理员） |

NoneBot 默认只响应 `/` 开头的消息；AstrBot 的前缀以它自己的配置为准。

> 电击是群里的虚拟玩法，数值与电费都是文案效果，不涉及任何真实惩罚。

## ⚙️ 配置

NoneBot 在 `.env` 或 `.env.prod` 中配置（均可选，默认值即可开箱使用）；AstrBot 在 WebUI 的插件配置页调整，字段一一对应。

```env
VOLT_RECEIVE_CAP=25        # 单目标每日受电上限，0 = 不限；超出只记失败不加电量
VOLT_OVERLOAD_WINDOW=60    # 过载统计窗口（秒）
VOLT_OVERLOAD_THRESHOLD=10 # 窗口内最多施电次数，达到即跳闸
VOLT_OVERLOAD_BAN=300      # 跳闸时长（秒）

VOLT_DAILY_QUOTA=0         # 每日施电额度，0 = 不限
VOLT_COOLDOWN=0            # 同一目标冷却秒数，0 = 关闭

VOLT_CRIT_PROB=0.15        # 暴击概率
VOLT_SELF_EFFICIENCY=0.8   # 电自己的效率倍率
VOLT_PRICE_PER_KWH=0.55    # 电价（元/度），只影响展示

VOLT_IS_LOG=false          # 是否写逐条审计日志
VOLT_GROUP_DEFAULT=true    # 新群默认启用
VOLT_WHITELIST=[]          # 免电名单初始值
VOLT_SHOW_AVATAR=true      # 成功施电后附被电者头像（仅 QQ 系平台）
```

### 档位与数值

| 档位 | 度数 | 电压 | 大致相当于 |
| --- | --- | --- | --- |
| 静电 | 0.01–0.05 | 120–180V | 手机充电 1% |
| 家用 | 0.05–0.15 | 180–240V | 电饭煲保温一小时 |
| 工业 | 0.15–0.35 | 240–380V | 洗衣机洗一桶 |
| 高压 | 0.35–0.80 | 380–800V | 空调开一小时 |
| 雷击 | 0.80–2.60 | 800–1000V | 电动车充满一次 |

同一目标 10 分钟内连续受电会累积连击并升档；暴击再升一档，最高到雷击。

## 🗃 数据

| 文件 | 内容 |
| --- | --- |
| `zap.json` | 群用电账本（原子写） |
| `zap_log.jsonl` | 逐条审计日志（`VOLT_IS_LOG=true` 时） |
| `zap_whitelist.json` | 免电名单 |

NoneBot 存于 localstore 插件数据目录，AstrBot 存于 `data/plugin_data/astrbot_plugin_volt_toy/`。两边格式一致，可对拷迁移。

## 💡 说明

- 电自己按 0.8 倍结算，且不占每日额度。
- 榜单只统计成功施电；失败记录保留在账本与日志里，不进电王榜。

## 📄 许可

MIT © [Funny1Potato](https://github.com/Funny1Potato)
