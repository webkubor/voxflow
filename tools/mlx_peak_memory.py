#!/usr/bin/env python3
"""MLX Qwen3-TTS 峰值内存探测：测模型加载后和生成时的 Metal GPU 内存占用。

跑法（用 MLX 环境，不是 voxflow 的 PyTorch venv）：
    ~/.local/share/voiceinput-models/.venv/bin/python tools/mlx_peak_memory.py
"""
import os
import sys
import warnings

warnings.filterwarnings("ignore")

# 默认路径，命令行第一个参数可覆盖
MODEL_DIR = sys.argv[1] if len(sys.argv) > 1 else os.path.expanduser(
    "~/.voxflow/models-mlx/Base-1.7B-8bit"
)
REF_AUDIO = sys.argv[2] if len(sys.argv) > 2 else os.path.expanduser(
    "~/.voxflow/assets/temp/当前参考_温柔旁白.wav"
)
REF_TEXT = "这是一段用于音色建模的中性短剧,语速平稳。"

import mlx.core as mx
from mlx_audio.tts.utils import load_model

mx.reset_peak_memory()
m = load_model(MODEL_DIR)
after_load = mx.get_peak_memory() / 1e9

results = list(m.generate(
    text="这是一次语音合成测试，用来验证模型能否正常工作。",
    ref_audio=REF_AUDIO,
    ref_text=REF_TEXT,
    lang_code="chinese", temperature=0.7, top_k=50, top_p=0.9,
))
after_gen = mx.get_peak_memory() / 1e9

print(f"MLX_PEAK_AFTER_LOAD={after_load:.2f}GB")
print(f"MLX_PEAK_AFTER_GEN={after_gen:.2f}GB")
print(f"产出 {len(results)} 段音频")
