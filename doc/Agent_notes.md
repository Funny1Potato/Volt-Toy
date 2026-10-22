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

### 文案与回执顺序

- 回执固定为「被电文案 → 头像 → 统计行」：
  `Outcome.main_text`（档位 + 连击/暴击）→ 图片 → `Outcome.stats_text`（第 N 次/累计/失败）。
- 两个适配器都按这个顺序拼消息；取不到头像时才退回整段文本 `Outcome.text`。
- 连击、暴击是附加句：只跟在主句后，不单独发送、不带占位符（数据由主句负责）。
- 清档文案带 `{n}` / `{total}`，两个适配器都在清档前先读一次记录再传值。
- 不要为了省一条消息把统计行并回主文案，否则头像会跑到统计后面。


- 「供电局」世界观：值班室、抄表员、跳闸、电费单。
- 一场景一池，`texts.pick()` 带最近三条去重；`texts.render()` 严格校验占位符。
- 失败文案单独成池，不带电量占位符。
- 禁 emoji（代码里不要加，需要时做配置开关）。

## 4. 实现状态

- 内核：完成（含单测）。
- nonebot：完成首版，**未在真实环境跑过**（本机 Python 环境暂时故障）。
- AstrBot：未开始。

## 5. 验证状态（2026-10-22 实测）

已在 `test/` 的 nonebot 2.5.0 + onebot v11 + alconna 0.62.1 + uninfo 0.11.2 环境跑过：

- [x] 内核单测 32 个全过（`pytest`）。
- [x] 插件加载成功，注册 10 个 matcher。
- [x] 启动钩子跑通，账本落在 `data/nonebot_plugin_volt_toy/zap.json`。
- [x] 会话解析：`onebot11:617770183`，`role=ADMINISTRATOR/admin`，`is_admin` 为真。
- [x] `zap`（带 At / 不带 At 电自己）、四个榜单、`zapinfo`、`zapnodo` 输出正确。
- [x] 过载：连续 10 次后返回 `overload`。
- [x] Alconna 规则对 `/电 @x`、`/电`、`电 @x`、`/zap @x` 均返回 True。

没做的：

- [ ] `nb plugin publish` 的元数据检查（要真实仓库地址与 PyPI 凭据）。
- [ ] 真实连接 QQ 的收发（只做了事件级模拟，头像走的是 mock）。
- [ ] AstrBot 真机运行。

## 5.1 实测踩到的两个坑

1. **localstore 不能在导入期取路径**：`get_plugin_data_file()` 用调用栈推断插件，
   一旦模块不是以「插件」身份被导入（例如被别的 import finder 抢先解析），
   直接抛 `Cannot detect caller plugin`。已改成 startup 时 `store.resolve()`。
2. **`pip install -e` 的插件 load 不起来**：PEP 660 的 editable finder 在
   `PathFinder` 之后才命中，nonebot 的 `PluginFinder` 用 `PathFinder` 查不到模块，
   于是模块以普通 `SourceFileLoader` 导入、没有 `__plugin__`，报
   `Module ... is not loaded as a plugin`。用普通安装、`plugin_dirs` 或把仓库根
   塞进 `sys.path` 都正常。

## 5.2 已修：电机器人被当成电自己（0.1.1 反馈）

- 现象：`/电 @机器人` 回执是自罚文案。
- 原因分两层：OneBot 适配器在分发前会执行 `_check_at_me`，把开头的 @机器人
  **从 `event.message` 里删掉**并置 `to_me=True`；命令解析拿不到目标，
  `_resolve_target` 退回发送者，于是走 `self_zap`。此时再扫 `event.get_message()`
  已经看不到 At，只有 `event.original_message` 还留着。
- 修法：参数里没有目标时，只要 `(not 私聊) and event.is_tome()` 为真，
  就按「电机器人」处理；At 还在消息里的适配器另用 `mentioned_self()` 兜底。
- 注意：`mentioned_self()` 单独一项不够，Att 被适配器提前删除后就查不到了。
- AstrBot 版不走 alconna 的 to_me 处理，直接读消息链里的 At，本来就没有这个问题。

## 5.3 已防：插件与内核版本混装

- 现象：`AttributeError: 'Outcome' object has no attribute 'main_text'`。
- 原因：`nonebot_plugin_volt_toy` 是从仓库/旧目录加载的新代码，而 `volt_toy_core`
  来自 site-packages 里的旧版本（0.1.1 以前没有拆分字段）。两个包必须同版本。
- 修法：两个适配器改用 `getattr(outcome, "main_text", "")`，缺字段时退回整段文本并告警。
- 正确的开发姿势：装 wheel（`pip install .`）就不要另外复制插件目录；
  想改代码就重新 `pip install .`，别只复制其中一个包。

## 6. 已知风险 / 待办

- `session.adapter` 可能是对象而不是字符串；`platform._adapter_name` 已做兜底，
  但群 key 的稳定性依赖它，验证时要打印一次实际值。
- `At.display` 可能带 `@` 前缀，如出现脏名字，在 `_at_name` 里 lstrip。
- `zap` 不接收理由（已按决定移除）。要加回来必须先把「理由用来做什么」定清楚：
  回显 / 入账 / 影响数值，三者选一，否则它只是在日志里躺着。
- 群开关（`zapon/zapoff`）只在内存，重启回默认。
- 额度、冷却、跳闸也是内存态，重启清空——这是有意的，不写盘。
- 头像只对 QQ 系协议（onebot / qq）生效，其它协议静默跳过。
- 分发：用 hatchling 打包，`volt_toy_core` 与插件在同一个 wheel 里
  （`[tool.hatch.build.targets.wheel] packages`），`version` 取自
  `nonebot_plugin_volt_toy/__init__.py` 的 `__version__`。若将来要独立发布
  `volt-toy-core`，需要改成依赖并拆包。
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

## 9. 发布纪律（硬规则，先于一切）

**发版前必须先向用户确认，得到明确同意后才执行。** 「发版」包括但不限于：

- 修改 `__version__` / `pyproject` 版本号；
- `git tag vX.Y.Z` 并 push tag（会触发 PyPI 自动发布）；
- 手动 `twine upload` / `python -m build` 后上传；
- 向 AstrBot 插件市场提交或更新版本。

一次确认只覆盖当次版本，不默认延续到下个版本。改代码、文档、测试、提交（不 tag）不需要确认。
用户明确说「发版」「发布」时才可进入发布流程；拿不准就先问。

## 10. 发布与打包（2026-10-22 已发布）

**PyPI 已上线**：`nonebot-plugin-volt-toy` 0.1.0 / 0.1.1 均已通过 Trusted Publishing 发布，
0.1.1 起 PyPI 页面的 README 为面向用户的版本、author 为 Funny1Potato。

- 发布方式：推 `vX.Y.Z` tag → `.github/workflows/pypi-publish.yml`
- 实测：tag 工作流 success，`pip install nonebot-plugin-volt-toy==0.1.1` 后插件可加载、注册 10 个 matcher
- 版本号唯一来源：`nonebot_plugin_volt_toy/__init__.py` 的 `__version__`

### 打包细节

- `python -m build` 产出 sdist + wheel；两者都实测可 `pip install`。
- wheel 内容：`nonebot_plugin_volt_toy/` + `volt_toy_core/`，不含 `main.py`/`tests`/`doc`。
- `[tool.nonebot]` 保留，供商店发布/识别插件类型。

## 11. 当前进度（2026-10-22）

- git 仓库已初始化（分支 `main`），首个提交 `feat: Volt-Toy 内核与 nonebot 适配首版`。
- 已用 `python -m compileall` 做过语法检查（通过），**未运行 pytest**：
  本机 Python 环境的 pip 安装不稳定，等环境恢复后再跑。
- 恢复后第一件事：`pip install -e ".[dev]"` → `pytest` → 再起一个 nonebot 测试 bot 冒烟。
- 环境里可用 `nb` CLI（1.4.1），可用它 `nb create` 建测试项目。

## 12. 发布前检查

- `pyproject.toml` 的 `[tool.nonebot]`：`plugins = ["nonebot_plugin_volt_toy"]`、
  `plugin_type = "application"`、`upstream_url` 换成真实仓库地址。
- `[tool.setuptools] packages` 同时打包了 `volt_toy_core`；如果之后要独立发布内核，
  需要拆包并把插件改成依赖 `volt-toy-core`。
- README 里的「未跑过测试」这句，测试通过后要删掉。

## 13. 与参考插件的规范对齐（nonebot_plugin_aigf_master）

参考插件本身未完整测试过，以下结论以官方文档与源码为准（2026-10 核对）：

1. **require 必须在任何相关 import 之前**，否则库先被普通 import，`require` 会判定它不是插件。
2. **`supported_adapters=inherit_supported_adapters("nonebot_plugin_alconna", "nonebot_plugin_uninfo")`**，
   不要写 `None`。
3. **配置类叫 `PluginConfig`，并在 config.py 里导出 `plugin_config = get_plugin_config(PluginConfig)`**；
   字段用 `Field(default, description=...)`。
4. **Alconna 对象必须强引用**：规则只持弱引用，`on_alconna(Alconna(...))` 可能被 GC，
   matcher 会静默失效。代码用 `_cmd()` 收集到 `_ALCONNA_REFS`。
5. **会话解析**：`nonebot_plugin_uninfo.get_session(bot, event)` 是公开接口，
   失败回落到 `nonebot_plugin_alconna.uniseg.get_target(event, bot)`。
   `Session.scene_path` 真实存在（读源码确认），群=群号、频道=父id_子id。
6. **角色是对象不是字符串**：`session.member.role` 是 `Role | None`，
   字段 `id/level/name`；OneBot 的 `id` 是 `OWNER/ADMINISTRATOR/MEMBER`，
   `name` 是小写 `owner/admin/member`。同时按 id 与 name 判断最稳。
7. **At 段字段**：`flag`(user/role/channel)、`target`、`display`；只接受 `flag == "user"`。
8. **`use_cmd_start` 默认 False**：不显式传 True 时，`/电` 不会被响应（alconna 文档明确写了默认值）。
9. **`MultiVar(str, "*")` 的第二个参数是 default，不是「0 个或多个」的开关**：
   参考插件里那种写法语义可疑，先不用。理由参数已整体移除，`zap` 只收 `At`；
   将来若要整句文本，按文档用 `AllParam`（返回 UniMessage）或 `MultiVar(str)` 并实测。
10. **头像**：uninfo 的 `User.avatar` 有值（OneBot 会给 qlogo 地址），
    目标用户走 `get_interface(bot).get_user(uid).avatar`，取不到再退回 qlogo 拼接。
11. 命令 matcher 显式给 `priority` / `block`；群管理判定仍用「超管 ∪ 群主 ∪ 群管理」，
    没有直接挂 `ADMIN()` 权限（那会把群主之外的管理挡掉，且频道场景语义不同）。

## 14. AstrBot 适配（v0.1 已完成首版，未经真机运行）

目录约定：**仓库根目录就是 AstrBot 插件目录**（`metadata.yaml` + `main.py` + `_conf_schema.json`），
把整个仓库克隆到 `data/plugins/` 下即可；`main.py` 把仓库根插入 `sys.path`，
所以 `import volt_toy_core` 不需要额外安装。

依据的官方文档（2026-10 核对）：

- 插件结构：`metadata.yaml` 必填（name / desc / version / author / repo）。
- 入口：`class X(Star)`，`__init__(self, context: Context, config: AstrBotConfig)`。
- 配置：`_conf_schema.json`，字段 type/description/hint/default；WebUI 可视化。
- 事件：`AstrMessageEvent` 提供 `get_sender_id()`、`get_sender_name()`、`get_group_id()`、
  `get_self_id()`、`is_admin()`、`unified_msg_origin`（platform:type:session）、`get_messages()`。
- 发送：`yield event.plain_result(text)` / `yield event.chain_result([Plain, Image])`。
- 图片：`astrbot.api.message_components.Image.fromURL(url)`（也有 fromBytes/fromBase64）。
- 数据目录：`get_astrbot_data_path() / "plugin_data" / <插件名>`。

实现要点：

- 会话键直接用 `event.unified_msg_origin`，天然区分平台/群/私聊，不会和 nonebot 的
  `适配器:scene_path` 冲突（两边数据目录本就分开）。
- @ 目标从消息链里找 `At`，跳过 `qq == "all"`（AtAll）。
- 头像是 aiocqhttp/QQ 系才拼 qlogo URL，其它平台只发文本。
- 管理员用 `event.is_admin()`（AstrBot 的 role），没有像 nonebot 那样再查平台群管理。

AstrBot 插件市场合规（2026-10-22 按官方「发布插件到插件市场」核对）：

- [x] 仓库根目录有 `metadata.yaml` + `main.py`（市场按仓库根识别）。
- [x] `name` 为 `astrbot_plugin_volt_toy`：`astrbot_plugin_` 前缀、全小写、无空格。
- [x] `version` 为 `0.1.0`（去掉原来的 `v` 前缀，按语义化版本）。
- [x] `author` / `name` 组合构成 plugin_id；`author` 已改成 GitHub 账号 `Funny1Potato`。
- [x] `repo` 是合规的 HTTPS GitHub 仓库 URL（不带子目录）。
- [x] `desc` 改为多行 Markdown；补了 `short_desc` / `support_platforms` / `tags` /
      `astrbot_version` / `social_link`。
- [x] 压缩包体积约 50KB，远低于 16MB 上限；`.gitignore` 已排除 `.venv`、`dist`、
      `__pycache__`、`pytest-of-*`。
- [ ] 尚未在 AstrBot 真机加载过；提交市场前建议先本地 `git clone` 到 `data/plugins/` 试一次。
- 注意：仓库名是 `Volt-Toy` 而插件名是 `astrbot_plugin_volt_toy`。规范允许仓库名不同
  （plugin_id 由 author/name 决定），但若市场审核要求仓库名与插件名一致，需要改名。

待办 / 风险：

- `event.is_admin()` 在 AstrBot 里通常是「机器人管理员」而非「群管理员」，若要让群管也能清档，
  需要按平台调接口或加配置项，这个语义要和用户确认。
- AstrBot 的数据目录函数在旧版本不存在，代码已 try/except 回退到插件目录。
- 同一份账本在两边之间迁移需要把 key 前缀统一（nonebot `onebot11:群号` vs
  astrbot `aiocqhttp:group:群号`），目前**没有**做迁移脚本。
