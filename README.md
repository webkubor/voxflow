<p align="center">
  <img src="assets/branding/logo-icon.png" width="120" alt="VoxFlow 声流" />
</p>

<h1 align="center">VoxFlow 声流</h1>

<p align="center">
  <img src="https://img.shields.io/github/license/webkubor/voxflow?style=flat-square&color=92a8b3" alt="License" />
  <img src="https://img.shields.io/github/stars/webkubor/voxflow?style=flat-square&color=cc584d" alt="Stars" />
  <img src="https://img.shields.io/badge/Python-3.10%2B-5fa8b2?style=flat-square" alt="Python 3.10+" />
  <img src="https://img.shields.io/badge/Qwen3--TTS-1.7B%20MLX%208--bit-A873C4?style=flat-square" alt="Qwen3-TTS 1.7B MLX 8-bit" />
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
  <a href="#-本地语音合成后端apple-mlx-8-bit"><strong>语音后端</strong></a> ·
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
| **成本与回本可见** | ❌ 只给账单总额 | ❌ 无 | 📊 **每首歌花了多少 · 播多少次回本 · 实测千播单价** |

---

## 🚀 快速开始

### 1. 装依赖（约 2 分钟）

```bash
git clone https://github.com/webkubor/voxflow.git
cd voxflow

# --skip-models：先不下 5.8 GB 模型，装完就能开工
chmod +x install.sh && ./install.sh --skip-models

source .venv/bin/activate
voice doctor            # 环境自检
```

### 2. 打开工作台，边用边下模型

```bash
voice web
# → 浏览器访问 http://localhost:8866
```

**不用等模型下完才开始。** 本地 TTS 的模型权重有 5.8 GB（MLX 8-bit），但 VoxFlow 里
**不碰本地模型的功能占了一多半**：

| 立刻可用（零下载） | 需要 Base 模型（2.9 GB） | 需要 VoiceDesign（2.9 GB） |
|---|---|---|
| AI 音乐（Suno） | 声音克隆 | 一句话凭空捏音色 |
| 作品看板 / 全网发行台账 | 多角色剧本合成 | |
| 运营台（成本 / 健康 / 日志） | | |

所以首屏**按当前能力决定落点**：模型没下时直接落在「AI 音乐」而不是一屏
灰按钮。想用克隆时点进去，那一屏有张卡可以**就地开始下载**（后台跑，
关掉页面也不中断），并列出这期间照常能用的功能。

也可以一次装到底：

```bash
./install.sh                        # 交互式，问你要不要下 VoiceDesign
./install.sh --yes                  # 无交互，两个模型都下（CI / Agent）
./install.sh --yes --skip-voice-design   # 只下 Base，省 2.9 GB
```

> 模型下到 **`~/.voxflow/models-mlx/`**（数据目录），不是项目目录 ——
> 重装工具、换分支、`git clean` 都不会让你重下一遍 5.8 GB。
>
> 2026-09-14 之前下的是 Qwen 原生 PyTorch 权重（`~/.voxflow/models/`，8.4 GB）。
> 那套现在已经没有代码读取，留着只是为了回滚；确认 MLX 版稳定后可以自行删除腾空间。

---

## ⚡ 核心能力与命令

VoxFlow 提供现代化 Typer CLI 工具链，支持本地音频处理全流程：

### 🎙️ 1. 声音克隆 (Voice Clone)
使用已有音色角色合成台词文本，产物落在数据目录的 `out/`：

```bash
# 基础克隆：音色取自该角色在 personas.json 里登记的参考音频
voice clone narrator "霜叶红于二月花，山色空蒙雨亦奇"
```

> **⚠️ `--tone` / `--emotion` 在克隆路径上不生效。** MLX 的 Base 模型在源码层
> 就没有动态情绪指令的入口（PyTorch 时代的 `instruct_ids` 是真生效的，迁移后
> 没有等价实现）。要带情绪就把情绪**写进文本本身**（「他愤怒地吼道：……」），
> 或改用下面的**音色设计** —— 它走 VoiceDesign，原生支持指令。
> 传了 `--tone` 时 CLI 会明确告诉你「本次不会生效」，不会静默吞掉。

### 🎨 2. 音色设计 (Voice Design)
**无需任何参考音频**，仅通过自然语言描述创造专属音色：

```bash
# 通过文字描述设计新音色并入库
voice design sword_master "十步杀一人，千里不留行。" --tone "苍劲豪迈的江湖侠客，沉稳威严"
```

### 📜 3. 多角色对白合成 (Dialogue)
根据剧本配置文件一键批量合成完整对话音轨：

```bash
voice dialogue configs/dialogue.json
```

### 📦 4. 音色库管理 (Voice Assets)

```bash
voice voice list                        # 查看本地所有已注册音色
voice voice add my_voice sample.wav     # 从参考音频注册新音色
voice voice preview narrator            # 试听音色预设样音
voice voice rm old_voice                # 删除指定音色
```

### 📊 5. 成本与运行状况 (Stats & Logs)

```bash
voice stats                    # 近 30 天：钱花在哪、本地跑省下多少
voice stats --tracks           # 按作品拆分：每首歌成本 + 回本播放数
voice stats --json             # 结构化输出，供 agent 判断「还要不要继续跑」
voice logs --level error       # 只看失败的调用（失败照样扣上游积分）
```

---

## 🧠 本地语音合成后端：Apple MLX 8-bit

VoxFlow 的 TTS 在 **2026-09-14** 从 PyTorch(MPS) 迁到了 **Apple MLX**，模型换成
`mlx-community` 的 8-bit 量化版。这不是「换个库」，它把一类静默故障从架构上消掉了。

### 实测收益

| 指标 | PyTorch + MPS（迁移前） | Apple MLX 8-bit（现在） | 变化 |
|---|---|---|---|
| 模型体积（Base + VoiceDesign） | 8.4 GB | **5.8 GB** | ⬇ **省 31%** |
| 单次推理 | 9.32 s | **5.29 s** | ⬆ **快 1.76×** |
| 输出时长（同文本同音色） | 4.64 s | 4.56 s | 一致 |
| 音质（whisper 转写回读） | 一字不差 | 一字不差 | **无损失** |
| 峰值内存 | — | 6.97 GB（实测） | — |
| 模型加载 | 14.44 s | 6.55 s 冷 / 5.74 s 热 | 首次冷读盘偏慢 |

**快的原因不是「MLX 天生快」。** PyTorch 那版靠一行
`PYTORCH_ENABLE_MPS_FALLBACK=1` 才跑得起来 —— MPS 不支持的算子会**静默回退到
CPU**，中间还要把张量搬回来，「统一内存」在这一步被浪费，而外部完全看不出来。
MLX 没有 fallback：要么全走 Metal GPU，要么报错，**不存在静默降级**。
这才是迁移的根本收益，省 31% 体积只是顺带的。

### 音色还原度：既没变差，也没变好

用 Qwen3-TTS 自带的 speaker encoder（x-vector）算余弦相似度，**带负对照**（另一个
音色作下界）**并测噪声底**（同后端换 seed，看相似度自己抖多少）：

| 对象 | 与原音色的余弦相似度 |
|---|---|
| 参考音频自比（上界） | 1.0000 |
| PyTorch seed 42 / 43 / 44 | 0.9931 / 0.9928 / 0.9925 |
| MLX | 0.9934 |
| 负对照 · 另一个音色（下界） | 0.9425 |

PyTorch 三个 seed 的极差（**噪声底**）= 0.0006，MLX 与 PyTorch 均值之差 = **+0.0006**
—— 恰好落在噪声底上。**所以迁移在音色上既没有损失也没有收益**，别拿它当补偿项。
复现脚本：[`tools/compare_voice_fidelity.py`](tools/compare_voice_fidelity.py)。

### 两个必须知道的限制

**1. 克隆路径没有动态情绪指令。** MLX 的 Base 模型在源码层就没有 instruct 入口
（`_generate_icl()` 签名里没有该参数）。而 PyTorch 时代的 `instruct_ids` 是
**真生效的** —— 控制变量实测（固定 seed、只切这一个参数）输出完全分叉：
F0 变异系数 +33.9%、F0 动态幅度 +49.9%、能量动态幅度 +136.5%，正是情绪唤醒的声学
特征。所以这是**净损失**，不是「本来就没用」。替代方案：把情绪写进文本，或走
VoiceDesign。复现脚本：[`tools/verify_instruct_effect.py`](tools/verify_instruct_effect.py)。

**2. `ref_text` 必填。** 克隆时参考音频对应的文本要填在 `personas.json` 的
`ref_text` 字段里，留空会**截断 + 乱码**：

| `ref_text` | 产出时长 | whisper 转写 |
|---|---|---|
| `""`（错） | 2.08 s（截断） | 「这是一字语音色争要了根根」❌ |
| 真实文本（对） | 4.56 s | 「这是一次语音合成测试，用来验证模型能否正常工作。」✅ |

缺这个字段时 CLI 会直接报错、并告诉你该拿 whisper 转写哪个文件，不会丢一段乱码给你。

### 硬件要求

**Apple Silicon（M 系列）+ macOS，没有例外。** PyTorch 回退链路已整个删除
（留着等于每次改代码维护两套、A/B 跑两遍）。
`voice doctor` 在非 Apple Silicon 上会直接 **FAIL** 而不是 WARN ——
「不能用」不该被写成「差一点」。

决策过程、能力矩阵、全部改动清单与回滚方法见
[docs/MLX_MIGRATION.md](docs/MLX_MIGRATION.md)。

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
- **运营台**：成本、收益、系统健康、运行日志四合一 —— 见下一节。

---

## 📊 运营台：把这门生意的账算清楚

大多数 AI 创作工具只告诉你「生成成功」。VoxFlow 还告诉你**这次生成花了多少、
这首歌播多少次回本、到今天为止是赚还是赔**。

访问 `http://localhost:8866/#/ops`，或跑 `voice stats`。

### 成本侧：三条链路合成一本账

| 上游 | 计费方式 | 在账上怎么体现 |
|---|---|---|
| 本地 TTS（Qwen3-TTS） | 免费 | 实付永远 ¥0，同时折算出「同样的量走商业 API 要多少」 |
| Suno AI 音乐 | 订阅积分 | 每次生成扣的 credits × 当时单价 |
| museav 中台（出图 / 文案） | 预付积分 | 按 token / 张数计量，走 `voice museav login` 授权，花的是**你自己账户**的积分 |

两个容易被忽略、但这里特意做了的细节：

- **失败的调用照样记账**。Suno 生成失败一样扣积分，只记成功的话账永远对不上，
  而「失败率 × 单价」正是最该被看见的那笔浪费。
- **成本在写入时按当时单价定格**。换套餐、中台调价，都不会回溯改写历史账目 ——
  否则改一次价，过去半年的账全变了。

单价表在 [`configs/pricing.json`](configs/pricing.json)，复制到 `~/.voxflow/configs/`
即可覆盖，升级不会被冲掉。

### 收入侧：用实测数据反推真实分成率

平台后台同时给出累计播放量和可提现金额，两个数一除就是**这个账号实际拿到的
千播单价** —— 比任何公开资料都准，因为它已经包含了实际权益档位。

界面上会明确标注每个单价是「实测」还是「估算」。分成率零一手资料的平台
（如腾讯系）宁可留空，也不填一个猜的数 —— 猜的数会被当成真数据拿去做决策。

### 拆到单曲：哪首歌在赚钱

账号级汇总回答不了「下一首该做什么风格」。单曲维度的播放量公开 API 给不了
（网易云 `song/detail` 的 `playedNum` 恒为 0，实测过），只能从音乐人后台抓：

```bash
VF_BASE=$PWD browser-harness < scripts/ncm_stats.py         # 账号级：总播放 / 粉丝 / 收益
VF_BASE=$PWD browser-harness < scripts/ncm_track_stats.py   # 单曲级：近 30 日播放量
```

运营台的作品表随即给出每首歌的 **成本 · 近30日播放 · 折算收益 · ROI · 回本还差多少次**。

两个必须说清的口径：

- **播放量是近 30 日，不是累计**。后台只给 7 日 / 30 日两档；而且累计里绝大部分
  是老作品的历史沉淀，「最近 30 天哪首在涨」才是能指导选题的信号。
- **单曲收益是折算的**。后台没有单曲收益列，所以按 `播放量 × 实测千播单价` 折算。
  网易云按播放计费、同账号各曲单价基本相同，折算站得住 —— 但它不是平台实付，
  界面上标着，别拿它对账。

表里的「—」表示**没有数据**，不是 0。两者含义完全不同：前者是还没抓，后者是真的没播。

### 系统健康：不是 ping，是体检

`/api/health` 检查库能不能读、数据目录能不能写、磁盘还剩多少、模型下完没有、
任务队列堵没堵，返回 `ok` / `degraded` / `down` 三档。

`degraded` 是最有用的那一档 —— 「还能出歌，但快没空间了」。只有 ok/down 两档的话，
degraded 会被算成 ok，等发现时已经是 down。

```bash
curl -s localhost:8866/api/health | jq .status     # 给监控/agent 用
curl -s localhost:8866/api/metrics | jq .routes    # 各端点的量、错误率、P50/P95
```

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
./install.sh --yes --skip-voice-design  # 仅装依赖与 Base 模型（省 2.9GB）
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
├── core/           # 核心业务引擎 (克隆器 / 提示词设计 / 数据库 / 管道分发 / 计量 obs.py)
│   ├── paths.py    # 路径真源 —— 代码在哪、数据在哪，全项目只在这里定义一次
│   └── engine.py   # Qwen3-TTS 引擎（Apple MLX 8-bit，见 docs/MLX_MIGRATION.md）
├── web/            # FastAPI 后端路由与静态服务
│   ├── app.py      # RESTful API 端点 (合成、音色、艺人档案、任务队列、健康/指标/成本)
│   └── ui/         # Vue 3 + Pinia + Vite 现代纯黑工作台前端源码
├── configs/        # 平台 SOP、单价表 (pricing.json) 及初始配置
├── tools/          # 一次性验证脚本 (MLX 冒烟 / PyTorch 基线 / 音色还原度 / 内存探测)
├── docs/           # 文档索引见 docs/README.md
├── tests/          # 计量逻辑自检（无框架，python tests/test_obs.py 直接跑）
└── assets/         # 品牌图标与官方工作台截图
```

---

## 📄 开源协议

本项目采用 **Apache-2.0** 许可证开源。
底层语音建模基于 Qwen3-TTS 深度定制开发，推理权重使用
[mlx-community](https://huggingface.co/mlx-community) 的 12Hz-1.7B 8-bit 量化版。
