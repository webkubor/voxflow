import os
import json
import re
from datetime import datetime
from typing import Any, Dict, Tuple

# 数据根（~/.voxflow），不是代码目录 —— personas.json 里的 ref、design
# 存的都是相对它的路径。真源见 core/paths.py。
from core.paths import DATA_DIR as _DATA_DIR
BASE_DIR = str(_DATA_DIR)
PERSONA_CONFIG = os.path.join(BASE_DIR, "configs/personas.json")
CONFIG_DIR = os.path.join(BASE_DIR, "configs")
REFERENCE_AUDIO_DIR_REL = "assets/reference_audio"
ALLOWED_REFERENCE_EXTS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac")

CORE_RUNTIME_CONFIGS = {
    "clone": "clone.json",
    "design": "design.json",
    "dialogue": "dialogue.json",
}

DEFAULT_CONFIG_ALIASES = {
    "single": "clone",
    "clone": "clone",
    "design": "design",
    "voice_design": "design",
    "voice_production": "dialogue",
    "dialogue": "dialogue",
    "scene": "dialogue",
}

POLICY_RULES = {
    "max_text_chars": 400,
    "max_design_text_chars": 45,
    "default_design_text": "这是一段用于音色建模的短句，请保持自然呼吸。",
    "require_persona_for_single": True,
    "require_role_or_persona_for_dialogue_line": True,
    "forbid_empty_instruction_when_voice_design": True,
    "forbidden_instruction_keywords": ["nsfw", "露骨", "仇恨", "极端暴力"],
}

def get_persona_map():
    default_map = {"narrator": "旁白", "me": "老爹", "yue_qizhou": "月栖洲"}
    if os.path.exists(PERSONA_CONFIG):
        try:
            with open(PERSONA_CONFIG, 'r', encoding='utf-8') as f:
                return json.load(f)
        except: return default_map
    return default_map

def get_persona_cn(persona_en):
    persona_map = get_persona_map()
    data = persona_map.get(persona_en, persona_en)
    if isinstance(data, dict):
        return data.get("name", persona_en)
    return data

def sanitize_path_component(value: Any, fallback: str = "未知") -> str:
    """将任意输入清洗为可安全用于文件名/路径片段的字符串。"""
    text = str(value or "").strip()
    if not text:
        text = fallback
    text = text.replace("\\", "_").replace("/", "_")
    text = re.sub(r'[:*?"<>|]', "_", text)
    text = re.sub(r"\s+", "_", text).strip("._")
    return text or fallback

def resolve_output_persona_label(config: Dict[str, Any]) -> str:
    """解析输出命名使用的人物标签。

    优先级：
    1) persona（已注册或自定义）
    2) reference_audio 的文件名（无扩展名）
    3) 未知
    """
    persona = str(config.get("persona", "")).strip()
    if persona:
        return sanitize_path_component(get_persona_cn(persona), fallback="未知")

    reference_audio = str(config.get("reference_audio", "")).strip()
    if reference_audio:
        stem = os.path.splitext(os.path.basename(reference_audio))[0]
        return sanitize_path_component(stem, fallback="未知")

    return "未知"

def resolve_design_voice_label(config: Dict[str, Any]) -> str:
    """解析设计模式下的音色显示名（不依赖 personas）。"""
    voice_name = str(config.get("voice_name", "")).strip()
    if voice_name:
        return sanitize_path_component(voice_name, fallback="未命名角色")
    return "未命名角色"

def resolve_design_voice_key(config: Dict[str, Any]) -> str:
    """解析设计模式下的音色键名（用于生成配置文件名与 persona 字段占位）。"""
    voice_name = str(config.get("voice_name", "")).strip()
    if voice_name:
        return sanitize_path_component(voice_name, fallback="unknown_persona")
    return "unknown_persona"

def load_config(path):
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def _expected_ref_base(persona_name: str) -> str:
    return f"{persona_name}_参考"

def _normalize_ref_path(ref_path: str) -> str:
    return ref_path.replace("\\", "/")

def validate_persona_ref_rule(persona: str, persona_data: Dict[str, Any]):
    """强制约束：ref 必须位于 assets/reference_audio 且命名符合 <角色名>_参考.<ext>。"""
    if not isinstance(persona_data, dict):
        return
    if "ref" not in persona_data:
        return

    persona_name = str(persona_data.get("name", "")).strip()
    ref_rel = str(persona_data.get("ref", "")).strip()
    if not persona_name:
        raise ValueError(f"personas.json 中 {persona} 缺少 name。")
    if not ref_rel:
        raise ValueError(f"personas.json 中 {persona} 的 ref 不能为空。")

    normalized_ref = _normalize_ref_path(ref_rel)
    expected_prefix = f"{REFERENCE_AUDIO_DIR_REL}/"
    if not normalized_ref.startswith(expected_prefix):
        raise ValueError(
            f"personas.json 中 {persona} 的 ref 非法：{ref_rel}。"
            f"必须放在 {REFERENCE_AUDIO_DIR_REL}/ 下。"
        )

    ref_name = os.path.basename(normalized_ref)
    ref_stem, ref_ext = os.path.splitext(ref_name)
    if ref_ext.lower() not in ALLOWED_REFERENCE_EXTS:
        raise ValueError(
            f"personas.json 中 {persona} 的 ref 后缀非法：{ref_ext}。"
            f"仅允许 {', '.join(ALLOWED_REFERENCE_EXTS)}"
        )

    expected_stem = _expected_ref_base(persona_name)
    if ref_stem != expected_stem:
        raise ValueError(
            f"personas.json 中 {persona} 的 ref 命名不符合规范：{ref_name}。"
            f"应为 {expected_stem}<ext>"
        )

def persona_ref_audio(base_dir: str, persona_data: Dict[str, Any]) -> str:
    """
    音色参考音频的路径。**唯一来源是 ref 字段** —— 不从名字推导。

    以前这里是「先按 `当前参考_{名字}.wav` 拼一个路径，拼不到再读 ref」。
    两条路指向的其实是同一个文件（注册音色时 ref 写的就是那个 temp 路径），
    拼接完全冗余；但它带来一个很实际的后果：**名字变成了路径的一部分**，
    于是「给音色改个中文名」这种最普通的操作会让音频找不到，
    还得连带重命名文件、处理重名、失败回滚 —— 一件本该改一个字段的事。

    路径存在数据里，就只从数据里读。名字回归成纯粹的名字。

    返回 "" 表示没有可用音频，由调用方决定怎么提示 —— 不在这里抛异常，
    因为「列个清单看看谁缺素材」和「现在就要合成」需要的反应不一样。
    """
    ref_rel = str((persona_data or {}).get("ref", "")).strip()
    if not ref_rel:
        return ""
    path = ref_rel if os.path.isabs(ref_rel) else os.path.join(base_dir, ref_rel)
    return path if os.path.exists(path) else ""


def resolve_persona_ref_audio(base_dir: str, persona: str, persona_data: Dict[str, Any]) -> str:
    """解析参考音频路径并校验存在；缺素材时抛出可读的错误。"""
    path = persona_ref_audio(base_dir, persona_data)
    if path:
        return path

    ref_rel = str((persona_data or {}).get("ref", "")).strip()
    if not ref_rel:
        return ""
    raise ValueError(
        f"角色 {persona} 的参考音频不存在：{ref_rel}\n"
        f"（音色是否被删过文件？可以重新上传参考音频注册一次）"
    )

def _in_configs_dir(path: str) -> bool:
    abs_configs = os.path.abspath(CONFIG_DIR)
    abs_path = os.path.abspath(path)
    return os.path.commonpath([abs_configs, abs_path]) == abs_configs

def resolve_config_path(config_arg: str = "single") -> Tuple[str, str]:
    """将 CLI 参数解析为受控配置路径，阻止 configs 根目录继续堆临时文件。"""
    arg = (config_arg or "single").strip()
    alias = DEFAULT_CONFIG_ALIASES.get(arg, arg)

    if alias in CORE_RUNTIME_CONFIGS:
        rel_path = CORE_RUNTIME_CONFIGS[alias]
        # 先找你改过的（~/.voxflow/configs），没有就用项目自带的模板。
        # 只认数据目录的话，分家之后这些模板全读不到。
        from core.paths import find_config
        cfg_path = str(find_config(rel_path))
        if not os.path.exists(cfg_path):
            raise ValueError(f"配置不存在：{rel_path}")
        return cfg_path, alias

    if arg.endswith(".json"):
        normalized = os.path.normpath(arg)
        if os.path.isabs(normalized):
            cfg_path = normalized
            rel_path = os.path.relpath(cfg_path, CONFIG_DIR)
        else:
            cfg_path = os.path.join(CONFIG_DIR, normalized)
            rel_path = normalized

        if not _in_configs_dir(cfg_path):
            raise ValueError("仅允许加载 configs 目录内的配置文件。")
        if not os.path.exists(cfg_path):
            raise ValueError(f"配置不存在：{rel_path}")

        # 根目录仅保留 4 个核心 JSON（clone/design/dialogue/personas）
        if "/" not in rel_path and rel_path not in {
            "clone.json",
            "design.json",
            "dialogue.json",
            "personas.json",
        }:
            raise ValueError(
                "configs 根目录仅允许 4 个核心 JSON。"
            )
        return cfg_path, rel_path

    raise ValueError(f"未知配置参数：{config_arg}。请使用 clone/design/dialogue 或 configs 子目录内的 JSON。")

def _assert_text_rules(text: str, field_name: str, max_chars: int):
    if not isinstance(text, str) or not text.strip():
        raise ValueError(f"{field_name} 不能为空。")
    if len(text) > max_chars:
        raise ValueError(f"{field_name} 超过限制（{len(text)} > {max_chars}）。")

def _resolve_bootstrap_reference_audio(base_dir: str, reference_audio: str) -> str:
    """解析 0-1 克隆阶段的原始参考音频路径并校验合法性。"""
    ref = (reference_audio or "").strip()
    if not ref:
        raise ValueError("0-1 克隆阶段必须提供 reference_audio。")
    ref_path = ref if os.path.isabs(ref) else os.path.join(base_dir, ref)
    if not os.path.exists(ref_path):
        raise ValueError(f"reference_audio 不存在：{reference_audio}")
    ext = os.path.splitext(ref_path)[1].lower()
    if ext not in ALLOWED_REFERENCE_EXTS:
        raise ValueError(
            f"reference_audio 后缀非法：{ext}。仅允许 {', '.join(ALLOWED_REFERENCE_EXTS)}"
        )
    return ref_path

def validate_runtime_config(config: Dict[str, Any], config_ref: str = ""):
    """运行前策略校验：防止无约束配置进入主流程。"""
    rules = POLICY_RULES
    max_text_chars = int(rules.get("max_text_chars", 600))
    max_design_text_chars = int(rules.get("max_design_text_chars", 80))
    default_design_text = str(
        rules.get("default_design_text", "这是一段用于音色建模的短句，请保持自然呼吸。")
    ).strip()
    require_persona = bool(rules.get("require_persona_for_single", True))
    require_line_role = bool(rules.get("require_role_or_persona_for_dialogue_line", True))
    block_keywords = rules.get("forbidden_instruction_keywords", [])
    require_design_prompt = bool(rules.get("forbid_empty_instruction_when_voice_design", True))

    persona_map = get_persona_map()
    task_type = config.get("type", "single")
    model_type = config.get("model_type", "Base")
    lines = config.get("lines")

    # 注册表层面的命名规则校验（全面放开路径限制，只校验核心逻辑）
    for persona_key, persona_data in persona_map.items():
        if isinstance(persona_data, dict) and "ref" in persona_data:
            # validate_persona_ref_rule(persona_key, persona_data) # 切除古板校验
            pass

    if isinstance(lines, list):
        for idx, line in enumerate(lines, start=1):
            if not isinstance(line, dict):
                raise ValueError(f"lines[{idx}] 必须是对象。")
            role_or_persona = line.get("role") or line.get("persona")
            if require_line_role and not role_or_persona:
                raise ValueError(f"lines[{idx}] 缺少 role/persona。")
            if role_or_persona and role_or_persona not in persona_map:
                raise ValueError(f"lines[{idx}] 角色未注册：{role_or_persona}。请先在 personas.json 定义。")
            if role_or_persona and isinstance(persona_map.get(role_or_persona), dict):
                pdata = persona_map.get(role_or_persona, {})
                if "ref" in pdata:
                    resolve_persona_ref_audio(BASE_DIR, role_or_persona, pdata)
            _assert_text_rules(line.get("text", ""), f"lines[{idx}].text", max_text_chars)
            merged_instruct = " ".join([
                str(line.get("tone", "")),
                str(line.get("emotion", "")),
                str(line.get("instruction", "")),
            ]).lower()
            for keyword in block_keywords:
                if keyword and keyword.lower() in merged_instruct:
                    raise ValueError(f"lines[{idx}] 指令命中禁用关键词：{keyword}")

    elif task_type in ("single", "clone") or model_type == "Base":
        if require_persona and not config.get("persona"):
            raise ValueError("single/clone 模式必须提供 persona。")
        persona = config.get("persona")
        reference_audio = str(config.get("reference_audio", "")).strip()

        # 0-1 克隆阶段：允许 persona 未注册，但必须提供 reference_audio
        if persona and persona not in persona_map:
            if reference_audio:
                _resolve_bootstrap_reference_audio(BASE_DIR, reference_audio)
            else:
                raise ValueError(
                    f"persona 未注册：{persona}。"
                    "若处于 0-1 克隆阶段，请提供 reference_audio；"
                    "若处于生产生成阶段，请先在 personas.json 注册该 persona。"
                )
        if persona and isinstance(persona_map.get(persona), dict):
            pdata = persona_map.get(persona, {})
            if "ref" in pdata:
                resolve_persona_ref_audio(BASE_DIR, persona, pdata)
        if model_type != "VoiceDesign":
            _assert_text_rules(config.get("text", ""), "text", max_text_chars)

    if model_type == "VoiceDesign":
        # 设计模式：文案不是重点，可留空自动填默认短句；并做硬长度限制
        if not str(config.get("text", "")).strip():
            config["text"] = default_design_text
        _assert_text_rules(config.get("text", ""), "text", max_design_text_chars)
        voice_name = str(config.get("voice_name", "")).strip()
        if not voice_name:
            raise ValueError("VoiceDesign 模式必须提供 voice_name（设计音色标识）。")
        tone = str(config.get("tone", "")).strip()
        emotion = str(config.get("emotion", "")).strip()
        if require_design_prompt and not (tone or emotion):
            raise ValueError("VoiceDesign 模式至少提供 tone 或 emotion。")
        merged_instruct = f"{tone} {emotion}".lower()
        for keyword in block_keywords:
            if keyword and keyword.lower() in merged_instruct:
                raise ValueError(f"VoiceDesign 指令命中禁用关键词：{keyword}")

    # 标注来源便于追踪触发点
    if config_ref:
        print(f"🧩 配置策略校验通过：{config_ref}")

def generate_output_path(config, base_dir, suffix=""):
    out_dir = os.path.join(base_dir, "out")
    os.makedirs(out_dir, exist_ok=True)
    if config.get("output_filename") and not suffix:
        return os.path.join(out_dir, config["output_filename"])
    
    is_dial = "lines" in config and isinstance(config["lines"], list)
    if is_dial:
        persona_cn = "场景对话"
    elif config.get("model_type") == "VoiceDesign":
        persona_cn = resolve_design_voice_label(config)
    else:
        persona_cn = resolve_output_persona_label(config)
        
    mode_tag = "对话" if is_dial else ("设计" if config.get("model_type") == "VoiceDesign" else "克隆")
    filename = f"[{mode_tag}]{persona_cn}_第{config.get('episode', 'X')}集_{config.get('title', '未命名')}{suffix}.wav"
    return os.path.join(out_dir, re.sub(r'[\/:*?"<>|]', '_', filename))

def log_generation_metadata(config, audio_path, base_dir):
    """【修复版】智能识别对话场景，避免出现 unknown 记录"""
    mode_type = config.get("model_type", "Base")
    is_dial = "lines" in config and isinstance(config["lines"], list)
    episode = config.get("episode", "unknown")
    
    # 确定记录主体的中文名
    if is_dial or episode == "Scene":
        persona_cn = "场景"
    elif mode_type == "VoiceDesign":
        persona_cn = resolve_design_voice_label(config)
    else:
        persona_cn = resolve_output_persona_label(config)
    
    # --- 分支 A：音色设计配方 ---
    if mode_type == "VoiceDesign" and not is_dial:
        design_dir = os.path.join(base_dir, "voice_designs")
        os.makedirs(design_dir, exist_ok=True)
        design_file = os.path.join(design_dir, f"{persona_cn}.json")
        
        design_data = {
            "persona": persona_cn,
            "created_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "model": f"{config.get('model_size', '1.7B')}-VoiceDesign",
            "instruction_formula": {
                "full_prompt": config.get("tone", ""),
                "emotion": config.get("emotion", "")
            },
            "reference_seed_audio": f"{persona_cn}_参考.wav"
        }
        with open(design_file, 'w', encoding='utf-8') as f:
            json.dump(design_data, f, ensure_ascii=False, indent=2)
        print(f"🧪 [设计配方] 已归档：voice_designs/{persona_cn}.json")

    # --- 分支 B：生成历史日志 ---
    log_dir = os.path.join(base_dir, "assets/production")
    os.makedirs(log_dir, exist_ok=True)
    log_file = os.path.join(log_dir, f"{persona_cn}_生成历史.json")
    
    new_log = {
        "audio_file": os.path.basename(audio_path),
        "title": config.get("title", "未命名"),
        "episode": episode,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_dialogue": is_dial
    }
    
    if is_dial:
        new_log["dialogue_lines"] = config["lines"]
    else:
        new_log["text"] = config.get("text", "")

    history = {"persona": persona_cn, "records": []}
    if os.path.exists(log_file):
        try:
            with open(log_file, 'r', encoding='utf-8') as f:
                history = json.load(f)
        except: pass
    history["records"].append(new_log)
    with open(log_file, 'w', encoding='utf-8') as f:
        json.dump(history, f, ensure_ascii=False, indent=2)
    print(f"📄 [生成日志] 已更新：assets/metadata/production_logs/{persona_cn}_生成历史.json")

def write_generation_json(base_dir: str, persona: str, source: str = "design") -> str:
    """生成“可直接用于后续生成”的 JSON 配置模板。

    该文件用于标准化后续生产流程：
    - 克隆/对话统一基于 assets/temp 中的标准样音
    - 文案、语气、情绪可按任务修改
    """
    persona_key = str(persona or "").strip() or "unknown_persona"
    persona_cn = sanitize_path_component(get_persona_cn(persona_key), fallback="未命名角色")
    gen_dir = os.path.join(base_dir, "configs", "generated")
    os.makedirs(gen_dir, exist_ok=True)

    payload = {
        "type": "single",
        "content_type": "movie",
        "model_size": "1.7B",
        "model_type": "Base",
        "persona": persona_key,
        "text": "请替换成你要生成的文案",
        "tone": "",
        "emotion": "",
        "title": f"{persona_cn}_标准音生成",
        "episode": "GEN",
        "meta": {
            "created_from": source,
            "standard_seed": f"assets/temp/当前参考_{persona_cn}.wav"
        }
    }

    file_name = f"{sanitize_path_component(persona_key, fallback='unknown_persona')}_generate.json"
    file_path = os.path.join(gen_dir, file_name)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(payload, f, ensure_ascii=False, indent=2)
    return file_path

def upsert_persona_mapping(
    base_dir: str,
    persona_key: str,
    persona_name: str,
    ref_rel: str,
    design_rel: str = "",
    instruction: str = "",
) -> str:
    """新增或更新 personas.json 的映射关系。

    设计模式完成后调用该函数，把角色映射直接指向 temp 标准样音，
    确保后续单人生成/对话统一走 temp 参考链路。
    """
    key = sanitize_path_component(persona_key, fallback="unknown_persona")
    name = sanitize_path_component(persona_name, fallback="未命名角色")

    persona_file = os.path.join(base_dir, "configs", "personas.json")
    data: Dict[str, Any] = {}
    if os.path.exists(persona_file):
        try:
            with open(persona_file, "r", encoding="utf-8") as f:
                loaded = json.load(f)
                if isinstance(loaded, dict):
                    data = loaded
        except Exception:
            data = {}

    current = data.get(key, {})
    if not isinstance(current, dict):
        current = {}

    current["name"] = name
    current["ref"] = _normalize_ref_path(ref_rel)
    if design_rel:
        current["design"] = _normalize_ref_path(design_rel)
    if instruction.strip():
        current["instruction"] = instruction.strip()

    data[key] = current
    with open(persona_file, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    return persona_file
