<p align="center">
  <img src="assets/branding/logo-icon.png" width="120" alt="VoxFlow 声流" />
</p>

<h1 align="center">VoxFlow 声流</h1>

<p align="center">
  <img src="https://img.shields.io/github/license/webkubor/voxflow?style=flat-square&color=92a8b3" alt="License" />
  <img src="https://img.shields.io/github/stars/webkubor/voxflow?style=flat-square&color=cc584d" alt="Stars" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-5fa8b2?style=flat-square" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/Qwen3--TTS-1.7B-A873C4?style=flat-square" alt="Qwen3-TTS 1.7B" />
  <img src="https://img.shields.io/badge/%E9%9F%B3%E9%A2%91-%E4%B8%8D%E5%87%BA%E6%9C%AC%E6%9C%BA-4c9a6b?style=flat-square" alt="音频不出本机" />
  <img src="https://img.shields.io/badge/Platform-macOS%20Apple%20Silicon-1f1f1f?style=flat-square" alt="macOS Apple Silicon" />
</p>

<p align="center">
  <b>本地运行的中文语音克隆、音色设计与全网音乐发行工作台。</b>
  <br />
  一条命令合成音频，<b>不联网、无需商业 API Key、私密音频永不离机</b>。
  <br />
  面向创作者、独立音乐人，以及 AI / Agent 自动化工作流。
</p>

<p align="center">
  <a href="#-快速开始"><strong>快速开始</strong></a> ·
  <a href="#-核心能力与命令"><strong>核心命令</strong></a> ·
  <a href="#-web-ui-工作台"><strong>Web 工作台</strong></a> ·
  <a href="#-全网音乐发行集成"><strong>全网发行</strong></a> ·
  <a href="#-agent--ai-调用"><strong>Agent 调用</strong></a>
</p>

<p align="center">
  <img src="assets/branding/social-banner.png" width="100%" alt="VoxFlow 声流 — 本地中文语音克隆 · 音色设计 · 全网音乐发行" />
</p>

---

## ⚖️ 核心优势与方案对比

| 特性 | ElevenLabs / 商业云 | 剪映配音 / 在线平台 | **VoxFlow 声流** |
|---|:---:|:---:|:---:|
| **音频隐私安全** | ❌ 必须上传云端 | ❌ 依赖平台服务器 | 🛡️ **全程本地运行，绝不出机** |
| **声音克隆** | ⚠️ 按月订阅 / 计次计费 | ❌ 不支持自定义 | ✅ **一段 5~10 秒样音即刻克隆** |
| **文字描述造音色** | ⚠️ 支持有限 | ❌ 无此能力 | 🎨 **无需参考音，一句话提示词凭空捏音** |
| **持续使用成本** | 💸 按 Token/字符持续扣费 | 🔒 绑定特定生态 | 🎁 **一次部署，永久免费** |
| **全网发行集成** | ❌ 需手动分发 | ❌ 仅限内置分发 | 🚀 **汽水音乐 / QQ音乐 / 网易云发行台账集成** |
| **开发与自动化** | ✅ REST API | ❌ 封闭 GUI | ⚡ **统一 CLI + FastAPI 后端 + Agent Skill** |

---

## 🚀 快速开始

### 1. 一键安装与环境初始化

```bash
# 克隆仓库
git clone https://github.com/webkubor/voxflow.git
cd voxflow

# 运行自动化安装脚本（自动创建 .venv、安装依赖并下载基础模型）
chmod +x install.sh && ./install.sh

# 激活虚拟环境
source .venv/bin/activate

# 查看环境就绪状态
voice doctor
```

### 2. 启动 Web UI 创作工作台

```bash
voice web
# → 浏览器访问 http://localhost:8866
```

---

## ⚡ 核心能力与命令

VoxFlow 提供现代化 Typer CLI 工具链，支持本地音频处理全流程：

### 🎙️ 1. 声音克隆 (Voice Clone)
使用已有音色角色批量合成台词文本：

```bash
# 基础克隆
voice clone narrator "霜叶红于二月花，山色空蒙雨亦奇"

# 指定语气与情绪修饰
voice clone xiao_jing "今天天气真好，我们一起去散步吧！" --tone "轻快活泼" --emotion "happy" -o out/morning.wav
```

### 🎨 2. 音色设计 (Voice Design)
**无需任何参考音频**，仅通过自然语言描述创造专属音色：

```bash
# 通过文字描述设计新音色并入库
voice design sword_master "十步杀一人，千里不留行。" --tone "苍劲豪迈的江湖侠客，沉稳威严"
```

### 📜 3. 多角色对白合成 (Dialogue)
根据剧本配置文件一键批量合成完整对话音轨：

```bash
voice dialogue configs/dialogue.json -o out/story_episode_1.wav
```

### 📦 4. 音色库管理 (Voice Assets)

```bash
voice voice list                        # 查看本地所有已注册音色
voice voice add my_voice sample.wav     # 从参考音频注册新音色
voice voice preview narrator            # 试听音色预设样音
voice voice rm old_voice                # 删除指定音色
```

---

## 🖥 Web UI 工作台

VoxFlow 内置高对比、纯净深色的现代音频创作界面：

<p align="center">
  <img src="assets/screenshots/web-ui-clone-workflow.png" width="100%" alt="VoxFlow 声音克隆与工作台"/>
</p>

- **音色工坊**：左侧统一管理所有已装载的音色艺人，支持快捷试听波形律动与样音状态。
- **创作控制台**：包含快速氛围预设（温柔治愈 / 激情旁白 / 午夜低语 / 武侠江湖）、情绪优先级控制与草稿箱管理。
- **全网发行枢纽**：直连 **汽水音乐、QQ音乐、网易云音乐** 发行台账，管理歌手档案、歌曲 ID 映射及平台元数据。
- **媒体资产库**：历史音频一键在线试听、波形查看与批量物理下载。
- **全定制纯净播放器**：完全剔除原生浏览器控件，提供极细时间轨、高精度拖拽定位与无损播放。

---

## 🌐 全网音乐发行集成

VoxFlow 不仅是语音合成引擎，更是面向独立创作者的**音乐与音频发行管理中枢**：

- **歌手身份台账 (`configs/artist.json`)**：统一维护公开艺名、实名版权主体、各平台主页与平台歌手 ID。
- **多平台数据对齐**：支持自动解析与校验汽水音乐、QQ 音乐、网易云音乐已上架曲目 ID 与播放外链。
- **标准分发规范**：一键打包 Audio、Cover 与歌词 Meta 资产包，对齐各大音乐发行渠道规范。

---

## 🤖 Agent / AI 自动化调用

VoxFlow 原生面向自动化 Agent 体系设计：

### 1. 无交互自动化部署 (CI/CD)

```bash
./install.sh --yes                      # 全自动安装：依赖 + Base + VoiceDesign 模型
./install.sh --yes --skip-voice-design  # 仅装依赖与 Base 模型（省 4.2GB）
```

### 2. 环境诊断与健康检查

```bash
voice doctor           # 终端表格检查报告
voice doctor --json    # 输出 JSON 格式供 Agent 决策解析
```

---

## 📁 项目架构

```
voxflow/
├── cli/            # Typer CLI 命令入口 (clone / design / dialogue / web / doctor 等)
├── core/           # 核心业务引擎 (克隆器 / 提示词设计 / 数据库 / 管道分发)
├── web/            # FastAPI 后端路由与静态服务
│   ├── app.py      # RESTful API 端点 (合成、音色、艺人档案、任务队列)
│   └── ui/         # Vue 3 + Pinia + Vite 现代纯黑工作台前端源码
├── configs/        # 平台 SOP、模板及初始配置
└── assets/         # 品牌图标与官方工作台截图
```

---

## 📄 开源协议

本项目采用 **Apache-2.0** 许可证开源。
底层语音建模基于 Qwen3-TTS 深度定制开发。
