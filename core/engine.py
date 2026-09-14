import os
from mlx_audio.tts.utils import load_model


class TTSBaseEngine:
    """基础引擎类：加载 Qwen3-TTS（Apple MLX 版）

    2026-09-14 起：只支持 macOS + Apple Silicon + MLX，不再保留 PyTorch 回退。
    理由见 docs/MLX_MIGRATION.md「已废弃的假设」段——PyTorch 链路既和
    mlx-audio 的 transformers 版本冲突，也是 MLP fallback 静默降级的根源。
    """

    def __init__(self, model_type: str, model_size: str):
        from core.paths import DATA_DIR
        self.base_dir = str(DATA_DIR)

        # 模型路径：models-mlx/<类型>-<规格>-8bit/
        self.model_path = os.path.join(
            self.base_dir, f"models-mlx/{model_type}-{model_size}-8bit"
        )
        if not os.path.exists(self.model_path):
            print(f"⚠️ 路径 {self.model_path} 不存在，尝试默认 Base-0.6B-8bit")
            self.model_path = os.path.join(
                self.base_dir, "models-mlx/Base-0.6B-8bit"
            )
        if not os.path.exists(self.model_path):
            raise RuntimeError(
                f"MLX 模型目录不存在：{self.model_path}\n"
                f"下载命令：\n"
                f"  hf download mlx-community/Qwen3-TTS-12Hz-1.7B-Base-8bit \\\n"
                f"    --local-dir {self.base_dir}/models-mlx/Base-1.7B-8bit\n"
                f"  hf download mlx-community/Qwen3-TTS-12Hz-1.7B-VoiceDesign-8bit \\\n"
                f"    --local-dir {self.base_dir}/models-mlx/VoiceDesign-1.7B-8bit"
            )

        print(f"🚀 正在加载 [MLX] {self.model_path} ...")
        self.wrapped_model = load_model(self.model_path)
        self.model_type = getattr(
            self.wrapped_model.config, "tts_model_type", "base"
        )
        self.sample_rate = self.wrapped_model.sample_rate
        print(
            f"      ✓ MLX 加载完成（type={self.model_type}, sr={self.sample_rate}）"
        )

    def ref_text_for(self, persona_key: str) -> str:
        """从 personas.json 取 ref_text；缺失抛清晰错误。

        MLX base 模型必须传 ref_text，否则输出截断+乱码（实测验证）。
        调用方（cloner）在生成前传 persona，由 engine 自动取文本。
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
