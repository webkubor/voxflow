# AGENTS.md — AI 助手工作守则

## 这是什么

VoxFlow（声流）—— Apple Silicon 本地 AI 音频工作台：本地 TTS（Qwen3-TTS MLX 8-bit）、
语音克隆、音色设计，另支持 Suno 音乐生成。**音频不出本机**是硬承诺。

## 关键文件

- `cli/`：命令行入口与子命令。
- `TUI_DESIGN.md` / `VOICE_DESIGN_SOP.md` / `TECHNICAL_PATH.md`：设计文档 —— TUI 交互、音色设计 SOP、技术路线，改交互/音色流程前先读对应文档。
- `CLAUDE.md`：Claude 的项目上下文（与本文不冲突时以更具体的为准）。
- `assets/`：品牌与静态资源。

## 约定

- **隐私红线**：任何改动不得引入音频上传 / 云端处理路径（Suno 是用户显式授权的例外，只传生成请求需要的最少内容）。
- Python 3.10+；模型走 MLX，改动注意 Apple Silicon 兼容。
- 双语 README（`README.md` / `README.en.md`）同步维护。
- 发版与 CHANGELOG 走既有流程。
