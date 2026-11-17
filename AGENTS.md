# AGENTS.md — AI 助手工作守则

## 这是什么

VoxFlow（声流）—— Apple Silicon 本地 AI 音频工作台：本地 TTS（Qwen3-TTS MLX 8-bit）、
语音克隆、音色设计、剧本演播。音乐生成与发行已迁到 suno-publisher（它仍通过 `/api/catalog/*`、`/api/artist`、`/api/economics` 读取本仓数据，这些接口不要删）。**音频不出本机**是硬承诺。

## 关键文件

- `cli/`：命令行入口与子命令。
- `TUI_DESIGN.md` / `VOICE_DESIGN_SOP.md` / `TECHNICAL_PATH.md`：设计文档 —— TUI 交互、音色设计 SOP、技术路线，改交互/音色流程前先读对应文档。
- `CLAUDE.md`：Claude 的项目上下文（与本文不冲突时以更具体的为准）。
- `assets/`：品牌与静态资源。

## 约定

- **隐私红线**：任何改动不得引入音频上传 / 云端处理路径。
- Python 3.10+；模型走 MLX，改动注意 Apple Silicon 兼容。
- 双语 README（`README.md` / `README.en.md`）同步维护。
- 发版与 CHANGELOG 走既有流程。

## Agent 用 CLI 操作音色库

音色库 / 生成库 / 设计模板的业务规则只有一处：`core/voice_library.py`，Web（`web/app.py`）和 CLI（`cli/commands/`）都调用它。改规则改这里，不要在两端各写一份。

调用约定（`cli/output.py`）：加 `--json` 时 stdout 只有一个 JSON 对象（`{"ok": true, ...}` / `{"ok": false, "error", "status"}`），进度走 stderr；退出码 0 成功、1 错误、3 不存在、4 冲突。删除类命令在非交互环境必须加 `--yes`。

```bash
voice voice add <key> <audio> --ref-text "逐字原文" [--name 显示名] --json   # 克隆自己的声音（重名退出 4，不覆盖）
voice voice record <key> --ref-text "朗读原文" --seconds 15 --json          # 麦克风录音并注册（需终端麦克风权限）
voice voice list [--favorites] --json                                      # 音色库；--favorites 只看收藏
voice voice rename <key> <新名> | favorite <key> | unfavorite <key> --json
voice voice rm <key> --yes --json                                          # 仅未收藏可删；参考音频保留
voice preset list [--pending] --json                                       # 模板及是否已生成
voice preset run <模板> [--dry-run] --json                                  # 已生成/正在生成 → 退出 4
voice library list [--kind design] [--unsaved] --json                      # 生成库
voice library save <文件名> <音色名> [--ref-text ...] --json                # 收藏设计样音，不重新生成
voice library rm <文件名> --yes --json                                     # 关联音色已收藏 → 退出 4
voice design / voice clone ... --json                                      # 本地模型生成，返回文件路径
```

契约测试：`tests/test_cli_voice_library.py`。
