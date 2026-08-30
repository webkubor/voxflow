# Configs 治理说明

> 完整命令清单请查看：[docs/COMMANDS.md](../docs/COMMANDS.md)

## 目录分层
- `configs/*.json`：仅保留 4 个核心 JSON：
  - `clone.json`
  - `design.json`
  - `dialogue.json`
  - `personas.json`

## 调用方式
- 推荐：
  - `voice clone ...`
  - `voice design ...`
  - `python main.py dialogue`

## 规则
- 运行前会执行内置策略校验（字段完整性、文本长度、角色合法性、禁用关键词）。
- 0-1 阶段（克隆/设计）可不注册 `personas.json`；生产阶段（单角色生成/对话）需在 `personas.json` 注册角色。
- `personas.json` 的 `ref` 必须遵循统一命名：`assets/reference_audio/<角色名>_参考.<wav|mp3|m4a>`。
- `design` 建议填写 `voice_name`；默认先输出到 `out/`。
- 当 `commit_to_temp=true` 时，设计结果会沉淀到 `assets/temp/`，并自动更新 `configs/personas.json` 和 `configs/generated/<voice_name>_generate.json`。
- `design` 文案最多 45 字，可留空自动填默认短句。
## 发布账号台账

`publish_accounts.json` 仅保存三个发布账号的显示名、平台归属和**状态元数据**，不保存 Cookie、密码、Token 或其他登录凭据。工作台的「自动发布」页从这里读取登录状态，并从 `pipeline.json` 读取账号名下已发布歌曲与云备份标记。

状态必须以真实检测或人工确认为准：未接入检测时使用 `unconfigured`，不要标记为 `connected`。
