#!/usr/bin/env python3
"""MLX Qwen3-TTS 冒烟测试：验证 MLX 版能不能加载、能不能出声。

用法：
    python smoke_mlx_tts.py <模型目录> [参考音频路径]

不传参考音频时只测 voice_design 路径（Base 模型不传 ref 会报错，属预期）。
"""
import sys
import time
import os
import warnings

warnings.filterwarnings("ignore")

MODEL_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/.voxflow/models-mlx/Base-1.7B-8bit"
)
REF_AUDIO = sys.argv[2] if len(sys.argv) > 2 else None

OUT_DIR = os.path.expanduser("~/.voxflow/out/mlx-smoke")
os.makedirs(OUT_DIR, exist_ok=True)

print(f"[1/4] 加载模型：{MODEL_DIR}")
t0 = time.time()
from mlx_audio.tts.utils import load_model

model = load_model(MODEL_DIR)
t_load = time.time() - t0
print(f"      ✓ 加载耗时 {t_load:.2f}s")

print(f"[2/4] 模型信息")
print(f"      model_type = {getattr(model.config, 'tts_model_type', '?')}")
print(f"      sample_rate = {model.sample_rate}")

print(f"[3/4] 生成测试（中文）")
text = "这是一次语音合成测试，用来验证模型能否正常工作。"
t0 = time.time()
if REF_AUDIO:
    print(f"      克隆模式，参考音频：{REF_AUDIO}")
    results = list(
        model.generate(
            text=text,
            ref_audio=REF_AUDIO,
            ref_text="",  # mlx_audio base 模型要求 ref_text，先试空串
            lang_code="chinese",
            temperature=0.7,
            top_k=50,
            top_p=0.9,
        )
    )
else:
    print(f"      设计模式（无参考音频）")
    results = list(
        model.generate_voice_design(
            text=text,
            instruct="中性、清晰、平稳、不带明显情绪",
            language="chinese",
            temperature=0.7,
        )
    )
t_gen = time.time() - t0
print(f"      ✓ 生成耗时 {t_gen:.2f}s，产出 {len(results)} 段")

print(f"[4/4] 保存音频")
import numpy as np
import soundfile as sf

for i, r in enumerate(results):
    audio = np.asarray(r.audio)
    out = os.path.join(OUT_DIR, f"smoke_{i}.wav")
    sf.write(out, audio, model.sample_rate)
    dur = len(audio) / model.sample_rate
    print(f"      ✓ {out}  时长 {dur:.2f}s  样本 {len(audio)}")

print()
print(f"小结：加载 {t_load:.2f}s · 生成 {t_gen:.2f}s · 输出目录 {OUT_DIR}")
