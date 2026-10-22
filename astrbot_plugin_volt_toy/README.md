# AstrBot 适配（未开始）

状态：**未实现**。nonebot 版稳定后再做。

## 已经确定的部分

- 业务逻辑全部在 `volt_toy_core`，AstrBot 版只需要做三件事：
  1. 把 AstrBot 的消息事件翻译成 `ZapRequest`（群 key、发送者、目标、显示名、是否管理员）；
  2. 调 `ZapService.zap()` 拿文本；
  3. 发文本，成功时可选附头像。
- 数据文件沿用同一份结构（`zap.json` / `zap_log.jsonl` / `zap_whitelist.json`），
  放到 AstrBot 的插件数据目录即可，两边可对拷。

## 待研究

- AstrBot 插件基类与注册方式（`Star`、`@filter.command`、`AstrBotConfig`）。
- 多协议消息对象：如何取群 ID、发送者 ID、@ 目标、显示名、群管理身份。
- 数据目录 API（`data/plugin_data/<plugin>/`）。
- 头像：QQ 系协议仍可用 qlogo；其它协议跳过。

## 依赖

AstrBot 插件如何声明 Python 依赖（requirements / metadata）需要按官方插件文档确认；
如果支持 PyPI 依赖，应依赖 `volt-toy-core`；否则在插件内 vendor 一份内核。
