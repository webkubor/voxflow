# MLX 迁移改动 Checklist（给执行的 agent）

> 配套 `MLX_MIGRATION.md` —— 读那个理解「为什么」，照这个执行「改什么」。
> 每改一项就勾一项，改完跑 `tools/smoke_mlx_tts.py` + `tools/baseline_pytorch_tts.py` 对比。

## 前置（必做）

- [ ] 装 mlx + mlx-audio 到 voxflow 自己的 venv
  ```bash
  cd ~/dev/github/app/voxflow
  .venv/bin/pip install mlx mlx-audio
  .venv/bin/python -c "import mlx_audio; print(mlx_audio.__version__)"
  # 应输出 0.5.3 或更新
  ```
- [ ] 确认两个模型已下载到 `~/.voxflow/models-mlx/`
  ```bash
  ls ~/.voxflow/models-mlx/
  # 期望：
  # Base-1.7B-8bit/        2.89 GB
  # VoiceDesign-1.7B-8bit/  2.87 GB
  # 缺哪个就下哪个
  ```
- [ ] 跑一次冒烟测试，确认 MLX 版能正常发声
  ```bash
  .venv/bin/python tools/smoke_mlx_tts.py \
    ~/.voxflow/models-mlx/Base-1.7B-8bit \
    ~/.voxflow/assets/temp/当前参考_温柔旁白.wav
  # 期望：~10s 生成 ~4.5s 音频，输出到 ~/.voxflow/out/mlx-smoke/
  ```

## 改 `core/engine.py`（最关键的一处）

- [x] 把 `from qwen_tts import Qwen3TTSModel` 换成 `from mlx_audio.tts.utils import load_model`
- [ ] 删除 `os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"`（MLX 不需要 fallback）
- [ ] 删除 `import torch`
- [ ] 把 `self.wrapped_model = Qwen3TTSModel.from_pretrained(...)` 换成
  ```python
  # 按路径后缀自动选 VoiceDesign 还是 Base（也可拆成两个独立 engine）
  self.wrapped_model = load_model(model_path)
  self.model_type = getattr(self.wrapped_model.config, "tts_model_type", "base")
  ```
- [ ] 删除整个 `_detect_device()` 方法（MLX 无 device 概念）
- [ ] 删除 `self.device` / `self.dtype` 字段
- [ ] 把 `self.processor = self.wrapped_model.processor` 整段删掉（MLX 无独立 processor）

**目标**：engine 暴露的方法变成
- `self.wrapped_model`（MLX 的 model 实例）
- `self.model_type` 字符串，cloner 和 designer 据此分流
- `self.base_dir`（保留，纯逻辑路径）

## 改 3 处调用点

### 1. `core/modes/cloner.py:109`

```python
# 改前
wavs, sr = self.engine.wrapped_model.generate_voice_clone(
    text=text, language=lang, ref_audio=seed,
    x_vector_only_mode=True,
    instruct_ids=[instruct_ids],
    do_sample=True, temperature=0.7, top_p=0.9, top_k=50,
)
return wavs, sr

# 改后
results = list(self.engine.wrapped_model.generate(
    text=text,
    ref_audio=seed,                       # seed 是文件路径，直接传
    ref_text=self.engine.ref_text_for(persona),   # 新增方法，下面定义
    lang_code="chinese",
    temperature=0.7, top_k=50, top_p=0.9,
))
audio = results[0].audio   # mx.array
sr = self.engine.wrapped_model.sample_rate
return [np.asarray(audio)], sr
```

**新增 engine 方法**（在 `core/engine.py`）：
```python
def ref_text_for(self, persona_key: str) -> str:
    """从 personas.json 取 ref_text；缺失抛清晰错误，让用户知道要补。"""
    from ..utils import get_persona_map
    m = get_persona_map().get(persona_key, {})
    txt = (m.get("ref_text") or "").strip()
    if not txt:
        raise RuntimeError(
            f"persona '{persona_key}' 缺少 ref_text；先用 whisper 转写 {m.get('ref')} 后填回 personas.json"
        )
    return txt
```

### 2. `core/modes/designer.py:9`

```python
# 改前
return self.engine.wrapped_model.generate_voice_design(
    text=text, language=lang, instruct=instruct,
)

# 改后（参数顺序：text, instruct, language）
results = list(self.engine.wrapped_model.generate_voice_design(
    text=text, instruct=instruct, language="chinese",
))
audio = results[0].audio
sr = self.engine.wrapped_model.sample_rate
return [np.asarray(audio)], sr
```

### 3. `cli/commands/voice.py:201` 和 `cli/commands/tts.py:125`

两处结构相同 —— 删 instruct_ids 那两行：

```python
# 删除
input_objs = engine.processor(text=..., return_tensors="pt", padding=True)
instruct_ids = input_objs["input_ids"].to(engine.device)
torch.manual_seed(42)

# 在生成调用里删 instruct_ids=[instruct_ids] 参数
# 把 wrapped_model.generate_voice_clone(...) 换成
# list(engine.wrapped_model.generate(ref_audio=..., ref_text=...))
```

## 改 `cli/commands/doctor.py`

- [ ] 把 `import torch` 删掉
- [ ] 把 `torch.backends.mps.is_available()` 检查换成 `import mlx_audio` 的存在性 + 模型目录存在性
- [ ] 新增 `ref_text` 字段检查（persona 字典里有没有这个键）

## 改 `paths.py` / `preset.py`

- [ ] `paths.py`：默认模型路径从 `models/Base-1.7B` 改为 `models-mlx/Base-1.7B-8bit` 和 `models-mlx/VoiceDesign-1.7B-8bit`
- [ ] `preset.py`：preset 列表里的模型路径同步更新

## 改 `~/.voxflow/configs/personas.json`

- [ ] 给 `jxx_host` 加 `ref_text` 字段（用 whisper 转写样音）
- [ ] 给 `demo_narrator` 加 `ref_text` 字段（虽然是设计路径，加了也不亏）

```json
{
  "jxx_host": {
    "name": "老陈·人文旁白",
    "ref": "assets/temp/当前参考_jxx_host.wav",
    "ref_text": "<转写后填>",
    "desc": "低沉稳重，尾音干净，适合历史与人文题材；语速偏慢"
  },
  "demo_narrator": {
    "name": "温柔旁白",
    "ref": "assets/temp/当前参考_温柔旁白.wav",
    "design": "voice_designs/demo_narrator.json",
    "instruction": "中性、清晰、平稳、不带明显情绪",
    "ref_text": "<转写后填>",
    "desc": "中性偏柔，语速平稳，适合纪录片和知识讲解"
  }
}
```

## 改完跑回归（按这个顺序）

- [ ] `cd voxflow && .venv/bin/python tools/smoke_mlx_tts.py ~/.voxflow/models-mlx/Base-1.7B-8bit ~/.voxflow/assets/temp/当前参考_温柔旁白.wav`
- [ ] 对比 `~/.voxflow/out/mlx-smoke/fixed.wav` 和 `~/.voxflow/out/mlx-smoke/baseline_pytorch.wav`（PyTorch 版）
- [ ] whisper 转写两边，对照文字
- [ ] `voice web` 走两个角色各发一段，听音色
- [ ] `voice doctor` 看内存读数

## 回滚（如果出问题）

```bash
cd ~/dev/github/app/voxflow
git checkout core/engine.py core/modes/cloner.py core/modes/designer.py
git checkout cli/commands/voice.py cli/commands/tts.py cli/commands/doctor.py
git checkout paths.py cli/commands/preset.py

# 旧模型仍在 ~/.voxflow/models/，旧路径自动生效
```

不需要重新下载，回滚 5 分钟内回到 PyTorch 版。

## 完成后清理（可选）

- [ ] 卸载 qwen_tts（迁完没用了）：`.venv/bin/pip uninstall qwen_tts`
- [ ] 但**不要**立即删 `~/.voxflow/models/`（PyTorch 原生模型）—— 至少留到确认 MLX 版稳定一周后
- [ ] U 盘备份：把 `~/.voxflow/models-mlx/` 整个目录纳入 `MLX/` 分类（已有此分类结构）
- [ ] CHANGELOG.md 加一行："2026-09-14: Qwen3-TTS 切到 Apple MLX 8-bit，体积 -31%、推理 1.76×"
