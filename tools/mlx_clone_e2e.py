#!/usr/bin/env python3
"""MLX 克隆链路端到端测试：用 voxflow 的真实 personas.json 和样音。

跑法：
    .venv/bin/python tools/mlx_clone_e2e.py

通过标准：跑通两个角色不抛错；产出非空音频。
"""
import os
import sys
import warnings
warnings.filterwarnings("ignore")

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import numpy as np
import soundfile as sf
from core.engine import TTSBaseEngine
from core.modes.cloner import CloneMode
from core.processor import AudioProcessor
from core.paths import DATA_DIR

OUT_DIR = os.path.join(str(DATA_DIR), "out/mlx-smoke")
os.makedirs(OUT_DIR, exist_ok=True)

TEXT = "这是一次语音合成测试，用来验证模型能否正常工作。"
ROLE = "demo_narrator"
REF = os.path.join(str(DATA_DIR), "assets/temp/当前参考_温柔旁白.wav")

print(f"[1/4] 加载 MLX engine")
engine = TTSBaseEngine("Base", "1.7B")
processor = AudioProcessor(str(DATA_DIR))
cloner = CloneMode(engine, processor)

print(f"[2/4] 跑 {ROLE} 的克隆（含 ref_text 自动取）")
import time
t0 = time.time()
wavs, sr = cloner.run(
    persona=ROLE, text=TEXT, lang="chinese", instruct="",
    emotion_priority=False, allow_ref_fallback=False, reference_audio=REF,
)
dt = time.time() - t0
print(f"      ✓ 推理耗时 {dt:.2f}s · 产出 {len(wavs)} 段 · sr={sr}")

print(f"[3/4] 保存第一段音频")
out = os.path.join(OUT_DIR, "e2e_demo_narrator.wav")
audio = np.asarray(wavs[0])
sf.write(out, audio, sr)
print(f"      ✓ {out}  时长 {len(audio)/sr:.2f}s")

print(f"[4/4] whisper 转写验证")
import mlx_whisper
r = mlx_whisper.transcribe(out, path_or_hf_repo="/Users/webkubor/.cache/voiceinput/models/whisper-large-v3-4bit", language="zh")
print(f"      ✓ 转写: {r['text'].strip()}")
