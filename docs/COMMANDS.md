# 命令速查

本文档只保留**当前仓库真实可用**的命令。

## 1. 安装

```bash
chmod +x install.sh
./install.sh
source .venv/bin/activate
```

运行要求：Python 3.10+、约 4.2GB（仅 Base）或 8.4GB（Base + VoiceDesign）模型磁盘空间；建议在 macOS Apple Silicon 上运行。FFmpeg 用于 MP3 参考音频与自动裁剪：`brew install ffmpeg`。没有 MPS 时会回退到 CPU。

如果你只想重新安装项目本体：

```bash
pip install -e .
```

## 2. CLI 主入口

```bash
voice --help
```

常用命令：

```bash
# 查看音色库
voice voice list

# 查看预设
voice preset list

# 查看任务历史
voice job list

# 从已有音色克隆
voice clone <persona> "你好，欢迎使用 VoxFlow 声流"

# 从文字描述设计新音色
voice design <voice_name> "这是一段建模短句" --tone "温柔、清晰、贴耳"

# 根据 JSON 剧本合成多角色对话
voice dialogue configs/dialogue.json
```

## 3. 兼容入口

旧流程仍可继续使用：

```bash
python main.py
python main.py clone
python main.py design
python main.py dialogue
```

## 4. 配置文件

运行时重点关注这几个文件：

- `configs/clone.json`
- `configs/design.json`
- `configs/dialogue.json`
- `configs/personas.json`

## 5. 前端开发

Web UI 已随仓库构建产物提供，直接使用：

```bash
voice web
```

修改或重新构建前端时：

```bash
cd web/ui
npm install
npm run dev      # 开发服务器
npm run build    # 构建到 web/static/
```

## 6. 排查

```bash
# 看当前改动
git status --short

# 看安装后的 CLI 是否存在
which voice

# 检查 Python 包是否已安装
pip show voxflow
```
