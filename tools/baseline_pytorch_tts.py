#!/usr/bin/env python3
"""PyTorch 版 Qwen3-TTS 基线：与 MLX 版做同文本同音色的 A/B 对比。

跑法（必须用 voxflow 自己的 venv）：
    .venv/bin/python tools/baseline_pytorch_tts.py

⚠️ **2026-09-29 起本脚本默认跑不了**：PyTorch 回退链路已整条删除，
   `~/.voxflow/models/`（8.4 GB PyTorch 权重）也随模型整理清掉了。
   保留本脚本只为一个用途：**MLX 版出问题时**，把权重从 U 盘
   `/Volumes/AI素材资源/开源模型/pytorch/Qwen3-TTS-1.7B/Base` 拷回
   `~/.voxflow/models/Base-1.7B` 再跑这个 A/B 对照。
   没有权重就先跑下面这段检查 —— 不要让它在 import torch 时才炸。
"""
import os
import sys
import time
import warnings

warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TEXT = "这是一次语音合成测试，用来验证模型能否正常工作。"
REF = os.path.expanduser("~/.voxflow/assets/temp/当前参考_温柔旁白.wav")
REF_TEXT = "这是一段用于音色建模的中性短剧,语速平稳。"
MODEL_PATH = os.path.expanduser("~/.voxflow/models/Base-1.7B")
OUT = os.path.expanduser("~/.voxflow/out/mlx-smoke/baseline_pytorch.wav")

# 前置检查：先说清「为什么不能跑」，而不是在 load_model 时抛一句
# No such file or directory（那年 MLX 迁移踩的就是「模型路径对不上」，
# 报错却指向别处，见 core/engine.py 注释）。
if not os.path.isdir(MODEL_PATH):
    sys.exit(
        f"[x] PyTorch 权重不存在：{MODEL_PATH}\n"
        f"    PyTorch 回退链路 2026-09-14 已删除，本脚本仅供回滚对照。\n"
        f"    需要时从 U 盘拷回：\n"
        f"      mkdir -p {os.path.dirname(MODEL_PATH)}\n"
        f"      cp -a '/Volumes/AI素材资源/开源模型/pytorch/Qwen3-TTS-1.7B/Base' {MODEL_PATH}\n"
        f"    日常走 MLX：core/engine.py 用的是 models-mlx/，与本脚本无关。"
    )

print(f"[1/3] 加载 PyTorch 模型：{MODEL_PATH}")
t0 = time.time()
import torch
from qwen_tts import Qwen3TTSModel

os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
device = "mps" if torch.backends.mps.is_available() else "cpu"
dtype = torch.bfloat16 if device == "mps" else torch.float32

model = Qwen3TTSModel.from_pretrained(
    MODEL_PATH, device_map=device, dtype=dtype, attn_implementation="sdpa"
)
t_load = time.time() - t0
print(f"      ✓ 加载耗时 {t_load:.2f}s（device={device}）")

print(f"[2/3] 生成同一句：{TEXT}")
instruct_text = "<|im_start|>user\n中性、清晰、平稳、不带明显情绪<|im_end|>\n"
input_objs = model.processor(text=instruct_text, return_tensors="pt", padding=True)
instruct_ids = input_objs["input_ids"].to(device)

torch.manual_seed(42)
t0 = time.time()
wavs, sr = model.generate_voice_clone(
    text=TEXT,
    language="Chinese",
    ref_audio=REF,
    x_vector_only_mode=True,
    instruct_ids=[instruct_ids],
    do_sample=True,
    temperature=0.7,
    top_p=0.9,
    top_k=50,
)
t_gen = time.time() - t0
print(f"      ✓ 生成耗时 {t_gen:.2f}s")

print(f"[3/3] 保存：{OUT}")
import numpy as np
import soundfile as sf

audio = np.asarray(wavs[0])
sf.write(OUT, audio, sr)
print(f"      ✓ 时长 {len(audio)/sr:.2f}s  采样率 {sr}")

print()
print(f"小结：加载 {t_load:.2f}s · 生成 {t_gen:.2f}s")
