# Agent 笔记（开发事项）

> 写给后续接手的人 / 模型：这里的结论是**已定**的，别凭直觉改。改动前先看「已定死的设计」。

## 1. 目标与范围

- v0.1 **只做手动电击**：群友互相电、电自己；不接图片检测。
- 检测留了挂点：`ZapService.zap()` 接收 `ZapRequest`，将来自动检测只要构造
  `source="auto"` 的请求即可，规则与记账不用改。
- 双框架：nonebot2（优先）与 AstrBot（未开始），共用 `volt_toy_core`。

## 2. 仓库结构

```
Volt-Toy/
  volt_toy_core/            内核，纯标准库
    model.py                三步抽样
    records.py              账本字段与 apply_zap
    texts.py                文案池 + pick/render
    storage.py              JsonStore / JsonlLog / 名单读写
    state.py                热状态（冷却/连击/额度/跳闸/名单）
    service.py              编排：校验 → 抽取 → 记账 → 出文案
    rankings.py             榜单聚合
    settings.py             参数默认值
    fmt.py                  两位小数格式化
  nonebot_plugin_volt_toy/   nonebot 适配
    __init__.py             PluginMetadata + require
    config.py               pydantic Config（volt_* 字段）
    runtime.py              单例：config/settings/state/service
    store.py                localstore 路径 + JsonStore/JsonlLog
    platform.py             Uninfo 会话 → 群 key / 名字 / 管理员 / 头像
    commands.py             Alconna 指令
  astrbot_plugin_volt_toy/  AstrBot 适配（仅 README，未实现）
  tests/                    内核单测
  conftest.py               让 tests 直接 import 内核
  pyproject.toml            发布用（含 [tool.nonebot]）
  doc/Agent_notes.md        本文件
```

## 3. 已定死的设计

### 数值

- 单次同时掷 **电压 V** 与 **电量 Ah**，**统计只记度（kWh）**。
- 三步抽样：抽档位 → 档内对数均匀抽能量 E → `V` 在档位电压带取值，`Ah = E×1000/V`。
- 连击每满 2 次升一档，暴击升一档，最高雷击；**不要**改回「能量翻倍」。
- 电自己 0.8 倍，最后一步打折（先抽完再乘）。
- 舍入只在返回前做一次；`|V·Ah/1000 − kWh| ≤ 0.02` 是硬约束。

| 档位 | 权重 | 度 | 电压 |
| --- | --- | --- | --- |
| 静电 | 40 | 0.01–0.05 | 120–180 |
| 家用 | 30 | 0.05–0.15 | 180–240 |
| 工业 | 18 | 0.15–0.35 | 240–380 |
| 高压 | 9 | 0.35–0.80 | 380–800 |
| 雷击 | 3 | 0.80–2.60 | 800–1000 |

### 规则

- 单目标每日上限 25 次：**不拦截**，超出的记 `num+1 / fail+1`，**不加电量**。
- 过载：60 秒内 10 次 → 跳闸 300 秒（硬拦截）。
- 每日额度默认 0（不限）；冷却默认 0（关闭）。两者 >0 才生效。
- 失败不计入电王榜，也不更新峰值。
- 没有 zapme：zap 不带目标就是电自己。

### 文案

- 「供电局」世界观：值班室、抄表员、跳闸、电费单。
- 一场景一池，`texts.pick()` 带最近三条去重；`texts.render()` 严格校验占位符。
- 失败文案单独成池，不带电量占位符。
- 禁 emoji（代码里不要加，需要时做配置开关）。

## 4. 实现状态

- 内核：完成（含单测）。
- nonebot：完成首版，**未在真实环境跑过**（本机 Python 环境暂时故障）。
- AstrBot：未开始。

## 5. 环境恢复后要验证的事

1. `pip install -e .`（或 `nb plugin install` 本地安装）能拉起依赖。
2. `python -c "import nonebot_plugin_volt_toy"` 不报错。
3. 冒烟：`zap @某人`、`zap`、`zapkwh`、`zapinfo`、`zapnodo`。
4. `get_session(bot, event)` 字段确认：`session.scene_path`、`session.adapter`、
   `session.scene.id/type/is_private`、`session.member.role`（枚举取 `.name`）。
5. `At` 段字段：优先 `target`，其次 `qq`；显示名 `display`。
6. `UniMessage.image(raw=bytes)` 可用。
7. `nb plugin publish` 能通过元数据检查。

## 6. 已知风险 / 待办

- `session.adapter` 可能是对象而不是字符串；`platform._adapter_name` 已做兜底，
  但群 key 的稳定性依赖它，验证时要打印一次实际值。
- `At.display` 可能带 `@` 前缀，如出现脏名字，在 `_at_name` 里 lstrip。
- 命令的 `reason` 只能取一个词（Alconna 空格分词）。要支持整句需要 `MultiVar`
  或读原始文本，验证后再改。
- 群开关（`zapon/zapoff`）只在内存，重启回默认。
- 额度、冷却、跳闸也是内存态，重启清空——这是有意的，不写盘。
- 头像只对 QQ 系协议（onebot / qq）生效，其它协议静默跳过。
- 分发时 `volt_toy_core` 与插件打在同一个 wheel 里（`[tool.setuptools] packages`）。
  将来若要独立发布 `volt-toy-core`，需要把内核移出插件分发包并加依赖。
- `[tool.nonebot]` 里的 `upstream_url` 还是占位地址，发布前替换。

## 7. 与参考插件的关系

- `nonebot_plugin_ccb_plus`：数据/指令骨架的参考（localstore、白名单、过载、榜单）。
- `nonebot_plugin_rollpig_plus`：文案风格的参考（一场景一池、大量变体、去重取词）。
- 两者都在工作区里，只作参考，**不要**把它们的代码复制进来。

## 8. 常用命令

```bash
cd Volt-Toy
pip install -e .
pytest
```

## 9. 当前进度（2026-10-22）

- git 仓库已初始化（分支 `main`），首个提交 `feat: Volt-Toy 内核与 nonebot 适配首版`。
- 已用 `python -m compileall` 做过语法检查（通过），**未运行 pytest**：
  本机 Python 环境的 pip 安装不稳定，等环境恢复后再跑。
- 恢复后第一件事：`pip install -e ".[dev]"` → `pytest` → 再起一个 nonebot 测试 bot 冒烟。
- 环境里可用 `nb` CLI（1.4.1），可用它 `nb create` 建测试项目。

## 10. 发布前检查

- `pyproject.toml` 的 `[tool.nonebot]`：`plugins = ["nonebot_plugin_volt_toy"]`、
  `plugin_type = "application"`、`upstream_url` 换成真实仓库地址。
- `[tool.setuptools] packages` 同时打包了 `volt_toy_core`；如果之后要独立发布内核，
  需要拆包并把插件改成依赖 `volt-toy-core`。
- README 里的「未跑过测试」这句，测试通过后要删掉。

## 11. 与参考插件的规范对齐（nonebot_plugin_aigf_master）

按参考插件改过的地方，别再改回去：

1. **require 必须在任何相关 import 之前**，否则库先被普通 import，`require` 会判定它不是插件。
2. **`supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna", "nonebot_plugin_uninfo")`**，
   不要写 `None`（发布审核更认「声明了支持的适配器」）。
3. **配置类叫 `PluginConfig`，并在 config.py 里导出 `plugin_config = get_plugin_config(PluginConfig)`**；
   字段用 `Field(default, description=...)`，描述会进配置文档。
4. **Alconna 对象必须强引用**：alconna 规则只持弱引用，`on_alconna(Alconna(...))`
   可能被 GC，matcher 会静默失效。代码里用 `_cmd()` 收集到 `_ALCONNA_REFS`。
5. **会话解析不用 Uninfo 依赖注入，改用 `nonebot_plugin_uninfo.get_session(bot, event)`**，
   失败回落到 alconna `get_target(event, bot)`；会话键用 `适配器 slug:scene_path`。
6. **群管理角色是枚举**：`member.role.name.lower()`，直接 `str(role)` 会得到 `role.admin`。
7. 命令 matcher 显式给 `priority` / `block`。
