import os
import sys
import soundfile as sf
from core.engine import TTSBaseEngine
from core.processor import AudioProcessor
from core.utils import (
    load_config,
    generate_output_path,
    get_persona_cn,
    log_generation_metadata,
    upsert_persona_mapping,
    resolve_design_voice_key,
    resolve_design_voice_label,
    resolve_config_path,
    sanitize_path_component,
    validate_runtime_config,
    write_generation_json,
)
from core.modes.cloner import CloneMode
from core.modes.designer import DesignMode
from core.modes.dialogue import DialogueMode

def main():
    BASE_DIR = os.path.dirname(os.path.abspath(__file__))
    agent_project = os.path.join(BASE_DIR, ".agent", "PROJECT.md")
    if not os.path.exists(agent_project):
        print("⚠️ [AI 初始化提醒] 未检测到 .agent/PROJECT.md。请先执行 AI 初始化（.agent + README 导航）。")

    config_arg = sys.argv[1].lower() if len(sys.argv) > 1 else "single"
    try:
        cfg_path, config_ref = resolve_config_path(config_arg)
    except ValueError as e:
        print(f"❌ 配置参数错误：{e}")
        sys.exit(1)

    print(f"📖 正在加载配置：{config_ref}")
    cfg = load_config(cfg_path)
    validate_runtime_config(cfg, config_ref)
    
    # 2. 初始化环境
    m_size = cfg.get("model_size", "1.7B")
    mode_type = cfg.get("model_type", "Base")
    engine = TTSBaseEngine(mode_type, m_size)
    processor = AudioProcessor(BASE_DIR)
    
    cloner = CloneMode(engine, processor)
    designer = DesignMode(engine, processor)
    dialogue = DialogueMode(engine, processor, cloner)
    
    # 智能识别任务类型
    task_type = cfg.get("type", "single") 
    is_dial = task_type == "dialogue" or ("lines" in cfg and isinstance(cfg["lines"], list))
    
    # 3. 模式分发
    if mode_type == "VoiceDesign":
        # ... (保持原逻辑)
        instruct = f"{cfg.get('tone','')}, {cfg.get('emotion','')}".strip(", ")
        wavs, sr = designer.run(cfg.get("text", ""), cfg.get("language","Chinese"), instruct)
        final_path = generate_output_path(cfg, BASE_DIR)
        sf.write(final_path, wavs[0], sr)
        processor.apply_design_cleanup(final_path)
        if bool(cfg.get("commit_to_temp", False)):
            voice_label = resolve_design_voice_label(cfg)
            voice_key = resolve_design_voice_key(cfg)
            temp_seed_path = processor.extract_voice_seed(final_path, voice_label, max_sec=10, skip_start_ms=0)
            ref_rel = os.path.relpath(temp_seed_path, BASE_DIR).replace("\\", "/")
            design_rel = f"voice_designs/{voice_label}.json"
            persona_file = upsert_persona_mapping(
                BASE_DIR,
                persona_key=voice_key,
                persona_name=voice_label,
                ref_rel=ref_rel,
                instruction=f"{cfg.get('tone', '')} {cfg.get('emotion', '')}".strip(),
            )
            gen_json_path = write_generation_json(BASE_DIR, voice_key, source="voice_design")
            print(f"🧬 [标准样音] 已沉淀：{os.path.relpath(temp_seed_path, BASE_DIR)}")
            print(f"🧭 [角色映射] 已更新：{os.path.relpath(persona_file, BASE_DIR)} -> {voice_key}")
            print(f"🧾 [生成配置] 模板：\n{gen_json_path}")
        else:
            print("📝 [待确认] 设计结果已输出到 out/。确认满意后，将 commit_to_temp 设为 true 再执行一次即可落库。")

    elif is_dial:
        final_path = dialogue.run(cfg)

    else:
        # 默认走 CloneMode (单人任务)
        instruct = f"{cfg.get('tone','')}, {cfg.get('emotion','')}".strip(", ")
        emotion_priority = bool(cfg.get("emotion_priority", False))
        wavs, sr = cloner.run(
            cfg.get("persona"),
            cfg.get("text", ""),
            cfg.get("language","Chinese"),
            instruct,
            emotion_priority=emotion_priority,
            reference_audio=cfg.get("reference_audio")
        )
        final_path = generate_output_path(cfg, BASE_DIR)
        sf.write(final_path, wavs[0], sr)
        processor.apply_post_tuning(final_path)

    print(f"\n✨ 生成成功！任务已闭环。\n📂 最终成品：{final_path}")
    log_generation_metadata(cfg, final_path, BASE_DIR)

if __name__ == "__main__":
    main()
