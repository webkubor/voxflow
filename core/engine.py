import os
from mlx_audio.tts.utils import load_model

# 兼容旧 import：cloner.py 和 doctor.py 还在 import torch/qwen_tts，下面 try/except 防炸
try:
    import torch  # noqa: F401  # PyTorch 链路暂时保留作为回退
    HAS_TORCH = True
except ImportError:
    HAS_TORCH = False

try:
    from qwen_tts import Qwen3TTSModel  # noqa: F401  # 同上
    HAS_QWEN_TTS = True
except ImportError:
    HAS_QWEN_TTS = False


class TTSBaseEngine:
    """基础引擎类：处理硬件加速与模型加载

    2026-09-14 迁移：PyTorch(MPS) → Apple MLX。
    MLX 没有 device/dtype 概念，统一在 Metal GPU 跑，不存在 MPS fallback。
    PyTorch 链路暂时保留作回退，但默认走 MLX。
    """

    def __init__(self, model_type, model_size, *, backend="mlx"):
        from core.paths import DATA_DIR
        self.base_dir = str(DATA_DIR)

        # MLX 模型放在 models-mlx/，PyTorch 模型放在 models/。
        # 路径约定让 install.sh 与 auto-rotate.sh 共用同一棵树。
        self.backend = backend
        if backend == "mlx":
            self.model_path = os.path.join(
                self.base_dir, f"models-mlx/{model_type}-{model_size}-8bit"
            )
        else:
            self.model_path = os.path.join(
                self.base_dir, f"models/{model_type}-{model_size}"
            )

        if not os.path.exists(self.model_path):
            print(f"⚠️ 路径 {self.model_path} 不存在，尝试默认 Base-0.6B")
            fallback_name = "Base-0.6B-8bit" if backend == "mlx" else "Base-0.6B"
            self.model_path = os.path.join(self.base_dir, f"models-mlx/{fallback_name}" if backend == "mlx" else f"models/{fallback_name}")

        print(f"🚀 正在加载 [{backend}] {self.model_path} ...")

        if backend == "mlx":
            self._load_mlx()
        else:
            self._load_pytorch()

    def _load_mlx(self):
        """MLX 加载路径。返回 model 实例 + model_type 字符串。
        上层（cloner / designer）据此分流调用 generate / generate_voice_design。
        """
        self.wrapped_model = load_model(self.model_path)
        self.model_type = getattr(
            self.wrapped_model.config, "tts_model_type", "base"
        )
        self.sample_rate = self.wrapped_model.sample_rate
        # 兼容旧字段（有些调用方还引用 engine.model / engine.processor）
        self.model = None  # MLX 没有暴露的内层 model，调用走 wrapped_model
        self.processor = None  # MLX 没有独立 tokenizer（generate 内置）
        self.device = "metal"  # 给 doctor.py / UI 报告用
        self.dtype = "mlx-quantized"
        print(f"      ✓ MLX 加载完成（type={self.model_type}, sr={self.sample_rate}）")

    def _load_pytorch(self):
        """PyTorch 链路（回退用）。原代码几乎原样保留。"""
        if not HAS_TORCH or not HAS_QWEN_TTS:
            raise RuntimeError(
                "PyTorch 后端不可用：torch / qwen_tts 未安装。"
                "请用 backend='mlx'，或装回 PyTorch 链路。"
            )
        os.environ["PYTORCH_ENABLE_MPS_FALLBACK"] = "1"
        self.device, self.dtype = self._detect_device()
        print(f"      ✓ PyTorch 加载到 {self.device.upper()}...")
        try:
            self.wrapped_model = Qwen3TTSModel.from_pretrained(
                self.model_path,
                device_map=self.device,
                dtype=self.dtype,
                attn_implementation="sdpa",
            )
        except Exception as e:
            print(f"⚠️ 硬件加速启动失败，回退到 CPU... ({e})")
            self.wrapped_model = Qwen3TTSModel.from_pretrained(
                self.model_path, device_map="cpu", dtype=torch.float32
            )
            self.device, self.dtype = "cpu", torch.float32
        self.model = self.wrapped_model.model
        self.processor = self.wrapped_model.processor
        self.model_type = getattr(
            self.wrapped_model.config, "tts_model_type", "base"
        ) if hasattr(self.wrapped_model, "config") else "base"
        self.sample_rate = 24000  # Qwen3-TTS 默认 24kHz

    def _detect_device(self):
        if not HAS_TORCH:
            return "cpu", None
        device = "mps" if torch.backends.mps.is_available() else "cpu"
        dtype = torch.bfloat16 if device == "mps" else torch.float32
        return device, dtype

    def ref_text_for(self, persona_key: str) -> str:
        """从 personas.json 取 ref_text；缺失抛清晰错误。

        MLX base 模型必须传 ref_text，否则输出截断+乱码（实测验证）。
        调用方（cloner）应在调用前传 persona，由 engine 自动取文本。
        """
        from core.utils import get_persona_map
        m = get_persona_map().get(persona_key, {})
        txt = (m.get("ref_text") or "").strip()
        if not txt:
            ref = m.get("ref", "<无 ref>")
            raise RuntimeError(
                f"persona '{persona_key}' 缺少 ref_text；先用 whisper 转写 "
                f"{ref} 后填回 ~/.voxflow/configs/personas.json"
            )
        return txt
