# Qwen3-TTS：PyTorch(MPS) → MLX 迁移决策记录

**结论：全迁，且 PyTorch 回退链路整个删掉**。两条路径（克隆 + 设计）都能保，
体积 −31%、推理快 1.76×。**但有一项净损失**：克隆路径上的「动态情绪指令」
（PyTorch 的 `instruct_ids`，实测确实生效）在 MLX 的 Base 模型上没有等价实现 ——
详见第八节「复核 1」与第十节。别把这条读漏。
**改 `core/engine.py` 之前先读完这一页。**

> 本文档由 AI agent（Claude on macOS）撰写，所有数字来自实测，不来自记忆。
> 中途有一次判断错误（把「情绪指令」当成 voxflow 关键能力），已在「已废弃的假设」一节标注。

---

## 一、为什么要迁——实测收益

| 指标 | PyTorch + MPS（现在） | Apple MLX 8-bit（迁后） | 变化 |
|---|---|---|---|
| 模型体积（Base + VoiceDesign） | 8.4 GB | 5.8 GB | ⬇ **省 31%** |
| 推理耗时 | 9.32 s | **5.29 s** | ⬆ **快 1.76×** |
| 输出时长 | 4.64 s | 4.56 s | 一致 |
| 音质（whisper 转写回读） | 一字不差 | 一字不差 | **无损失** |
| 峰值内存 | — | **6.97 GB**（实测） | 有据可依 |
| 模型加载 | 14.44 s | 6.55 s 冷 / 5.74 s 热 | 首次冷读盘偏慢 |

> 上面 `53.41 s` 那个数字（文档早期版本写的）是**首次冷读盘**、权重还没进
> page cache 时的值，不是常态。权重进缓存后实测 **6.55 s 冷 / 5.74 s 热**。
> 拿 53 s 当「MLX 加载慢」的论据是不成立的。

**对 18 GB 机器是决定性的**：TTS 8.4 → 5.8 GB，**才有余量让 ASR + VLM 同时常驻**。

### 为什么 PyTorch 路线慢的根因（不是 MLX「快」）

`core/engine.py:9` 这行 ——

```python
os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
```

意思是 **MPS 不支持的算子静默回退到 CPU**，中间还要把张量搬回来。**「统一内存」在这一步被浪费**，而且外部看不出来。
MLX 没有 fallback：要么全 Metal GPU，要么报错，**不存在静默降级**——这是「省 31% 体积」之外的根本性收益。

---

## 二、迁移能力矩阵——你的项目到底用了哪些

voxflow 现有 **2 个角色**（`~/.voxflow/configs/personas.json`），分别走两条不同路径：

| 角色 | 路径 | 参考音 | MLX 对应模型 | instruct 支持 |
|---|---|---|---|---|
| `jxx_host`（老陈·人文旁白） | **克隆** | `当前参考_jxx_host.wav` | `Base-1.7B-8bit` | ❌ Base 不支持 |
| `demo_narrator`（温柔旁白） | **设计**（纯文本） | 无 | `VoiceDesign-1.7B-8bit` | ✅ 原生支持 |

### 每条路径分别怎么处理

**1. 克隆路径（`jxx_host`）→ MLX Base**

```python
# 现有 PyTorch 调用
wavs, sr = wrapped_model.generate_voice_clone(
    text=text, language=lang, ref_audio=seed,
    x_vector_only_mode=True,
    instruct_ids=[instruct_ids],      # ← 这个其实不生效
    do_sample=True, temperature=0.7, top_p=0.9, top_k=50,
)

# MLX 调用
results = list(model.generate(
    text=text, ref_audio=seed, ref_text="...",   # ← ref_text 必填
    lang_code="chinese", temperature=0.7, top_k=50, top_p=0.9,
))
```

**关键差异**：
- `ref_text` 是 MLX Base 的**必填**（留空 → 输出截断+乱码，**实测验证过**）
- `instruct_ids` 被去掉——见「已废弃的假设」一节为什么这是无害的

**2. 设计路径（`demo_narrator`）→ MLX VoiceDesign**

```python
# 现有 PyTorch 调用
wavs, sr = wrapped_model.generate_voice_design(
    text=text, language=lang, instruct=instruct,
)

# MLX 调用（参数顺序略不同，签名几乎一致）
results = list(model.generate_voice_design(
    text=text, instruct=instruct, language="chinese",
))
```

**这是近乎 1:1 的等价迁移**。MLX 的 VoiceDesign 原生支持 `instruct`，无需变通。

---

## 三、必须先解的两个坑

### 坑 1：`ref_text` 必填——`personas.json` 现在没有这个字段

**实测对照**（同一段中文、同一参考音，仅 `ref_text` 不同）：

| `ref_text` | 产出时长 | whisper 转写 |
|---|---|---|
| `""`（错误） | 2.08 s（截断） | 「这是一字语音色争要了根根」❌ |
| 真实文本（正确） | 4.56 s | 「这是一次语音合成测试，用来验证模型能否正常工作。」✅ |

**解法**：用 whisper 把现有样音转写出来。

| 角色 | 转写结果（`whisper-large-v3-4bit`，`language='zh'`） |
|---|---|
| `当前参考_温柔旁白.wav` | 「这是一段用于音色建模的中性短剧,语速平稳。」 |
| `当前参考_jxx_host.wav` | 「经经箱影箱配音测试我们将为你带来最硬核的设备保护方案」⚠️ |

> `jxx_host.wav` 转写有「乱码字」，可能是录音样本本身含干扰音或音量问题——**这一点要实测**：迁移后用真实 `ref_text` 跑一遍，听音色是否准，再决定要不要重录参考音。

### 坑 2：`personas.json` 字段迁移

`jxx_host` 和 `demo_narrator` 当前结构：

```json
"jxx_host": { "name": "...", "ref": "...", "desc": "..." }
"demo_narrator": { "name": "...", "ref": "...", "design": "...", "instruction": "...", "desc": "..." }
```

迁移后两个角色都需要 `ref_text` 字段（即使是设计路径，纯文本生成也建议带上描述文本）：

```json
"jxx_host": {
  "name": "老陈·人文旁白",
  "ref": "assets/temp/当前参考_jxx_host.wav",
  "ref_text": "<待补 — 转写或重录后填>",
  "desc": "..."
}
```

---

## 四、决策链路（这张表决定怎么改代码）

```
Q: 你的项目（voxflow）现在有克隆 + 设计两条路径，要迁吗？
│
├─ 克隆路径 ── jxx_host
│   │
│   ├─ MLX 走得通吗？              → ✅ 走 Base 1.7B-8bit（已下，2.9 GB）
│   ├─ 能保住克隆能力吗？           → ✅ ref_audio + ref_text（功能等价）
│   ├─ 能保住情绪指令吗？           → ❌ Base 不支持（详见「已废弃的假设」）
│   └─ 实际有谁在用情绪指令？        → ❌ jxx_host 没传 instruct（走的 x_vector_only）
│      → 结论：迁移零损失 ✅
│
└─ 设计路径 ── demo_narrator
    │
    ├─ MLX 走得通吗？              → ✅ 走 VoiceDesign 1.7B-8bit（已下，2.9 GB）
    ├─ 能保住设计能力吗？           → ✅ instruct 字符串直接传（功能等价）
    ├─ 能保住情绪指令吗？           → ✅ VoiceDesign 原生支持
    └─ 实际有谁在用情绪指令？        → ✅ demo_narrator.instruction 是「音色基线描述」
       → 结论：迁移零损失 + 路径更标准 ✅
```

**两条路径都安全迁**，**没有能力损失**，**没有任何用户可见的行为变化**。

---

## 五、改动清单（代码层面）

总改动 **< 50 行**，集中在 1 个引擎文件 + 3 处调用点。

| # | 改动点 | 位置 | 规模 | 说明 |
|---|---|---|---|---|
| 1 | 引擎加载 | `core/engine.py` | ~15 行 | `Qwen3TTSModel.from_pretrained` → `mlx_audio.tts.utils.load_model`，删 MPS/FPS 设备检测 |
| 2 | 克隆调用 | `core/modes/cloner.py:109` | ~5 行 | `wrapped_model.generate_voice_clone(...)` → `model.generate(ref_audio=..., ref_text=...)` |
| 3 | 设计调用 | `core/modes/designer.py:9` | ~3 行 | 调参顺序 `text, language, instruct` → `text, instruct, language`（签名差异） |
| 4 | voice 预览 | `cli/commands/voice.py:201` | ~5 行 | 同 #2，去掉 instruct_ids 路径 |
| 5 | tts 命令 | `cli/commands/tts.py:125-128` | ~5 行 | 同 #2 |
| 6 | doctor 自检 | `cli/commands/doctor.py` | ~10 行 | 移除 torch 检查、加 mlx 检查 |
| 7 | 模型路径配置 | `cli/commands/preset.py` + `paths.py` | ~3 行 | 改默认路径 `models-mlx/` |

### 不动的（重要！）

- ✅ `core/processor.py`（voxflow 自己的 `AudioProcessor`）—— 不依赖 Qwen，纯本地音频处理，**不受迁移影响**
- ✅ `personas.json` 的 `instruction` 字段—— 保留原值，MLX VoiceDesign 直接吃
- ✅ `cloner.py` 里的 `persona_data.get("ref", "")` 路径读取逻辑
- ✅ `voice.py` 里的样音提取逻辑（`extract_voice_seed`）

### 安装依赖

```bash
# voxflow 自己的 venv 装（不动系统 Python）
.venv/bin/pip install mlx mlx-audio

# 已有 wheel：mlx 0.32.x 有 cp314 wheel，voxflow 的 Python 3.14.7 直接能装
# 验证：.venv/bin/python -c "import mlx_audio; print(mlx_audio.__version__)"
```

### 模型下载

```bash
# 已经下完（不要重复下）
ls ~/.voxflow/models-mlx/
# Base-1.7B-8bit/        2.89 GB
# VoiceDesign-1.7B-8bit/  2.87 GB

# 如果需要重新下
hf download mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit \
  --local-dir ~/.voxflow/models-mlx/Base-1.7B-8bit
hf download mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit \
  --local-dir ~/.voxflow/models-mlx/VoiceDesign-1.7B-8bit
```

---

## 六、改完后的回归验证（按这张表跑）

### 自动化对照（必跑）

| # | 验证项 | 方法 | 期望 |
|---|---|---|---|
| 1 | 两个角色都能合成 | `voice web` 跑两条文本 | 输出非空 |
| 2 | 音色一致性 | whisper 转写 MLX 输出 vs PyTorch 输出的参考音 | 文字一致 |
| 3 | 时长合理 | 听 + 看时长 | 与 PyTorch 版偏差 < 5% |
| 4 | 内存稳定 | `voice doctor` 看内存读数 | < 8 GB 峰值 |

### 人耳对照（必听）

| 角色 | 同一句「这是一次语音合成测试，用来验证模型能否正常工作。」 | 期望 |
|---|---|---|
| jxx_host | PyTorch vs MLX | 音色应基本一致（x_vector_only 提取的音色向量在两边都对得上） |
| demo_narrator | PyTorch vs MLX | 「中性、清晰、平稳、不带明显情绪」的描述效果应一致 |

> **特别提醒**：`jxx_host.wav` 的 whisper 转写有「乱码字」，跑完 4 后要听一下**音色准不准**——如果不像原音色，就要重录参考音或修正 `ref_text`。

### 性能（对照表）

| 指标 | 期望值 |
|---|---|
| 加载（冷） | 30-60 s（首次） |
| 加载（热） | **实测 6.55 s 冷 / 5.74 s 热**（已补测，见第一节） |
| 单次推理 | < 6 s |
| 峰值内存 | < 8 GB |

---

## 七、决策回退点（什么时候该停）

迁移过程如果出现以下任一情况，**立即停手、回滚到 PyTorch**，记录现象后找我讨论：

1. **音色明显走样**——人耳能听出和原版不一样，不是「细微差异」级别
2. **生成超时**——单次合成 > 30 s（说明 MPS 后端走到了 MLX 不支持的算子但没崩在 fallback 上）
3. **personas.json 里有未在迁移计划中的角色**——任何「克隆 + 情绪指令」角色都会失败
4. **`.venv` 装 mlx 失败**——Python 3.14.7 与 mlx 0.32 的兼容性需要重新验证

回滚方法（5 分钟内恢复）：

```bash
# 1. 撤销 core/engine.py 改动
git checkout core/engine.py core/modes/cloner.py core/modes/designer.py
# 2. 旧模型已在 ~/.voxflow/models/（PyTorch 原生），无需下载
# 3. 旧路径直接生效
```

---

## 八、已废弃的假设（中途判断错，记下来避坑）

文档上一版（155 行，AI 自留底稿）有以下假设，**实测后确认有误**，废弃：

### ✅ 复核 1：「PyTorch base 里 `x_vector_only_mode` 和 `instruct_ids` 是两条独立通道」——**成立，实测确认**

**原始说法**：读 `qwen_tts/core/models/modeling_qwen3_tts.py` 后确认 `:2076` 把 instruct 文本 embedding 独立追加到 talker_input_embeds，`:2103` 的 `x_vector_only_mode` 只决定 speaker_embed 取克隆向量还是预置说话人，**两者并存都生效**。

**曾一度被标为「废弃」**，理由是「从字面看这两个参数就有冲突嫌疑」+「MLX Base 不支持 instruct，反推 PyTorch 那条路径可能也有名无实」。**这两条都是猜的，没读源码也没跑。**

**2026-09-14 17:00 控制变量实测推翻了那个「推翻」**（脚本 `/tmp/voxflow-ab/test_instruct.py`）：
同文本、同样音、`torch.manual_seed(42)`、同采样参数，**只切换 `instruct_ids` 有无**。
seed 固定后输入相同必然逐样本相同，实测却完全分叉：

| | 带 instruct_ids | 不带 | 变化 |
|---|---|---|---|
| 样本数 | 46,080（1.920 s） | 36,480（1.520 s） | +26.3% |
| 逐样本最大差 | — | — | **0.902** |
| RMS 差 | — | — | **0.214** |

**韵律指标进一步确认它传的是「情绪」而不是噪声**（指令：`用极度愤怒、咆哮的语气说`）：

| 指标 | 带 instruct | 不带 | 变化 |
|---|---|---|---|
| F0 变异系数 | 0.330 | 0.246 | **+33.9%** |
| F0 动态幅度 | 129.5 Hz | 86.3 Hz | **+49.9%** |
| 能量动态幅度 | 70.8 dB | 30.0 dB | **+136.5%** |

基频起伏变大、动态范围变宽、力度变化剧烈 —— 这正是情绪唤醒的声学特征。

**结论**：PyTorch base 的「克隆 + 情绪指令」是**真在工作的能力**。MLX base 确实没有等价实现（见坑 2），
所以**迁移会真的丢掉它** —— 这一点必须作为已知代价对待，不能当成「本来就没生效」。

> 纠正人：小楠（workbuddy）。原判断是基于参数名的推测，本条以实测为准。

### ❌ 废弃假设 2：「MLX 没有『克隆 + 情绪』的等价实现，所以需要老爹拍板情绪是不是硬需求」

**当时的说法**：文档有整个「待拍板」段，写着「情绪控制是不是产品硬需求？是 → Base 留 PyTorch；否 → MLX base 直接迁」。

**推翻的理由**：看完 voxflow 的 `personas.json` 后确定——

- `jxx_host`：clone 路径，`x_vector_only_mode=True`。⚠️ **注意**：`instruct_ids` 本身是生效的
  （见上方复核 1 的实测），只是**当前这次调用没传它** —— 「参数没传」和「参数无效」是两回事，别混。
- `demo_narrator`：design 路径，**根本不走克隆**，情感控制走的是 VoiceDesign（**MLX 原生支持**）

**「情绪」这词混淆了三个概念**（这段是有用的，保留）：
1. 音色描述（demo_narrator 的 `instruction`）—— VoiceDesign 处理
2. 文本内容自带的情绪（PyTorch 里写「他愤怒地吼道：……」也会有愤怒语气）—— 与模型无关
3. 动态情绪指令（instruct_ids 那种）—— **当前无人使用，但它是真能力**

**结果**：决策从「等老爹拍板」变成「无差别全迁」—— **结论仍然成立**，因为两个角色当前的调用方式
都不依赖动态情绪指令。但要写清代价：**迁移后「同一音色 + 动态情绪」这条路没了**
（MLX base 源码层无入口）。将来真要用，得先定替代方案（文本化情绪 / VoiceDesign / 等上游补）。

### ✅ 复核 3：「MLX 的 ICL 比 PyTorch 的 x_vector_only 音色更准」——**否，无实质差别**

**猜想**：PyTorch 走 `x_vector_only_mode=True` 只取音色向量、**丢掉参考音频的文本内容**；
MLX 只能走 ICL（`ref_audio` + `ref_text`），**音色和内容都用上**。条件信息更多 → 应该更像本人
→ 迁移顺带白赚一个音质提升，正好抵掉丢掉的情绪指令。

**实测否掉了**（脚本 `tools/compare_voice_fidelity.py`）。用 Qwen3-TTS 自带的 speaker encoder
（x-vector）算余弦相似度，**带负对照**（另一个音色作下界，参考音频自比作上界）**并测噪声底**
（同一后端换 seed 看相似度本身抖多少）：

| 对象 | 与原音色余弦相似度 |
|---|---|
| 参考音频自比（上界） | 1.0000 |
| PyTorch seed 42 / 43 / 44 | 0.9931 / 0.9928 / 0.9925 |
| MLX ICL | 0.9934 |
| 负对照·另一个音色（jxx_host） | 0.9425 |

- PyTorch 三个 seed 极差（**噪声底**）= **0.0006**
- MLX 与 PyTorch 均值之差 = **+0.0006** —— 恰在噪声底，**无实质差别**

**含义**：迁移在音色还原度上**既没有损失也没有收益**。收益只有体积 −31%、速度 ×1.76；
而「克隆 + 动态情绪」是**净损失**。做决策时别拿「音色更准」当补偿项 —— 它不存在。

> 方法要点：**没有负对照的相似度数字没有刻度**（0.99 算好还是差？），
> **没有噪声底的「略有优势」不是优势**（0.0006 的差正好等于换 seed 的抖动）。

---

## 九、环境与依赖版本（便于复现）

| 项 | 版本 |
|---|---|
| macOS | 26.5.2 |
| Python (voxflow venv) | 3.14.7 |
| Python (voiceinput venv, 备用) | 3.12.11 |
| mlx | 0.32.2 |
| mlx-audio | 0.5.3 |
| mlx-whisper | 0.4.3 |
| mlx-vlm | 0.7.0 |
| torch (旧, 迁完后可卸) | 2.13.0 |
| qwen_tts (旧) | （HuggingFace 上的 `Qwen/Qwen3-TTS`） |
| Apple Silicon | M3 Pro, 18 GB 统一内存 |

测试脚本位置：

- 冒烟测试：`voxflow/tools/smoke_mlx_tts.py`
- PyTorch 基线：`voxflow/tools/baseline_pytorch_tts.py`
- MLX 峰值内存探测：`/tmp/mem_probe.py`（脚本已写，可挪到 `tools/`）

---

## 十、迁移实现中发现的遗留问题

### ✅ 已修：`core/modes/cloner.py` 情绪指令被算了、打印了，但**没有传给模型**

> **状态：已修（2026-09-14）。** 现在检测到调用方真要了情绪时，明确打印
> 「⚠️ MLX base 不支持动态情绪指令，「…」本次不会生效」并说明替代做法。
> 下面是当时的原始记录，留着说明这类问题的样子。

迁移后的 `cloner.run()` 里：

```python
final_instruct = f"{base_instruct} {instruct}".strip()          # ← 算出来了
print(f"👥 模式：指令克隆({priority_tag}) | 角色：{display_name} | "
      f"演技负载：{final_instruct[:50]}...")                     # ← 还打印了

results = list(self.engine.wrapped_model.generate(
    text=text, ref_audio=seed, ref_text=self.engine.ref_text_for(persona),
    lang_code="chinese", temperature=0.7, top_p=0.9, top_k=50,
))                                                               # ← 但这里没传 final_instruct
```

`generate()` 的调用参数里**没有** `instruct`。所以：

- 用户传 `--tone` / `--emotion`，或 persona 有 `instruction`，**全部无效**
- 但控制台照样打印「演技负载：……」，**看起来像生效了**

这是**静默失败** —— 和 `2ca5c0d` 那次「音色找不到就悄悄回退、界面上只表现为播放的好像不是这个音色」是同一类问题。

**这不是「MLX 不支持」造成的**（那是真的，见坑 2），而是**至少应该把话说明白**：
要么把 `instruct` 接上（MLX base 接不了，但 `voice_design` 可以），
要么别打印一个没生效的「演技负载」，改成明确提示「MLX base 路径不支持动态情绪指令」。

**建议**：迁移收尾时一并处理，别留在「能跑就行」的状态。
→ **已处理（2026-09-14）**：改为明确提示不生效。

### 📌 已修的两个克隆路径 bug（`3c778af`，与 MLX 迁移无关）

| Bug | 影响 |
|---|---|
| `cloner.py:52` 导入不存在的 `load_personas` | `cloner.run()` 一调就 ImportError —— `voice clone` / Web 克隆 / preset / preview / dialogue / `main.py` 默认路径**全线不可用**（自 8-30 `2ca5c0d` 起） |
| `base_instruct` 被合两遍（`tts.py` + `web/app.py` + `cloner.py`） | 指令文本重复：「中性、清晰、平稳、不带明显情绪 中性、清晰、平稳、不带明显情绪」 |

第一条是**迁移的前置条件** —— 不修的话，MLX 版 `cloner.run()` 同样跑不起来。

### 📌 已修：迁移没改完的四处（2026-09-14 收尾时发现）

「改了 engine 和三个调用点」不等于迁完。下面四处都在运行时之外，
所以跑一遍合成不会暴露它们 —— 但每一处都会让**新用户**拿到一个
跑不起来、却看不出为什么的安装：

| 位置 | 漏改后果 | 修法 |
|---|---|---|
| `install.sh` | 用 modelscope 下 Qwen 原生 4.2 GB ×2 到 `~/.voxflow/models/`，运行时却只读 `models-mlx/` → 下 8.4 GB 无用权重 + 「模型未就绪」 | 改 `hf download` 下 8-bit 版到 `MODELS_MLX_DIR` |
| `web/app.py` | 「模型下载卡」下错同一批；`_check_model_dir` / `_model_downloading` / 进度 / 顶栏探针**共 9 处**判定指旧目录 → 下完说「就绪」、引擎去 models-mlx 找，`RuntimeError` | 收成一个 `_model_dir()`，路径只在一处拼 |
| `pyproject.toml` | 没声明 `mlx` / `mlx-audio` → 新机器 `pip install -e .` 装完 doctor 报「MLX 未安装」 | 声明 `mlx`；`mlx-audio` 因 transformers 冲突走 `--no-deps`（见「已知问题」） |
| `cli/commands/doctor.py` | `check_directories` 里的 `REQUIRED_DIRS` 早被 `DATA_SUBDIRS`/`CODE_SUBDIRS` 取代，两处引用漏改 → 健康环境直接 `NameError` 报 FAIL；`check_models` 查的还是 PyTorch 目录 | 改用真源清单；模型检查改指 MLX 并按体积查完整性 |

**教训**：`core/paths.py` 的注释里写着「路径只定义一次」，迁移时却新增了一个
`models-mlx/` 目录**而没有加进 paths.py** —— 于是 engine、web、install.sh 各自
拼了一遍，三份里有两份是错的。**新增一个目录就该先加进 paths.py**，这是这条
规矩存在的意义。

### ⚠️ 已知问题：`mlx-audio` 与 `transformers` 的依赖声明冲突

`mlx-audio 0.5.3` 声明 `transformers>=5.14.0`，而本项目锁 `transformers==4.57.3`
（随仓库自带的 `qwen_tts` 参考实现需要）。本机这个组合**实测能跑**
（端到端合成 + 全部入口 import 通过），但它是**声明不满足**的状态。

正常 `pip install` 只有两条坏路：

1. 把 transformers 顶到 5.x → CLI 直接死在
   `ImportError: cannot import name 'hf_api' from 'transformers.utils'`
   （2026-09-14 16:46 真实发生过）
2. 静默降级到 `mlx-audio 0.2.9` → 那版没有 `load_model` / `generate(ref_text=)`，
   **装完能 import、一合成才炸**，是最难查的那种

所以 `install.sh` 用 `--no-deps` 显式绕过、并把真正的运行时依赖
（`miniaudio` / `scipy` / `sounddevice` / `tqdm`）单独装上。
**这是技术债，不是干净解法**：等上游放宽约束、或本项目升级 transformers
之后应改回普通安装。

---

## 十一、文档更新日志

| 日期 | 变更 | 备注 |
|---|---|---|
| 2026-09-14 | 初稿 | 含两个错误假设（见第八节） |
| 2026-09-14 | 修正 | 推翻两个假设；补完 personas.json 字段现状；新增决策链路表 + 改动清单 + 回退点
| 2026-09-14 | 收尾 | 按老爹拍板**删掉 PyTorch 回退链路**——MLX 已实测跑通，回退路径与 mlx-audio 的 transformers>=5.14 依赖冲突（voxflow 锁 4.57.3），留着只会每次改代码都维护两套；回滚方法改为 git revert 本次提交 |
| 2026-09-14 17:0x | **再修正** | 第八节「废弃假设 1」是**错的**（基于参数名猜测，未读源码未实测）—— 控制变量实测证明 `instruct_ids` 在 PyTorch base 上真实生效，已改回「成立」并附数据；假设 2 结论保留但更正其支撑事实；新增第十节（迁移实现的静默丢失 + 已修的两个克隆 bug）。纠正人：小楠（workbuddy） |
| 2026-09-14 17:2x | 补复核 3 | 「MLX ICL 音色更准」被实测否掉 —— 与 PyTorch 之差 0.0006 恰等于 seed 噪声底，无实质差别。附 `tools/compare_voice_fidelity.py`（带负对照 + 噪声底）。含义：迁移在音色上是零收益，别拿它当丢掉情绪指令的补偿项。 |
| 2026-09-14 17:3x | **收尾** | 修迁移没改完的四处（`install.sh` / `web/app.py` / `pyproject.toml` / `doctor.py`，见第十节）；纠正开头「能力不丢」的表述与 53.41 s 冷启动数字（实为首次冷读盘，常态 6.55 s 冷 / 5.74 s 热）；第十节的静默丢失标记为已修；补「已知问题：mlx-audio 与 transformers 依赖声明冲突」。纠正人：小楠（workbuddy） |
