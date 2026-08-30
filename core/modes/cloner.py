import os
import torch
from ..utils import get_persona_cn, sanitize_path_component

class CloneMode:
    """【模块 1：单人克隆】 深度重构：支持指令克隆，开启 1.7B 演技模式"""
    def __init__(self, engine, processor):
        self.engine = engine
        self.processor = processor
        self.seed_dir = os.path.join(engine.base_dir, "assets/output_audio/designed_seeds")

    def _try_build_temp_seed_from_reference(self, persona: str, persona_cn: str) -> str:
        """当 temp 样音不存在时，尝试从 personas.json 的参考音频自动提取黄金样音。"""
        from ..utils import get_persona_map

        persona_map = get_persona_map()
        persona_data = persona_map.get(persona, {})
        if not isinstance(persona_data, dict):
            return ""

        ref_rel = str(persona_data.get("ref", "")).strip()
        if not ref_rel:
            return ""

        ref_path = os.path.join(self.engine.base_dir, ref_rel)
        if not os.path.exists(ref_path):
            return ""

        return self.processor.extract_voice_seed(ref_path, persona_cn, max_sec=10, skip_start_ms=1500)

    def run(
        self,
        persona,
        text,
        lang,
        instruct,
        emotion_priority=False,
        allow_ref_fallback=True,
        reference_audio=None,
    ):
        """执行单人克隆。

        - allow_ref_fallback=True: temp 缺失时，允许从原始参考音频自动提取样音
        - allow_ref_fallback=False: temp 缺失直接报错（对话模式用）
        - reference_audio: 0-1 克隆阶段可直接指定原始参考音频路径
        """
        display_name = get_persona_cn(persona)
        p_cn = sanitize_path_component(display_name, fallback="未命名角色")

        # 参考音频的路径只从 personas.json 的 ref 字段来，不按名字拼 ——
        # 拼路径会把名字焊死成文件名，改个名就找不到音频了。
        from core.utils import persona_ref_audio, load_personas
        ref_audio = persona_ref_audio(
            self.engine.base_dir, (load_personas() or {}).get(persona) or {})

        if not os.path.exists(ref_audio):
            # 优先使用请求中显式提供的原始参考音频，适配 0-1 克隆阶段
            if reference_audio:
                ref_path = reference_audio if os.path.isabs(reference_audio) else os.path.join(self.engine.base_dir, reference_audio)
                if os.path.exists(ref_path):
                    built = self.processor.extract_voice_seed(ref_path, p_cn, max_sec=10, skip_start_ms=1500)
                    if built and os.path.exists(built):
                        ref_audio = built
                    else:
                        raise RuntimeError(f"reference_audio 提取失败：{reference_audio}")
                else:
                    raise RuntimeError(f"reference_audio 不存在：{reference_audio}")
            elif allow_ref_fallback:
                built = self._try_build_temp_seed_from_reference(persona, p_cn)
                if built and os.path.exists(built):
                    ref_audio = built
                else:
                    raise RuntimeError(
                        f"找不到角色【{display_name}】的参考音频资产。"
                        f"需要 temp 样音：{ref_audio}，或在 personas.json 配置可用的 ref 原始参考音频。"
                    )
            else:
                raise RuntimeError(
                    f"找不到角色【{display_name}】的标准样音。"
                    f"对话/生成模式仅允许使用 temp 标准样音：{ref_audio}。"
                    "请先执行一次克隆或设计流程，生成该角色的标准样音。"
                )

        seed = ref_audio  # 直接使用 temp 里的黄金样音

        # --- 合并指令：基础音色描述 + 实时情绪控制 ---
        from ..utils import get_persona_map
        persona_map = get_persona_map()
        persona_data = persona_map.get(persona, {})
        base_instruct = ""
        if isinstance(persona_data, dict) and "instruction" in persona_data:
            base_instruct = persona_data["instruction"]

        if emotion_priority:
            final_instruct = (instruct or "").strip() or base_instruct
        else:
            final_instruct = f"{base_instruct} {instruct}".strip()
        instruct_text = f"<|im_start|>user\n{final_instruct}<|im_end|>\n"
        input_objs = self.engine.processor(text=instruct_text, return_tensors="pt", padding=True)
        instruct_ids = input_objs["input_ids"].to(self.engine.device) 

        priority_tag = "情绪优先" if emotion_priority else "人设优先"
        print(f"👥 模式：指令克隆({priority_tag}) | 角色：{display_name} | 演技负载：{final_instruct[:50]}...")

        torch.manual_seed(42)
        if torch.cuda.is_available(): torch.cuda.manual_seed_all(42)

        # --- 标准答案逻辑：平衡音色与演技张力 ---
        wavs, sr = self.engine.wrapped_model.generate_voice_clone(
            text=text, 
            language=lang, 
            ref_audio=seed, 
            x_vector_only_mode=True,
            instruct_ids=[instruct_ids],
            do_sample=True,
            temperature=0.7,  # 标准答案：既有戏，又稳得住音色
            top_p=0.9,       # 标准答案：保留富有张力的情感分支
            top_k=50
        )
        return wavs, sr
