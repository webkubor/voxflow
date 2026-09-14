# Qwen3-TTS：PyTorch(MPS) → MLX 迁移决策记录

**结论：不要整块切。** 先只迁 VoiceDesign（等价迁移、零损失），Base 等一个实验做完再定。

本文记的是**查证过的事实**，不是推断。改 `core/engine.py` 之前先读完这一页。

---

## 为什么要换

现在走 `Qwen3TTSModel.from_pretrained` + MPS，但 `core/engine.py:9` 那行
`PYTORCH_ENABLE_MPS_FALLBACK = "1"` 意味着 **MPS 不支持的算子会静默回退 CPU**，
中间还要把张量搬回来 —— 「统一内存」被浪费在这里，而且外部看不出来。
MLX 没有 fallback：要么全 GPU，要么报错，不存在静默降级。

实测收益（同一段中文文本，同一参考音频）：

| 指标 | PyTorch + MPS | MLX 8-bit | 变化 |
|---|---|---|---|
| 模型体积（两模型合计） | 8.4 GB | 5.8 GB | ⬇ 省 31% |
| 推理耗时 | 9.32 s | 5.29 s | ⬆ 快 1.76× |
| 输出时长 | 4.64 s | 4.56 s | 一致 |
| 音质（whisper 转写回读） | 一字不差 | 一字不差 | 无损失 |
| 峰值内存 | — | 6.97 GB（实测） | 有据可依 |
| 冷启动加载 | 14.44 s | 53.41 s | ⚠️ MLX 慢（未做热缓存复测） |

对 18 GB 机器是决定性的：TTS 8.4 → 5.8 GB，才有余量让 ASR + VLM 同时常驻。

---

## 能力矩阵（这张表决定「值不值得」）

| 模型类型 | 克隆音色 | 情绪指令 `instruct` |
|---|---|---|
| **PyTorch Base**（现在用） | ✅ `x_vector_only_mode` 或 ICL | ✅ `instruct_ids`，**独立通道** |
| MLX `base` | ✅ 只能走 ICL（`ref_audio` + `ref_text`） | ❌ **源码层无入口** |
| MLX `voice_design` | ❌ 不克隆 | ✅ 支持 |
| MLX `custom_voice` | ❌ 只能预置说话人 | ✅ 支持（`voice` + `instruct`） |

**关键：MLX 目前没有「克隆你自己的声音 + 加情绪指令」的等价实现。**
voxflow 的 `CloneMode` 正是干这个的（`main.py:87` 默认走它），所以这不是无损迁移。

---

## 两条容易搞错的事实

### 1. PyTorch 里 `x_vector_only_mode` 与 `instruct_ids` **不冲突**

曾经怀疑这两个参数互斥（`x_vector_only` 字面意思就是「只用音色向量、不用文本内容」）。
读 `qwen_tts/core/models/modeling_qwen3_tts.py` 后确认是**两条独立路径**：

- `:2076` 把 instruct 的文本 embedding 独立追加到 `talker_input_embeds`
- `:2103` 的 `x_vector_only_mode` 只决定 `speaker_embed` 取克隆向量还是预置说话人

**两者并存，都生效。** 所以现在的「指令克隆」（音色来自样音 + 情绪来自 instruction）
是真在工作的功能，迁移会真的丢掉它。

### 2. MLX base 丢 instruct 是**源码层面**的，不是配置问题

`mlx_audio/tts/models/qwen3_tts/qwen3_tts.py`：

- base 分支调 `_prepare_generation_inputs(...)` 时**不传** `instruct`（该参数默认 `None`）
- ICL 克隆路径 `_generate_icl()` 的签名里**根本没有** `instruct` 参数

所以改配置救不回来。要么接受损失，要么给上游提 PR。

---

## 两个必须先解的坑

### 坑 1：`ref_text` 必填（MLX base 的 ICL 模式）

留空会**截断 + 乱码**。实测对照：

| `ref_text` | 产出时长 | whisper 转写 |
|---|---|---|
| `""`（错误） | 2.08 s（截断） | 「这是一字语音色争要了根根」❌ |
| 真实文本（正确） | 4.56 s | 「这是一次语音合成测试，用来验证模型能否正常工作。」✅ |

而且正确版更快（5.29 s vs 10.31 s）。
`~/.voxflow/configs/personas.json` 目前**没有** `ref_text` 字段，需要补。
解法已有：用 whisper 转写样音得到文本，例如
「这是一段用于音色建模的中性短剧,语速平稳。」

### 坑 2：情绪指令在 MLX base 上失效

见上方能力矩阵。要老爹拍板怎么走。

---

## 迁移改动面（不到 50 行）

| 改动点 | 位置 | 规模 |
|---|---|---|
| 引擎加载 | `core/engine.py` | ~10 行（换 `from_pretrained`） |
| 推理调用 | `core/modes/cloner.py:109`、`core/modes/designer.py:9`、`cli/commands/voice.py:201` | 3 处 API 映射 |
| 设备检测 | `core/engine.py` 的 `_detect_device()` | 整段删掉（MLX 无 device/dtype 概念） |
| doctor 自检 | `cli/commands/doctor.py` | ~15 行 |
| 散点 | `paths.py` / `tts.py` / `preset.py` | 各 1-3 行 |

好消息：`mlx_audio` 的 `generate_voice_design(text, instruct, language)` 与现有
`generate_voice_design(text, language, instruct)` **签名几乎一致**，是等价迁移。
`generate()` 收 `ref_audio` 为文件路径，与 `cloner.py` 里的 `seed = ref_audio` 也对得上。
`mlx_audio` 内部已把 instruct 包成 `<|im_start|>user\n{instruct}<|im_end|>\n`，
与 `cloner.py:98` 手工包的一致，可以直接传字符串。

另外注意：代码里有**两个 processor**，别搞混 ——
`engine.processor` 是 Qwen 的 tokenizer（只用来做 `instruct_ids`，**受迁移影响**）；
`core/processor.py` 的 `AudioProcessor` 是自己的（提取样音、后处理，**不受影响**）。

---

## 环境

`mlx 0.32.2` 有 `cp314` wheel，voxflow 的 Python 3.14.7 直接能装：

```bash
.venv/bin/pip install mlx mlx-audio
```

不用另开 3.12 环境。（另有一份 MLX 环境在 `~/.local/share/voiceinput-models/.venv`，
Python 3.12，含 mlx / mlx_audio 0.5.3 / mlx_vlm / mlx_whisper，是 voiceinput 项目的。）

---

## 推荐路径

**① 先只迁 VoiceDesign** —— 零风险，等价迁移，顺手拿到 31% 体积和 1.76× 速度。

**② 补「情绪 + 音色」双 AB 实验** —— 现有对比有个缺口：测试文本是中性陈述句
（「这是一次语音合成测试，用来验证模型能否正常工作」），**完全没测情绪**，
所以「情绪丢了有没有影响」现有数据一个字都答不了。要补两组：

- **情绪**：同一段带明显情绪的文本，PyTorch base vs MLX base 各跑一遍，人耳听
- **音色**：MLX 的 ICL 用上了 `ref_text` 的内容，**可能比现在的 `x_vector_only` 更准**
  （信息量更大）。同一句话比「像不像原音色」，值得单独测

**③ 实验后再定 Base 去留。**

还有一条备选路：**情绪改走文本**。TTS 对文本本身是敏感的，
写「他愤怒地吼道：……」比传 `instruct_ids` 更自然，且零迁移成本。
如果这条路走通，「掉 instruct」就不算损失。这个也要在实验里一起验。

---

## 待拍板

**情绪控制是不是产品硬需求？**

- 是 → Base 留 PyTorch（或等 MLX 上游补 `_generate_icl` 的 instruct 入口）
- 否 → MLX base 直接迁，还顺带升级音色还原度

参考：目前 `personas.json` 只有 2 个角色，唯一带 `instruction` 的是
`demo_narrator`，写的是「中性、清晰、平稳、不带明显情绪」—— **音色基线描述，
不是情绪控制**。没有任何角色在做动态情绪。损失面比看起来小得多。
