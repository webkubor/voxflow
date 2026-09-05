# TUI 设计文档 — VoxFlow 声流

> 本文档描述将VoxFlow 声流改造为 TUI（终端用户界面）CLI 服务的完整设计方案。
> 目标：在现有 `core/` 后端不变的前提下，用 `typer` + `rich` + `textual` 构建一套
> 本地音色素材管理 + TTS 生产工作流的终端交互系统。
>
> 说明：本文档里历史上出现的旧命令别名 `bsm`，现统一视为 `voice`。

---

## 一、为什么选择 TUI

| 维度 | TUI | GUI 网页 |
|---|---|---|
| 进程数 | 1（Python 进程） | 2（FastAPI + Vite） |
| 与现有 CLI 的距离 | 零重写，直接扩展 `main.py` | 需维护前后端同步 |
| 音色资产管理 | 表格 + 预览，足够 | 需要额外文件上传接口 |
| 本地使用场景 | 完美匹配 | 过度设计 |
| 武侠审美 | 终端黑底 + 金色高亮，天然契合 | 需要额外设计 |

---

## 二、命令体系设计

### 入口命令：`bsm`（boiling-snow manage）

```
bsm [子命令] [参数] [选项]
```

#### 2.1 音色素材管理（`bsm voice`）

```
bsm voice list                         # 列出所有已注册音色（表格形式）
bsm voice add <key> <audio_path>       # 从参考音频注册新音色
bsm voice preview <key> [--text TEXT]  # 用短句预听音色（默认测试句）
bsm voice show <key>                   # 查看音色详情（personas.json + 设计配方）
bsm voice rm <key>                     # 删除音色注册（不删除实际音频文件）
bsm voice import <personas.json>       # 批量导入角色映射
```

**`bsm voice list` 输出示例：**

```
┌─────────────────────────────────────────────────────────────────┐
│  沸腾之雪 · 音色库                            共 12 个音色       │
├──────────────┬────────┬──────────────┬─────────────┬───────────┤
│  角色 Key    │  名称  │  样音状态    │  设计配方   │  最近使用 │
├──────────────┼────────┼──────────────┼─────────────┼───────────┤
│  xue_wuhen   │  薛无恨│  ✓ 已缓存   │  ✓ 有配方   │  3 天前   │
│  shui_yan    │  水烟  │  ✓ 已缓存   │  ✓ 有配方   │  今天     │
│  old_monk    │  老和尚│  ✗ 缺失     │  ✓ 有配方   │  —        │
│  wang_ye     │  王爷  │  ✓ 已缓存   │  ✗ 无配方   │  7 天前   │
└──────────────┴────────┴──────────────┴─────────────┴───────────┘
```

#### 2.2 TTS 合成（`bsm tts`）

```
bsm tts clone <key> <text>             # 单条克隆合成
  --emotion TEXT                       # 实时情绪指令
  --emotion-priority                   # 情绪优先模式（覆盖基础音色描述）
  --lang TEXT                          # 语言（默认 Chinese）
  --out PATH                           # 输出路径

bsm tts design <preset> <text>        # 用预设音色设计合成
  --out PATH

bsm tts dialogue <config.json>        # 批量对话合成（剧本模式）
  --dry-run                            # 仅校验配置，不生成
```

**`bsm tts clone` TUI 进度显示：**

```
● 加载模型 Qwen3-TTS 1.7B (MPS) ━━━━━━━━━━━━━━━━━━ 完成  1.2s
● 提取样音 当前参考_水烟.wav   ━━━━━━━━━━━━━━━━━━ 完成  0.3s
● 生成语音 [柔软，带着撒娇...]  ━━━━━━━━━━━━━━━━━━ 100%  3.8s
● 音频后处理                    ━━━━━━━━━━━━━━━━━━ 完成  0.1s

✓ 输出：out/水烟_柔软_20260407_143022.wav  (4.2s · 16kHz)
```

#### 2.3 预设管理（`bsm preset`）

```
bsm preset list                        # 列出 configs/presets/ 所有预设
bsm preset show <name>                 # 打印预设 JSON（语法高亮）
bsm preset create                      # 交互式 wizard 创建新预设
bsm preset run <name>                  # 执行单个预设任务
bsm preset batch [--dir DIR]           # 批量执行目录下所有预设
  --dry-run                            # 仅校验，不生成
  --filter PATTERN                     # glob 过滤（如 "王爷_*"）
```

**`bsm preset list` 输出示例：**

```
┌────────────────────────────────────────────────────────────────┐
│  预设任务库  configs/presets/                    共 52 个任务   │
├───────────────────────────┬────────┬──────────┬───────────────┤
│  预设名称                 │  模式  │  角色    │  状态         │
├───────────────────────────┼────────┼──────────┼───────────────┤
│  王爷_威严_批量设计       │ design │  王爷    │  ✓ 有配方     │
│  年轻和尚_温柔_批量设计   │ design │  年轻和尚│  ✓ 有配方     │
│  水烟_柔软_generate       │ clone  │  水烟    │  ✓ 可生产     │
│  AI女友_批量设计          │ design │  AI女友  │  ✗ 待落库     │
└───────────────────────────┴────────┴──────────┴───────────────┘
```

#### 2.4 任务历史（`bsm job`）

```
bsm job list                           # 最近 20 条生成记录
bsm job show <id>                      # 查看单条记录详情
bsm job clean                          # 清理 out/ 下 N 天前的成品
```

#### 2.5 TUI 交互界面（`bsm ui`）

```
bsm ui                                 # 启动全屏 Textual TUI
```

全屏 TUI 是所有子命令的可视化入口，见第四节详细设计。

---

## 三、技术选型

### 核心依赖

| 库 | 用途 | 版本建议 |
|---|---|---|
| `typer` | CLI 框架，子命令树 | `>=0.12` |
| `rich` | 表格、进度条、语法高亮、面板 | `>=13.0` |
| `textual` | 全屏 TUI（`bsm ui`） | `>=0.80` |

### 与现有代码的集成

```
CLI 入口（typer）
    └── bsm voice list     → 读取 configs/personas.json
    └── bsm tts clone      → core/modes/cloner.CloneMode.run()
    └── bsm tts design     → core/modes/designer.DesignMode.run()
    └── bsm tts dialogue   → core/modes/dialogue.DialogueMode.run()
    └── bsm preset run     → main.py 的任务分发逻辑（提取为函数）
    └── bsm ui             → textual.App（所有命令的 TUI 封装）
```

`main.py` 中的任务分发逻辑提取为 `core/runner.py`，供 CLI 和 TUI 共用。

### 音色注册表

路径：`~/.voxflow/configs/personas.json`（或项目内 `configs/personas.json`）

```json
{
  "shui_yan": {
    "name": "水烟",
    "ref": "assets/temp/当前参考_水烟.wav",
    "design": "voice_designs/水烟.json",
    "instruction": "极致软糯，带有慵懒撒娇的气息",
    "created_at": "2026-03-15",
    "last_used": "2026-04-07"
  }
}
```

---

## 四、全屏 TUI 界面设计（`bsm ui`）

### 4.1 布局结构

```
┌─────────────────────────────────────────────────────────────────┐
│  沸腾之雪 TTS  v0.1.0          [模型: Qwen3-1.7B · MPS]  04-07  │
├──────────────┬──────────────────────────────────────────────────┤
│              │                                                   │
│  [1] 音色库  │   音色详情 / 合成面板 / 任务输出                │
│  [2] 预设库  │                                                   │
│  [3] 任务    │                                                   │
│  [4] 日志    │                                                   │
│              │                                                   │
├──────────────┴──────────────────────────────────────────────────┤
│  > 输入命令或按数字键导航             [q]退出  [?]帮助  [r]刷新  │
└─────────────────────────────────────────────────────────────────┘
```

### 4.2 各面板说明

**音色库面板**
- 左侧：音色列表（可键盘上下导航）
- 右侧：选中音色的详情（基础指令、样音状态、最近生成记录）
- 操作：`a` 新增、`d` 删除、`p` 预听、`Enter` 进入合成

**合成面板**（从音色库进入）
- 文本输入框（支持多行）
- 情绪指令输入
- 模式切换（克隆 / 设计）
- 实时进度条
- 输出路径显示

**预设库面板**
- 预设列表（支持 glob 过滤）
- 右侧预设 JSON 预览（rich 语法高亮）
- 操作：`r` 执行、`b` 批量执行、`c` 创建

**任务面板**
- 最近 50 条生成记录（时间、角色、时长、路径）
- 支持翻页和关键词过滤

### 4.3 快捷键

| 按键 | 功能 |
|---|---|
| `1-4` | 切换主面板 |
| `↑↓` | 列表导航 |
| `Enter` | 确认 / 进入详情 |
| `n` | 新建（上下文感知） |
| `d` | 删除选中项 |
| `p` | 预听音色 |
| `r` | 执行选中任务 |
| `q` | 退出 |
| `?` | 帮助面板 |
| `Ctrl+C` | 中断当前生成 |

---

## 五、目录结构规划

新增文件，现有 `core/` 不动：

```
voxflow/
├── cli/                         # 新增：CLI 主体
│   ├── __init__.py
│   ├── app.py                   # typer App 定义，子命令注册
│   ├── commands/
│   │   ├── voice.py             # voice voice 子命令组
│   │   ├── tts.py               # voice tts 子命令组
│   │   ├── preset.py            # voice preset 子命令组
│   │   └── job.py               # voice job 子命令组
│   └── tui/                     # voice ui 全屏界面
│       ├── app.py               # textual.App 主类
│       ├── screens/
│       │   ├── voice_screen.py  # 音色库面板
│       │   ├── preset_screen.py # 预设库面板
│       │   └── job_screen.py    # 任务历史面板
│       └── widgets/
│           ├── progress.py      # 自定义进度条组件
│           └── voice_card.py    # 音色卡片组件
├── core/
│   ├── runner.py                # 新增：从 main.py 提取的任务分发逻辑（CLI+TUI 共用）
│   ├── engine.py
│   ├── processor.py
│   ├── utils.py
│   └── modes/
│       ├── cloner.py
│       ├── designer.py
│       └── dialogue.py
├── main.py                      # 保留（向后兼容旧用法）
└── pyproject.toml               # 注册 bsm 入口点
```

### `pyproject.toml` 新增入口点

```toml
[project.scripts]
bsm = "cli.app:app"
qwen-tts-demo = "qwen_tts.cli.demo:main"  # 保留原有
```

---

## 六、实现优先级

### Phase 1：基础 CLI（1-2 天）

- [x] `cli/app.py` — typer 根 app，注册子命令
- [x] `cli/commands/voice.py` — `bsm voice list/show/add/preview/rm/import`
- [ ] `cli/commands/tts.py` — `bsm tts clone`（包装 CloneMode.run）
- [ ] `core/runner.py` — 从 main.py 提取任务分发逻辑
- [x] `pyproject.toml` 注册 `bsm` 入口点

### Phase 2：完整 CLI（2-3 天）

- [x] `bsm voice add/preview/rm` ✓
- [x] `bsm tts design/dialogue` — `bsm tts clone` + `bsm tts design` 已实现 ✓
- [ ] `bsm preset list/show/run/batch`
- [ ] `bsm job list/show`
- [ ] rich 进度条 + 表格输出（tts 命令已带 Progress 进度条）

### Phase 3：全屏 TUI（3-5 天）

- [ ] `cli/tui/app.py` — textual.App 主框架
- [ ] 音色库面板（列表 + 详情）
- [ ] 预设库面板
- [ ] 合成进度面板（实时 worker 线程）
- [ ] 任务历史面板

---

## 七、安装方式

```bash
# 开发模式安装（注册 bsm 命令）
uv pip install -e .

# 验证
bsm --help

# 或直接通过 Python 运行
.venv/bin/python -m cli.app --help
```

安装后：

```bash
bsm voice list              # 查看所有音色
bsm tts clone shui_yan "她轻轻地哼了一声。"  --emotion "慵懒，带着笑意"
bsm preset run 水烟_柔软_generate
bsm ui                      # 启动全屏 TUI
```

---

## 八、与现有工作流的兼容性

`main.py` 保持不变，旧命令继续有效：

```bash
# 旧用法（保留）
python main.py clone.json

# 新用法（TUI CLI）
bsm tts clone shui_yan "..." --emotion "..."
bsm preset run clone
```

`web_api.py` 作为可选的服务端保留，可通过 `bsm server` 或 `npm run api:dev` 启动，
不是主路径，不影响 TUI 使用。
