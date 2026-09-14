#!/usr/bin/env python3
"""控制变量实验：PyTorch base 路径上 `instruct_ids` 到底生不生效？

## 为什么要有这个脚本

关于 `x_vector_only_mode=True` 和 `instruct_ids` 能不能共存，项目里出现过两派判断：
一派读 `qwen_tts/core/models/modeling_qwen3_tts.py` 说两者是独立通道（`:2076` 独立追加
instruct embedding、`:2103` 只管 speaker_embed），都生效；另一派从参数**字面**推测
二者冲突、instruct 被静默忽略。

**从字面猜是靠不住的。** 这个脚本用控制变量法把它一次测死。

## 设计

同文本、同样音、`torch.manual_seed(42)`、同采样参数，**只切换 `instruct_ids` 有无**。
seed 固定后，输入相同则输出必然逐样本相同；实测若分叉，就说明 instruct 确实进了计算图。

用强指令（「用极度愤怒、咆哮的语气说」）放大信号，避免弱指令测不出差别。

## 用法

    .venv/bin/python tools/verify_instruct_effect.py [输出目录]

需要 PyTorch 链路可用（`~/.voxflow/models/Base-1.7B`）。
"""
import os
import sys
import time
import json
import warnings

warnings.filterwarnings("ignore")

PROJECT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(PROJECT)
sys.path.insert(0, PROJECT)

OUT = sys.argv[1] if len(sys.argv) > 1 else "/tmp/voxflow-instruct-check"
os.makedirs(OUT, exist_ok=True)

REF = os.path.expanduser("~/.voxflow/assets/temp/当前参考_温柔旁白.wav")
MODEL = os.path.expanduser("~/.voxflow/models/Base-1.7B")
TEXT = "你怎么能这样对我说话！"
INSTRUCT = "中性、清晰、平稳、不带明显情绪 用极度愤怒、咆哮的语气说"

import numpy as np
import soundfile as sf
import torch
from qwen_tts import Qwen3TTSModel

print("=" * 66)
print("instruct_ids 是否生效 —— 控制变量实验")
print("=" * 66)

t0 = time.time()
model = Qwen3TTSModel.from_pretrained(
    MODEL, device_map="mps", dtype=torch.bfloat16, attn_implementation="sdpa"
)
print(f"模型加载 {time.time() - t0:.2f}s")

processor = model.processor
input_objs = processor(
    text=f"<|im_start|>user\n{INSTRUCT}<|im_end|>\n",
    return_tensors="pt",
    padding=True,
)
instruct_ids = input_objs["input_ids"].to("mps")

report = {"text": TEXT, "instruct": INSTRUCT, "runs": {}}


def run(tag: str, with_instruct: bool):
    torch.manual_seed(42)
    t0 = time.time()
    kwargs = dict(
        text=TEXT,
        language="Chinese",
        ref_audio=REF,
        x_vector_only_mode=True,
        do_sample=True,
        temperature=0.7,
        top_p=0.9,
        top_k=50,
    )
    if with_instruct:
        kwargs["instruct_ids"] = [instruct_ids]
    wavs, sr = model.generate_voice_clone(**kwargs)
    dt = time.time() - t0
    a = np.asarray(wavs[0], dtype=np.float32)
    path = os.path.join(OUT, f"instruct_{tag}.wav")
    sf.write(path, a, sr)
    print(f"  [{tag}] 时长 {len(a) / sr:.3f}s  生成 {dt:.2f}s  样本 {len(a)}")
    report["runs"][tag] = {
        "with_instruct": with_instruct,
        "file": path,
        "audio_sec": round(len(a) / sr, 4),
        "samples": int(len(a)),
        "gen_sec": round(dt, 2),
    }
    return a


print("\n--- A：带 instruct_ids ---")
a = run("with", True)
print("--- B：不带 instruct_ids ---")
b = run("without", False)

n = min(len(a), len(b))
diff = np.abs(a[:n] - b[:n])
max_abs = float(diff.max()) if n else 0.0
rms_diff = float(np.sqrt((diff ** 2).mean())) if n else 0.0
identical = bool(len(a) == len(b) and max_abs == 0.0)

report["verdict"] = {
    "same_length": len(a) == len(b),
    "identical_samples": identical,
    "max_abs_diff": round(max_abs, 8),
    "rms_diff": round(rms_diff, 8),
}

print("\n" + "=" * 66)
print(f"样本数       : {len(a)} vs {len(b)}  ({'相同' if len(a) == len(b) else '不同'})")
print(f"逐样本最大差 : {max_abs:.8f}")
print(f"RMS 差       : {rms_diff:.8f}")
if identical:
    print("判定：逐样本完全相同 → instruct_ids 在这条路径上无任何作用")
else:
    print("判定：输出分叉 → instruct_ids 确实在起作用（不是被忽略）")
print("=" * 66)

with open(os.path.join(OUT, "report_instruct.json"), "w", encoding="utf-8") as f:
    json.dump(report, f, ensure_ascii=False, indent=2)
print(f"报告 → {OUT}/report_instruct.json")

sys.exit(0 if not identical else 1)
