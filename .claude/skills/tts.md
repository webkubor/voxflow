---
name: tts
project: voxflow
for: ai-agent
---

# VoxFlow 声流 — Agent 调用 SOP

## 前置

```bash
cd /path/to/voxflow
source .venv/bin/activate
# 或直接用绝对路径：.venv/bin/voice
```

调用前建议先运行环境自检：

```bash
voice doctor --json
```

## 核心命令

```bash
# 查看可用音色
voice voice list

# 声音克隆（角色 + 台词 → wav）
voice clone <persona> "<台词>" [-o output.wav]

# 音色设计（文字描述 → 新音色）
voice design <name> "<建模短句>" --tone "<风格描述>"

# 多角色对话（脚本文件 → 多段音频）
voice dialogue --script <script.txt>

# 启动 Web UI
voice web
```

## 输出

- 默认输出到 `out/`
- 文件名格式：`<persona>_YYYYMMDD_HHMMSS.wav`

## 红线

- 调用前必须 `source .venv/bin/activate`，否则 `voice` 找不到
- `--tone` 参数用中文描述效果更准确
- 首次运行需确认 `models/` 目录有模型文件
- 自动化安装使用 `./install.sh --yes`
