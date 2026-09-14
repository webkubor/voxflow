#!/usr/bin/env python3
"""音色还原度对比：PyTorch `x_vector_only` vs MLX `ICL`。

## 为什么要有这个脚本

迁移前 voxflow 走 `x_vector_only_mode=True` —— 只取参考音频的**音色向量**，
**丢掉参考音频的文本内容**。MLX 侧没有 x_vector_only，只能走 ICL
（`ref_audio` + `ref_text`），**音色和内容都用上**。

于是有个顺理成章的猜想：条件信息更多 → 音色更像本人 → 迁移顺带白赚一个音质提升。

**实测把这个猜想否掉了。** 两侧还原度差异恰好落在 seed 噪声底量级上。

## 方法

用 Qwen3-TTS 自带的 speaker encoder（x-vector：TDNN + Res2Net + Attentive Statistics
Pooling）提取说话人向量，算余弦相似度。

**关键是带负对照**：另一个音色（jxx_host）给下界，参考音频自比给上界（1.0）。
没有负对照的话，0.993 这种数字没有刻度 —— 你不知道 0.99 算好还是算差。

**并且要测噪声底**：同一后端换 seed 重跑，看相似度本身抖多少。
如果两个后端的差 < 噪声底，那就叫「没有差别」，不能叫「略有优势」。

## 实测结论（2026-09-14）

| 对象 | 与原音色余弦相似度 |
|---|---|
| 参考音频自比（上界） | 1.0000 |
| PyTorch seed 42 / 43 / 44 | 0.9931 / 0.9928 / 0.9925 |
| MLX ICL | 0.9934 |
| 负对照·另一个音色 | 0.9425 |

- PyTorch 三个 seed 极差（**噪声底**）= 0.0006
- MLX 与 PyTorch 均值之差 = +0.0006 —— **恰在噪声底，无实质差别**

**含义**：迁移在音色还原度上**既没有损失也没有收益**。它换来的是体积 −31%、
速度 ×1.76；而「克隆 + 动态情绪」是净损失（见 `docs/MLX_MIGRATION.md` 坑 2）。

## 用法

    <MLX venv>/bin/python tools/compare_voice_fidelity.py <参考音频> <样本1> [样本2 ...]

样本用 PyTorch 与 MLX 两侧各自生成，文本与采样参数保持一致。
需 24kHz 音频（speaker encoder 只吃 24kHz）。
"""
import os
import sys
import json
import warnings

warnings.filterwarnings("ignore")

if len(sys.argv) < 3:
    print(__doc__)
    print("错误：至少需要 <参考音频> 和 一个 <样本>")
    sys.exit(2)

REF = sys.argv[1]
SAMPLES = sys.argv[2:]
MODEL = os.path.expanduser("~/.voxflow/models-mlx/Base-1.7B-8bit")

import numpy as np
import soundfile as sf
import mlx.core as mx
from mlx_audio.tts.utils import load_model

model = load_model(MODEL)


def embed(path: str) -> np.ndarray:
    y, sr = sf.read(path, dtype="float32", always_2d=False)
    if y.ndim > 1:
        y = y.mean(axis=1)
    if sr != 24000:
        raise ValueError(f"{path} 采样率 {sr}，speaker encoder 只吃 24kHz")
    v = np.asarray(
        model.extract_speaker_embedding(mx.array(y), sr=24000), dtype=np.float32
    ).reshape(-1)
    return v / (np.linalg.norm(v) + 1e-9)


print(f"参考：{os.path.basename(REF)}")
ref = embed(REF)
print(f"{'样本':<34}{'余弦相似度':>12}")
print("-" * 46)
rows = []
for p in SAMPLES:
    if not os.path.exists(p):
        print(f"{os.path.basename(p):<34}{'文件不存在':>12}")
        continue
    cos = float(np.dot(ref, embed(p)))
    rows.append({"file": os.path.basename(p), "cosine": round(cos, 4)})
    print(f"{os.path.basename(p):<34}{cos:>12.4f}")

print(f"\n参考音频自比应为 1.0000；不同音色作负对照时通常低 0.04~0.06。")
print("比较两个后端时，请同时测各后端换 seed 的极差作噪声底 —— 差小于噪声底即无实质差别。")

out = os.path.join(os.path.dirname(os.path.abspath(REF)), "voice_fidelity.json")
with open(out, "w", encoding="utf-8") as f:
    json.dump({"ref": os.path.basename(REF), "samples": rows}, f, ensure_ascii=False, indent=2)
print(f"报告 → {out}")
