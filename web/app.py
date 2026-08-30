"""VoxFlow 声流 Web UI — FastAPI 后端

启动方式:
    .venv/bin/python -m web.app
    或
    .venv/bin/voice web
"""

import os
import sys
import json
import re
import shutil
import threading
import time
import queue as queue_mod
import uuid
from datetime import datetime
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# ── 路径设置 ──────────────────────────────────────────────
# 代码和数据分开：代码在项目目录，数据在 ~/.voxflow。
# 混在一起的话，换个目录 clone、git clean 一下，音色和歌就没了 ——
# 代码 git clone 随时能拿，数据没了就没了，两者不该同生共死。
# 真源见 core/paths.py。
_PROJECT_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_PROJECT_DIR))

from core.paths import (  # noqa: E402
    DATA_DIR, OUT_DIR, TEMP_DIR, REF_DIR, MODELS_DIR,
    PERSONAS_FILE, SCRIPTS_FILE, PROJECT_DIR, ensure_dirs,
)

# BASE_DIR 是数据根 —— personas.json 里的 ref 存的是相对它的路径
BASE_DIR = DATA_DIR
ensure_dirs()

# ── 引擎单例（懒加载） ────────────────────────────────────
_engine_lock = threading.Lock()
_base_engine = None
_design_engine = None
_processor = None
_model_status = {"base": False, "design": False, "loading": False, "error": ""}

# ── 异步任务队列 ──────────────────────────────────────────
_task_queue: queue_mod.Queue = queue_mod.Queue()
_tasks: dict[str, dict] = {}  # task_id -> task info
_tasks_lock = threading.Lock()
_worker_started = False


def _submit_task(task_type: str, label: str, params: dict) -> str:
    """提交一个异步任务，返回 task_id"""
    task_id = uuid.uuid4().hex[:8]
    task = {
        "id": task_id,
        "type": task_type,  # "clone" | "design"
        "label": label,
        "status": "queued",  # queued | running | done | error | cancelled
        "progress": 0,       # 0-100
        "stage": "",         # "加载模型中..." | "生成音频中..." | ""
        "params": params,
        "result": None,      # 成功时的返回数据
        "error": None,       # 失败时的错误信息
        "created_at": datetime.now().strftime("%H:%M:%S"),
        "completed_at": None,
    }
    with _tasks_lock:
        _tasks[task_id] = task
    _task_queue.put(task_id)
    _ensure_worker()
    return task_id


def _update_task(task_id: str, **kwargs):
    """更新任务状态"""
    with _tasks_lock:
        if task_id not in _tasks:
            return
        _tasks[task_id].update(kwargs)


def _ensure_worker():
    """确保 worker 线程已启动"""
    global _worker_started
    if _worker_started:
        return
    _worker_started = True
    t = threading.Thread(target=_task_worker, daemon=True)
    t.start()


def _task_worker():
    """后台 worker：从队列取任务执行"""
    while True:
        task_id = _task_queue.get()
        if task_id is None:
            break
        with _tasks_lock:
            task = _tasks.get(task_id)
            if task is None or task["status"] == "cancelled":
                continue
            task["status"] = "running"

        try:
            if task["type"] == "clone":
                _run_clone_task(task_id, task["params"], _update_task)
            elif task["type"] == "design":
                _run_design_task(task_id, task["params"], _update_task)
            elif task["type"] == "suno":
                _run_suno_task(task_id, task["params"], _update_task)
            elif task["type"] == "dialogue":
                _run_dialogue_task(task_id, task["params"], _update_task)
        except Exception as e:
            _update_task(task_id, status="error", error=str(e),
                         completed_at=datetime.now().strftime("%H:%M:%S"))


def _run_dialogue_task(task_id: str, params: dict, update_fn):
    """执行多角色剧本对话合成任务"""
    import torch
    from core.modes.cloner import CloneMode
    from core.modes.dialogue import DialogueMode

    update_fn(task_id, progress=10, stage="加载 Base 模型中...")
    engine = _get_base_engine()
    processor = _get_processor()
    cloner = CloneMode(engine, processor)
    dialogue = DialogueMode(engine, processor, cloner)

    update_fn(task_id, progress=30, stage="生成剧本音频中...")
    torch.manual_seed(42)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(42)

    final_path = dialogue.run(params)
    out_filename = os.path.basename(final_path)

    update_fn(
        task_id,
        progress=100,
        stage="完成",
        status="done",
        result={
            "ok": True,
            "filename": out_filename,
            "urls": [f"/api/audio/{out_filename}"],
            "files": [out_filename]
        },
        completed_at=datetime.now().strftime("%H:%M:%S")
    )


def _run_clone_task(task_id: str, params: dict, update_fn):
    """执行克隆合成任务"""
    import soundfile as sf
    import torch
    from core.modes.cloner import CloneMode
    from core.utils import get_persona_map, get_persona_cn

    req = CloneRequest(**params)
    if not req.text.strip():
        raise ValueError("文本不能为空")
    if len(req.text) > 400:
        raise ValueError(f"文本过长（{len(req.text)} > 400 字）")

    persona_map = get_persona_map()
    if req.persona not in persona_map:
        raise ValueError(f"音色 {req.persona} 未注册")

    pdata = persona_map[req.persona]
    if not isinstance(pdata, dict):
        pdata = {}
    display_name = get_persona_cn(req.persona)

    # 解析参考音频
    ref_path = None
    if req.reference_audio:
        p = Path(req.reference_audio)
        if not p.is_absolute():
            p = BASE_DIR / req.reference_audio
        if p.exists():
            ref_path = p
    if not ref_path:
        ref_rel = pdata.get("ref", "")
        if ref_rel:
            p = BASE_DIR / ref_rel
            if p.exists():
                ref_path = p
    if not ref_path:
        raise ValueError(
            f"音色 {req.persona} 未找到参考音频。"
            f"请先上传参考音频"
        )

    # 构建指令
    base_instruct = pdata.get("instruction", "")
    if req.emotion_priority:
        final_instruct = (req.tone or req.emotion or "").strip()
    else:
        raw = " ".join(filter(None, [req.tone or "", req.emotion or ""]))
        final_instruct = f"{base_instruct} {raw}".strip()

    # 加载引擎
    update_fn(task_id, progress=10, stage="加载模型中...")
    engine = _get_base_engine()
    processor = _get_processor()
    cloner = CloneMode(engine, processor)

    update_fn(task_id, progress=30, stage="生成音频中...")
    torch.manual_seed(42)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(42)

    wavs, sr = cloner.run(
        persona=req.persona,
        text=req.text,
        lang="Chinese",
        instruct=final_instruct,
        emotion_priority=req.emotion_priority,
        allow_ref_fallback=True,
        reference_audio=str(ref_path),
    )

    update_fn(task_id, progress=80, stage="保存文件中...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", display_name)
    out_filename = f"[克隆]{safe_name}_{ts}.wav"
    out_path = OUT_DIR / out_filename
    sf.write(str(out_path), wavs[0], sr)
    processor.apply_post_tuning(str(out_path))

    update_fn(task_id, progress=100, stage="完成",
              status="done",
              result={
                  "ok": True,
                  "filename": out_filename,
                  "url": f"/api/audio/{out_filename}",
                  "persona": display_name,
                  "text": req.text,
              },
              completed_at=datetime.now().strftime("%H:%M:%S"))


def _run_design_task(task_id: str, params: dict, update_fn):
    """执行音色设计任务"""
    import soundfile as sf
    from core.modes.designer import DesignMode
    from core.utils import (
        upsert_persona_mapping,
        resolve_design_voice_key,
        write_generation_json,
    )

    req = DesignRequest(**params)
    if not (req.tone or req.emotion):
        raise ValueError("必须提供 tone 或 emotion")
    if not req.text.strip():
        req.text = "这是一段用于音色建模的短句，请保持自然呼吸。"
    if len(req.text) > 45:
        raise ValueError(f"设计文本过长（{len(req.text)} > 45 字）")

    instruct = " ".join(p.strip() for p in [req.tone, req.emotion] if p.strip())

    update_fn(task_id, progress=10, stage="加载模型中...")
    engine = _get_design_engine()
    processor = _get_processor()
    designer = DesignMode(engine, processor)

    update_fn(task_id, progress=30, stage="设计音色中...")
    wavs, sr = designer.run(text=req.text, lang="Chinese", instruct=instruct)

    update_fn(task_id, progress=80, stage="保存文件中...")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    safe_name = re.sub(r"[^\w\u4e00-\u9fff-]", "_", req.voice_name)
    out_filename = f"[设计]{safe_name}_{ts}.wav"
    out_path = OUT_DIR / out_filename
    sf.write(str(out_path), wavs[0], sr)
    processor.apply_design_cleanup(str(out_path))

    result = {
        "ok": True,
        "filename": out_filename,
        "url": f"/api/audio/{out_filename}",
        "voice_name": req.voice_name,
    }

    if req.commit:
        voice_key = resolve_design_voice_key({"voice_name": req.voice_name})
        temp_seed_path = processor.extract_voice_seed(
            str(out_path), req.voice_name, max_sec=10, skip_start_ms=0
        )
        ref_rel = os.path.relpath(str(temp_seed_path), str(BASE_DIR)).replace("\\", "/")
        design_rel = f"voice_designs/{safe_name}.json"
        upsert_persona_mapping(
            str(BASE_DIR),
            persona_key=voice_key,
            persona_name=req.voice_name,
            ref_rel=ref_rel,
            design_rel=design_rel,
            instruction=instruct,
        )
        write_generation_json(str(BASE_DIR), voice_key, source="voice_design")
        result["committed"] = True
        result["persona_key"] = voice_key

    update_fn(task_id, progress=100, stage="完成",
              status="done",
              result=result,
              completed_at=datetime.now().strftime("%H:%M:%S"))


def _check_model_dir(model_type: str) -> bool:
    """检查模型是否下载完成（不是 .incomplete 文件）"""
    if model_type == "VoiceDesign":
        p = MODELS_DIR / "VoiceDesign-1.7B"
    else:
        p = MODELS_DIR / "Base-1.7B"
    if not p.exists():
        return False
    # 检查是否有完整的 model.safetensors（不是 .incomplete）
    safetensors = list(p.glob("*.safetensors"))
    incomplete = list(p.glob("*.incomplete"))
    return len(safetensors) > 0 and len(incomplete) == 0


def _model_downloading(model_type: str) -> bool:
    """检查模型是否正在下载"""
    if model_type == "VoiceDesign":
        p = MODELS_DIR / "VoiceDesign-1.7B"
    else:
        p = MODELS_DIR / "Base-1.7B"
    if not p.exists():
        return False
    return len(list(p.glob("*.incomplete"))) > 0


def _get_processor():
    global _processor
    if _processor is None:
        from core.processor import AudioProcessor
        _processor = AudioProcessor(str(BASE_DIR))
    return _processor


def _get_base_engine():
    """懒加载 Base 引擎（克隆模式用）"""
    global _base_engine, _model_status
    if _base_engine is not None:
        return _base_engine

    with _engine_lock:
        if _base_engine is not None:
            return _base_engine
        if not _check_model_dir("Base"):
            raise RuntimeError(
                f"Base 模型未下载。请先运行 install.sh 或手动下载:\n"
                f"  .venv/bin/python -m modelscope.cli.cli download "
                f"--model Qwen/Qwen3-TTS-12Hz-1.7B-Base --local_dir ./models/Base-1.7B"
            )
        from core.engine import TTSBaseEngine
        print("🚀 正在加载 Base-1.7B 引擎...")
        _base_engine = TTSBaseEngine("Base", "1.7B")
        _model_status["base"] = True
        print("✅ Base 引擎就绪")
        return _base_engine


def _get_design_engine():
    """懒加载 VoiceDesign 引擎（设计模式用）"""
    global _design_engine, _model_status
    if _design_engine is not None:
        return _design_engine

    with _engine_lock:
        if _design_engine is not None:
            return _design_engine
        if not _check_model_dir("VoiceDesign"):
            raise RuntimeError(
                f"VoiceDesign 模型未下载。请手动下载:\n"
                f"  .venv/bin/python -m modelscope.cli.cli download "
                f"--model Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign --local_dir ./models/VoiceDesign-1.7B"
            )
        from core.engine import TTSBaseEngine
        print("🚀 正在加载 VoiceDesign-1.7B 引擎...")
        _design_engine = TTSBaseEngine("VoiceDesign", "1.7B")
        _model_status["design"] = True
        print("✅ VoiceDesign 引擎就绪")
        return _design_engine


# ── Pydantic 模型 ─────────────────────────────────────────
class CloneRequest(BaseModel):
    persona: str
    text: str
    tone: Optional[str] = ""
    emotion: Optional[str] = ""
    emotion_priority: bool = False
    reference_audio: Optional[str] = None


class DesignRequest(BaseModel):
    voice_name: str
    text: str = "这是一段用于音色建模的短句，请保持自然呼吸。"
    tone: str = ""
    emotion: str = ""
    commit: bool = False


class PersonaAddRequest(BaseModel):
    key: str
    name: Optional[str] = None
    instruction: Optional[str] = ""


class ScriptSaveRequest(BaseModel):
    title: str
    content: str


# ── FastAPI 应用 ──────────────────────────────────────────
app = FastAPI(title="VoxFlow 声流", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

class _NoCacheStaticFiles(StaticFiles):
    """
    本地工具的静态文件服务：一律不缓存。

    这是个跑在 127.0.0.1 的单用户桌面工具，不是公网站点。HTTP 缓存那一整套
    （长缓存 + 内容哈希 + 分层策略）解决的是「跨网络重复下载」和「CDN 回源」，
    本地环回连接上这两件事都不存在 —— 收益是零，代价却是实打实的：
    改了 logo 页面还是旧的，改了前端要硬刷新，每次都得先怀疑一遍是不是缓存。

    所以不分层、不区分构建产物和品牌资产，全部 no-store。
    """

    def file_response(self, *args, **kwargs):
        resp = super().file_response(*args, **kwargs)
        resp.headers["Cache-Control"] = "no-store"
        return resp


_STATIC_DIR = Path(__file__).parent / "static"
app.mount("/static", _NoCacheStaticFiles(directory=str(_STATIC_DIR)), name="static")

# index.html 里的 logo 走 /assets/branding/...，但此前只挂了 /static，
# 于是首页左上角 logo 一直是碎图（README 里的截图也就跟着碎）。
_ASSETS_DIR = Path(__file__).parent.parent / "assets"
if _ASSETS_DIR.is_dir():
    app.mount("/assets", _NoCacheStaticFiles(directory=str(_ASSETS_DIR)), name="assets")


# ── 页面路由 ──────────────────────────────────────────────
@app.get("/")
async def index():
    # 入口页也不缓存 —— 它缓存了，整个前端就都停在旧版本上，
    # 后面所有资源无论怎么改都看不到。
    return FileResponse(
        str(_STATIC_DIR / "index.html"),
        headers={"Cache-Control": "no-store"},
    )


# ── API 路由 ──────────────────────────────────────────────
def _model_download_progress(model_type: str) -> dict:
    """检查模型下载进度"""
    if model_type == "VoiceDesign":
        p = MODELS_DIR / "VoiceDesign-1.7B"
        expected_size = 3_600_000_000  # ~3.6GB
    else:
        p = MODELS_DIR / "Base-1.7B"
        expected_size = 3_600_000_000  # ~3.6GB
    if not p.exists():
        return {"downloading": False, "downloaded_mb": 0, "total_mb": round(expected_size / 1024 / 1024), "percent": 0}
    incomplete = list(p.glob("*.incomplete"))
    complete = list(p.glob("*.safetensors"))
    if incomplete:
        size = sum(f.stat().st_size for f in incomplete)
        return {
            "downloading": True,
            "downloaded_mb": round(size / 1024 / 1024),
            "total_mb": round(expected_size / 1024 / 1024),
            "percent": round(size / expected_size * 100),
        }
    if complete:
        size = sum(f.stat().st_size for f in complete)
        return {
            "downloading": False,
            "downloaded_mb": round(size / 1024 / 1024),
            "total_mb": round(size / 1024 / 1024),
            "percent": 100,
        }
    return {"downloading": False, "downloaded_mb": 0, "total_mb": round(expected_size / 1024 / 1024), "percent": 0}


@app.get("/api/status")
async def get_status():
    """检查模型和系统状态"""
    base_prog = _model_download_progress("Base")
    design_prog = _model_download_progress("VoiceDesign")
    return {
        "base_model": _check_model_dir("Base"),
        "design_model": _check_model_dir("VoiceDesign"),
        "base_downloading": base_prog["downloading"],
        "design_downloading": design_prog["downloading"],
        "base_progress": base_prog,
        "design_progress": design_prog,
        "base_loaded": _base_engine is not None,
        "design_loaded": _design_engine is not None,
        "loading": _model_status["loading"],
        "error": _model_status["error"],
    }


def _scan_design_presets() -> list:
    """扫描 configs/presets/ 目录，加载设计配方"""
    # presets 是代码自带的内置预设，留在项目里跟着版本走；
    # 你自己存的预设落在数据目录。两处都扫。
    preset_dirs = [DATA_DIR / "configs" / "presets", PROJECT_DIR / "configs" / "presets"]
    preset_dir = next((d for d in preset_dirs if d.is_dir()), preset_dirs[-1])
    result = []
    if not preset_dir.exists():
        return result
    for f in sorted(preset_dir.glob("*.json")):
        try:
            with open(f, "r", encoding="utf-8") as fh:
                cfg = json.load(fh)
            if cfg.get("model_type") != "VoiceDesign":
                continue
            voice_name = cfg.get("voice_name", "").strip()
            if not voice_name:
                continue
            result.append({
                "voice_name": voice_name,
                "config_file": f.name,
                "tone": cfg.get("tone", ""),
                "emotion": cfg.get("emotion", ""),
                "text": cfg.get("text", ""),
            })
        except Exception:
            continue
    return result


@app.get("/api/persona-audio")
async def get_persona_audio(key: str):
    """获取音色的参考音频（优先 temp 样音，其次原始 ref）"""
    if not PERSONAS_FILE.exists():
        raise HTTPException(404, "personas.json 不存在")
    try:
        with open(PERSONAS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception:
        raise HTTPException(500, "读取 personas.json 失败")

    if key not in data:
        raise HTTPException(404, f"音色 {key} 不存在")

    pdata = data[key]
    if not isinstance(pdata, dict):
        pdata = {}
    ref_rel = pdata.get("ref", "")
    if ref_rel:
        ref_path = BASE_DIR / ref_rel
        if ref_path.exists():
            return FileResponse(str(ref_path), media_type="audio/wav")

    raise HTTPException(404, f"音色 {key} 没有可用的参考音频")


@app.get("/api/personas")
async def list_personas():
    """列出所有已注册音色 + 设计预设"""
    # 从 personas.json 加载已注册音色
    registered = {}
    if PERSONAS_FILE.exists():
        try:
            with open(PERSONAS_FILE, "r", encoding="utf-8") as f:
                data = json.load(f)
        except Exception:
            data = {}
        for key, val in data.items():
            if isinstance(val, dict):
                ref_rel = val.get("ref", "")
                ref_path = BASE_DIR / ref_rel if ref_rel else None
                has_audio = ref_path.exists() if ref_path else False
                registered[key] = {
                    **val,
                    "source": "registered",
                    # has_temp / has_ref 曾经是两条路径（按名字拼的样音、ref 指的
                    # 原始素材），实际指向同一个文件。合成一个 has_audio。
                    "has_audio": has_audio,
                    "has_temp": has_audio,
                    "has_ref": has_audio,
                }
            else:
                registered[key] = {
                    "name": val,
                    "source": "registered",
                    "has_temp": False,
                    "has_ref": False,
                }

    # 设计预设
    presets = _scan_design_presets()

    return {"personas": registered, "presets": presets, "total": len(registered)}


@app.post("/api/personas/add")
async def add_persona(
    key: str = Form(...),
    name: str = Form(None),
    instruction: str = Form(""),
    audio: UploadFile = File(...),
):
    """上传参考音频并注册新音色"""
    from core.utils import upsert_persona_mapping, sanitize_path_component

    display_name = name or key
    safe_key = sanitize_path_component(key, fallback="unknown")
    safe_name = sanitize_path_component(display_name, fallback="未命名角色")

    # 保存上传的音频
    ext = os.path.splitext(audio.filename or "audio.wav")[1].lower()
    if ext not in (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac"):
        ext = ".wav"

    ref_filename = f"{safe_name}_参考{ext}"
    ref_path = REF_DIR / ref_filename
    with open(ref_path, "wb") as f:
        content = await audio.read()
        f.write(content)

    # 提取标准样音
    processor = _get_processor()
    temp_path = processor.extract_voice_seed(
        str(ref_path), display_name, max_sec=10, skip_start_ms=1500
    )

    ref_rel = os.path.relpath(str(temp_path), str(BASE_DIR)).replace("\\", "/")
    upsert_persona_mapping(
        str(BASE_DIR),
        persona_key=safe_key,
        persona_name=display_name,
        ref_rel=ref_rel,
        design_rel="",
        instruction=instruction or "",
    )

    return {"ok": True, "key": safe_key, "name": display_name, "ref": ref_rel}


@app.patch("/api/personas/{key}")
async def update_persona(key: str, name: str = Form(None), desc: str = Form(None)):
    """
    改音色的名字和描述。就是改两个字段，不碰任何文件。

    这里曾经是一百行：改名要连带重命名 assets/temp 下的样音、
    voice_designs 下的配方，还要挡重名、失败回滚。原因是当时读音频靠
    `当前参考_{名字}.wav` 拼路径 —— 名字成了路径的一部分，改名自然要动文件。

    根子上的修法不是把重命名写得更严密，是**不让名字参与路径**：
    参考音频的路径本来就完整存在 ref 字段里（注册音色时写进去的），
    改成只读 ref 之后，名字回归成纯粹的名字，改名就是改个字段。
    """
    if not PERSONAS_FILE.exists():
        raise HTTPException(404, "personas.json 不存在")

    with open(PERSONAS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if key not in data:
        raise HTTPException(404, f"音色 {key} 不存在")

    entry = data[key] if isinstance(data[key], dict) else {"name": data[key]}

    # 只写传了的字段。空字符串是有意义的输入（清空描述），判 None 不判真值。
    if name is not None and name.strip():
        entry["name"] = name.strip()
    if desc is not None:
        entry["desc"] = desc.strip()

    data[key] = entry
    with open(PERSONAS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {"ok": True, "key": key, "name": entry.get("name", key), "desc": entry.get("desc", "")}


@app.delete("/api/personas/{key}")
async def delete_persona(key: str):
    """删除音色注册（不删除音频文件）"""
    if not PERSONAS_FILE.exists():
        raise HTTPException(404, "personas.json 不存在")

    with open(PERSONAS_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if key not in data:
        raise HTTPException(404, f"音色 {key} 不存在")

    del data[key]
    with open(PERSONAS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    return {"ok": True}


@app.post("/api/clone")
async def clone(req: CloneRequest):
    """提交克隆合成任务（异步）"""
    if not req.text.strip():
        raise HTTPException(400, "文本不能为空")
    if len(req.text) > 400:
        raise HTTPException(400, f"文本过长（{len(req.text)} > 400 字）")

    label = req.text[:20].replace("\n", " ").strip()
    if len(req.text) > 20:
        label += "..."

    task_id = _submit_task("clone", label, req.model_dump())
    return {"task_id": task_id, "status": "queued"}


@app.post("/api/design")
async def design(req: DesignRequest):
    """提交音色设计任务（异步）"""
    if not (req.tone or req.emotion):
        raise HTTPException(400, "必须提供 tone 或 emotion（至少一个）")
    if req.text and len(req.text) > 45:
        raise HTTPException(400, f"设计文本过长（{len(req.text)} > 45 字）")

    label = f"{req.voice_name} — {req.tone or req.emotion}"
    task_id = _submit_task("design", label, req.model_dump())
    return {"task_id": task_id, "status": "queued"}


@app.get("/api/tasks")
async def list_tasks():
    """列出所有任务（按创建时间倒序）"""
    with _tasks_lock:
        tasks = sorted(
            _tasks.values(),
            key=lambda t: t["created_at"],
            reverse=True,
        )
    # 清理超过 50 条的旧任务
    if len(tasks) > 50:
        old_ids = [t["id"] for t in tasks[50:]]
        with _tasks_lock:
            for tid in old_ids:
                _tasks.pop(tid, None)
        tasks = tasks[:50]
    return {"tasks": [
        {
            "id": t["id"],
            "type": t["type"],
            "label": t["label"],
            "status": t["status"],
            "progress": t["progress"],
            "stage": t["stage"],
            "result": t["result"],
            "error": t["error"],
            "created_at": t["created_at"],
            "completed_at": t["completed_at"],
        }
        for t in tasks
    ]}


@app.delete("/api/tasks/{task_id}")
async def cancel_task(task_id: str):
    """取消任务（仅 queued 状态可取消）"""
    with _tasks_lock:
        task = _tasks.get(task_id)
        if task is None:
            raise HTTPException(404, "任务不存在")
        if task["status"] not in ("queued",):
            raise HTTPException(400, f"任务正在执行或已完成，无法取消")
        task["status"] = "cancelled"
        task["completed_at"] = datetime.now().strftime("%H:%M:%S")
    return {"ok": True}


@app.get("/api/scripts")
async def list_scripts():
    """列出所有保存的文案"""
    if not SCRIPTS_FILE.exists():
        return {"scripts": []}
    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            return {"scripts": json.load(f)}
    except Exception:
        return {"scripts": []}


@app.post("/api/scripts")
async def save_script(req: ScriptSaveRequest):
    """保存文案到文案库"""
    if not req.content.strip():
        raise HTTPException(400, "文案内容不能为空")

    # 读取现有
    if SCRIPTS_FILE.exists():
        try:
            with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
                scripts = json.load(f)
        except Exception:
            scripts = []
    else:
        scripts = []

    # 去重：如果标题相同则更新内容
    title = req.title.strip() or req.content[:20].strip() + "..."
    found = False
    for s in scripts:
        if s.get("title") == title:
            s["content"] = req.content.strip()
            s["updated"] = datetime.now().strftime("%Y-%m-%d %H:%M")
            found = True
            break
    if not found:
        scripts.insert(0, {
            "id": uuid.uuid4().hex[:8],
            "title": title,
            "content": req.content.strip(),
            "created": datetime.now().strftime("%Y-%m-%d %H:%M"),
            "updated": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })

    with open(SCRIPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(scripts, f, ensure_ascii=False, indent=2)

    return {"ok": True, "scripts": scripts}


@app.delete("/api/scripts/{script_id}")
async def delete_script(script_id: str):
    """删除文案"""
    if not SCRIPTS_FILE.exists():
        raise HTTPException(404, "文案库不存在")
    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            scripts = json.load(f)
    except Exception:
        scripts = []

    before = len(scripts)
    scripts = [s for s in scripts if s.get("id") != script_id]
    if len(scripts) == before:
        raise HTTPException(404, "文案不存在")

    with open(SCRIPTS_FILE, "w", encoding="utf-8") as f:
        json.dump(scripts, f, ensure_ascii=False, indent=2)

    return {"ok": True, "scripts": scripts}


AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
MEDIA_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".flac": "audio/flac",
    ".ogg": "audio/ogg",
}


@app.get("/api/audio-list")
async def audio_list():
    """列出已生成的音频文件（TTS wav + Suno 音乐 mp3/m4a 统一管理）"""
    files = []
    if OUT_DIR.exists():
        for f in sorted(OUT_DIR.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if f.suffix.lower() in AUDIO_EXTS:
                stat = f.stat()
                files.append({
                    "filename": f.name,
                    "url": f"/api/audio/{f.name}",
                    "size": stat.st_size,
                    "size_mb": round(stat.st_size / 1024 / 1024, 2),
                    "created": datetime.fromtimestamp(stat.st_mtime).strftime(
                        "%Y-%m-%d %H:%M:%S"
                    ),
                    "kind": "suno" if "[Suno]" in f.name else "tts",
                })
    return {"files": files}


@app.get("/api/audio/{filename}")
async def get_audio(filename: str):
    """获取音频文件"""
    # 防止路径穿越
    safe = os.path.basename(filename)
    path = OUT_DIR / safe
    if not path.exists():
        raise HTTPException(404, f"音频文件不存在: {safe}")
    media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(str(path), media_type=media_type, filename=safe)


@app.delete("/api/audio/{filename}")
async def delete_audio(filename: str):
    """删除音频文件"""
    safe = os.path.basename(filename)
    path = OUT_DIR / safe
    if not path.exists():
        raise HTTPException(404, f"音频文件不存在: {safe}")
    path.unlink()
    return {"ok": True}


# ── LLM (FreeLLMAPI) ────────────────────────────────────────

class LLMGenerateRequest(BaseModel):
    prompt: str
    word_count: Optional[int] = None

class LLMPolishRequest(BaseModel):
    text: str
    style: str = ""


class LLMLyricsRequest(BaseModel):
    prompt: str
    style: str = ""


@app.get("/api/llm/status")
async def llm_status():
    """检测 LLM 后端是否可用"""
    from core.llm_client import check_status
    return check_status()


# ── 作品流水线（可观测：每首歌走到哪一步）──────────────────

@app.get("/api/inbox")
async def inbox_scan():
    """
    扫下载目录里等着入库的音乐文件。

    ## 为什么需要这一步

    Suno 刻意防自动下载：API 返回的 audio_url 写死 `api/forbidden`，
    CDN 直链 403，网页播放走 blob/MSE 拿不到源地址，行内的下载菜单也不响应
    合成事件。硬绕这层反爬性价比极低 —— 而且下载本来就是个一次性动作，
    Suno 一次出两首，人本来就要听过才知道要哪首，顺手点一下下载的成本几乎为零。

    真正吃时间的是**后面那段**：填表、传文件、拼 Excel、三个平台各重复一遍。
    所以分工改成：人在浏览器点一下下载，工具接管之后的全部环节。

    这个端点就是接管的入口 —— 列出下载目录里最近的音频，让人挑哪些入库。
    """
    import time
    from pathlib import Path as _P

    AUDIO_EXTS = {".mp3", ".wav", ".m4a", ".flac", ".aac", ".ogg"}
    cutoff = time.time() - 7 * 86400        # 只看最近一周，避免翻出几年前的下载
    candidates = []

    for d in [_P.home() / "Downloads", OUT_DIR / MUSIC_SUBDIR]:
        if not d.is_dir():
            continue
        for f in d.iterdir():
            if f.suffix.lower() not in AUDIO_EXTS or not f.is_file():
                continue
            st = f.stat()
            if st.st_mtime < cutoff:
                continue
            candidates.append({
                "name": f.name,
                "path": str(f),
                "size_mb": round(st.st_size / 1024 / 1024, 1),
                "mtime": st.st_mtime,
                "in_library": d != _P.home() / "Downloads",   # 已经在库里的标出来
            })

    candidates.sort(key=lambda x: x["mtime"], reverse=True)
    return {"files": candidates[:40], "downloads_dir": str(_P.home() / "Downloads")}


@app.post("/api/inbox/import")
async def inbox_import(req: dict):
    """
    把选中的音频收进音乐库，并在流水线登记一条「已出歌」。

    **复制不移动**：下载目录是人的地盘，工具不该把人的文件搬走 ——
    万一认错了文件，原件还在。重名自动加后缀，不覆盖。

    登记成 generated 而不是 draft：文件都拿到了，歌显然已经出来了。
    下一步「选定这首」仍然要人点 —— 一次出两首，哪首更好只有人知道。
    """
    from pathlib import Path as _P
    from core import pipeline

    paths = req.get("paths") or []
    if not paths:
        raise HTTPException(400, "没有选择文件")

    music_dir = OUT_DIR / MUSIC_SUBDIR
    music_dir.mkdir(parents=True, exist_ok=True)
    imported = []

    for src_str in paths:
        src = _P(src_str)
        if not src.is_file():
            continue

        dst = music_dir / src.name
        if dst.resolve() != src.resolve():
            n = 1
            while dst.exists():
                dst = music_dir / f"{src.stem}_{n}{src.suffix}"
                n += 1
            shutil.copy2(src, dst)

        # 文件名去掉扩展名和 Suno 常见的后缀就是歌名
        title = re.sub(r"[_-]?(v\d+(\.\d+)?|extended|remaster)$", "", dst.stem, flags=re.I).strip()
        track_id = re.sub(r"[^\w\u4e00-\u9fff]+", "-", title).strip("-").lower() or dst.stem
        pipeline.upsert(track_id, title=title, stage="generated",
                        note=f"从 {src.parent.name} 导入")
        imported.append({"track_id": track_id, "title": title, "file": dst.name})

    return {"ok": True, "imported": imported, "count": len(imported)}


@app.get("/api/pipeline")
async def pipeline_list():
    """
    作品看板数据。

    这是「可观测流程」的数据源 —— 打开首页就能看到每首歌卡在哪一步，
    而不是自己去几个目录里翻文件猜。状态机与理由见 core/pipeline.py。
    """
    from core import pipeline
    return {
        "stages": pipeline.STAGES,
        "stage_labels": pipeline.STAGE_LABELS,
        "platforms": pipeline.PLATFORMS,
        "summary": pipeline.summary(),
        "tracks": pipeline.list_tracks(),
    }


@app.get("/api/publish-board")
async def publish_board():
    """发布账号、已发布曲目与云备份状态的同源看板数据。"""
    from core import pipeline
    return pipeline.publication_board()


class PipelineStageRequest(BaseModel):
    track_id: str
    stage: str


@app.post("/api/pipeline/stage")
async def pipeline_set_stage(req: PipelineStageRequest):
    """
    推进作品状态。**每一步都要人点** —— 尤其 selected → publishing
    那一下是「我确认要发这首」，不能因为文件齐了就自动跳。
    """
    from core import pipeline
    try:
        return {"ok": True, "track": pipeline.set_stage(req.track_id, req.stage)}
    except ValueError as e:
        raise HTTPException(400, str(e))


class PipelineTrackRequest(BaseModel):
    track_id: str
    title: str | None = None
    voice: str | None = None
    clip_id: str | None = None
    note: str | None = None


@app.post("/api/pipeline/track")
async def pipeline_upsert(req: PipelineTrackRequest):
    """登记或更新一首作品。"""
    from core import pipeline
    return {"ok": True, "track": pipeline.upsert(
        req.track_id, title=req.title, voice=req.voice,
        clip_id=req.clip_id, note=req.note,
    )}


class PipelinePlatformRequest(BaseModel):
    track_id: str
    platform: str
    status: str
    url: str | None = None
    note: str | None = None


@app.post("/api/pipeline/platform")
async def pipeline_platform(req: PipelinePlatformRequest):
    """
    记录某平台的发布状态。每个平台单独记 —— 同一首歌可能汽水已上架、
    网易云还在审核，只有一个全局状态表达不出这种情况。
    """
    from core import pipeline
    try:
        return {"ok": True, "track": pipeline.set_platform_status(
            req.track_id, req.platform, req.status, url=req.url, note=req.note,
        )}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/capabilities")
async def capabilities():
    """
    一次拿全「现在能干什么、还剩多少资源」。

    为什么要聚合成一个端点：这些状态本来散在三处，前端要并发调三个、各自处理
    超时和失败，还要自己拼出「能不能开工」这个判断。更要命的是**中台的身份和
    额度前端压根没调** —— 用户不知道自己是谁、还剩多少额度。

    **四项并行探测**：串行做要 4.6 秒（Suno CLI 冷启动 + 中台往返 + LLM 探活），
    而它们互不依赖。并行后总耗时取决于最慢的一项，不是四项之和。
    每项独立容错 —— 某个上游挂了只是那一项 unavailable。
    """
    import os, json as _json, subprocess, asyncio
    from urllib import request as _req

    def _probe_tts():
        # downloaded 是文件在磁盘、loaded 是已读进内存。对用户来说都是「能用」
        # （首次合成时才加载，约 10 秒），所以对外只给一个 ready，
        # 不把「未装载」这种实现细节顶到界面上。
        try:
            ok = (MODELS_DIR / "Base-1.7B").exists() and (MODELS_DIR / "VoiceDesign-1.7B").exists()
            return {"ready": ok, "detail": "本地模型" if ok else "模型未下载，跑 ./install.sh"}
        except Exception as e:
            return {"ready": False, "detail": str(e)[:60]}

    def _probe_suno():
        # 积分是硬约束 —— 没了就出不了歌，得让人提前看见
        try:
            r = subprocess.run([SUNO_BIN, "credits", "--json"],
                               capture_output=True, text=True, timeout=15)
            d = (_json.loads(r.stdout or "{}")).get("data", {})
            left = d.get("total_credits_left", 0)
            plan = (d.get("plan") or {}).get("name", "")
            return {"ready": bool(d.get("is_active")), "credits": left,
                    "plan": plan, "detail": f"{plan} · 剩 {left}"}
        except Exception:
            return {"ready": False, "credits": 0, "detail": "未登录或 CLI 不可用"}

    def _probe_studio():
        base_url = os.environ.get("VOXFLOW_LLM_BASE_URL", "")
        api_key = os.environ.get("VOXFLOW_LLM_API_KEY", "")
        if not (base_url and api_key and "manager.museav" in base_url):
            return {"ready": False, "identity": "", "detail": "未接中台（本地模式）"}
        try:
            # 必须带 User-Agent：默认的 Python-urllib/3.x 会被 CDN 当爬虫挡掉（403），
            # 而 curl 同样的请求是通的 —— 这种差异很容易被误判成「网络不通」。
            rq = _req.Request(f"{base_url}/me", headers={
                "Authorization": f"Bearer {api_key}", "User-Agent": "VoxFlow/0.3.0"})
            with _req.urlopen(rq, timeout=10) as resp:
                me = _json.loads(resp.read().decode())
            t = me.get("tenant") or {}
            who = t.get("nickname") or t.get("name") or "未知"
            return {"ready": True, "identity": who, "detail": f"租户 {who}"}
        except Exception as e:
            msg = str(e)
            hint = "凭据无效或被拦截" if ("403" in msg or "401" in msg) else "连不上中台"
            return {"ready": False, "identity": "", "detail": hint}

    def _probe_llm():
        try:
            from core.llm_client import check_status
            st = check_status()      # 内部有 60 秒缓存，不会每次都真打一次
            return {"ready": bool(st.get("available")), "model": st.get("model", ""),
                    "detail": st.get("error") or st.get("model", "")}
        except Exception as e:
            return {"ready": False, "model": "", "detail": str(e)[:60]}

    names = ["tts", "suno", "studio", "llm"]
    probes = [_probe_tts, _probe_suno, _probe_studio, _probe_llm]
    results = await asyncio.gather(*[asyncio.to_thread(f) for f in probes],
                                   return_exceptions=True)
    caps = {}
    for name, res in zip(names, results):
        caps[name] = res if isinstance(res, dict) else {"ready": False, "detail": "探测失败"}
    return caps


@app.post("/api/llm/generate")
async def llm_generate(req: LLMGenerateRequest):
    """AI 文案生成"""
    from core.llm_client import generate_script
    try:
        result = generate_script(req.prompt, req.word_count)
        return {"ok": True, "text": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/llm/polish")
async def llm_polish(req: LLMPolishRequest):
    """AI 文案润色"""
    from core.llm_client import polish_script
    try:
        result = polish_script(req.text, req.style)
        return {"ok": True, "text": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/llm/lyrics")
async def llm_lyrics(req: LLMLyricsRequest):
    """生成可直接提交给 Suno 的结构化歌词。"""
    if not req.prompt.strip():
        raise HTTPException(400, "请填写歌词主题，或先填写歌曲标题和风格标签")
    from core.llm_client import generate_lyrics
    try:
        return {"ok": True, "text": generate_lyrics(req.prompt, req.style)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── Suno AI 音乐（voxsuno 集成）────────────────────────────
#
# 声音一条龙工作台的最后一环：用 VoxFlow 复刻的声音（或任何已建 persona）
# 在 Suno 生成音乐，产物落回 out/ 由音频库统一管理。
# persona 在 suno.com 网页端创建（无公开 API），本模块负责登录态/生成/入库。

SUNO_BIN = os.path.expanduser("~/.cargo/bin/suno")
if not os.path.exists(SUNO_BIN):
    SUNO_BIN = "suno"  # 回退到 PATH
SUNO_STATE = os.path.expanduser("~/.voxsuno/personas.json")
MUSIC_SUBDIR = "music"  # Suno 音乐单独放 out/music，跟 TTS wav 分开


class SunoGenerateRequest(BaseModel):
    title: str = "Untitled"
    tags: str = ""
    lyrics: str = ""
    lyrics_file: Optional[str] = None
    persona: Optional[str] = None  # persona 名（查 ~/.voxsuno/personas.json）
    model: str = "v5.5"
    wait: bool = False
    download: bool = True  # 生成后拉回本地入库


@app.get("/api/suno/status")
async def suno_status():
    """Suno 登录态 + 余额 + 已保存 persona"""
    import subprocess
    try:
        r = subprocess.run(
            [SUNO_BIN, "credits", "--json"],
            capture_output=True, text=True, timeout=15,
        )
        data = json.loads(r.stdout or "{}")
        cred = data.get("data", {})
        authenticated = r.returncode == 0 and cred.get("is_active", False)
    except Exception:
        authenticated, cred = False, {}
    personas = {}
    if os.path.exists(SUNO_STATE):
        try:
            personas = json.load(open(SUNO_STATE))
        except Exception:
            personas = {}
    return {
        "ok": True,
        "authenticated": authenticated,
        "credits": cred.get("credits", 0),
        "total_credits_left": cred.get("total_credits_left", 0),
        "plan": (cred.get("plan") or {}).get("name", "") if isinstance(cred.get("plan"), dict) else "",
        "personas": personas,
        "suno_bin": SUNO_BIN,
    }


@app.post("/api/suno/generate")
async def suno_generate(req: SunoGenerateRequest):
    """提交 Suno 音乐生成任务（异步，走现有任务队列）"""
    task_id = _submit_task("suno", f"🎵 {req.title or 'Suno 音乐'}", req.model_dump())
    return {"task_id": task_id, "status": "queued"}


def _run_suno_task(task_id: str, params: dict, update_fn):
    """执行 Suno 音乐生成：调 suno CLI → 产物拷回 out/music"""
    import subprocess, shutil, glob

    req = SunoGenerateRequest(**params)
    if not os.path.exists(SUNO_BIN):
        raise ValueError(f"suno CLI 不存在: {SUNO_BIN}（先 cargo install suno）")

    music_dir = OUT_DIR / MUSIC_SUBDIR
    music_dir.mkdir(parents=True, exist_ok=True)

    # 解析 persona ID
    persona_id = None
    if req.persona:
        try:
            personas = json.load(open(SUNO_STATE))
            persona_id = (personas.get(req.persona) or {}).get("id")
        except Exception:
            persona_id = None
        if not persona_id and req.persona.startswith("{"):
            persona_id = req.persona  # 直接传 ID

    update_fn(task_id, progress=15, stage="调用 Suno 生成中...")
    cmd = [SUNO_BIN, "generate", "--title", req.title, "--model", req.model, "--wait"]
    if req.tags:
        cmd += ["--tags", req.tags]
    if req.lyrics:
        cmd += ["--lyrics", req.lyrics]
    elif req.lyrics_file and os.path.exists(req.lyrics_file):
        cmd += ["--lyrics-file", req.lyrics_file]
    if persona_id:
        cmd += ["--persona", persona_id]

    # 临时下载目录，生成后拷回 out/music
    import tempfile
    tmp = tempfile.mkdtemp(prefix="voxsuno_")
    cmd += ["--download", tmp]
    update_fn(task_id, progress=30, stage="Suno 生成中（约 1-3 分钟）...")

    r = subprocess.run(cmd, capture_output=True, text=True, timeout=360)
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-500:]
        raise ValueError(f"Suno 生成失败: {err}")

    update_fn(task_id, progress=85, stage="入库音频库...")
    # 把下载的音频拷回 out/music，带 [Suno] 前缀便于音频库识别
    copied = []
    for f in glob.glob(os.path.join(tmp, "*")):
        if os.path.splitext(f)[1].lower() in AUDIO_EXTS:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe_title = re.sub(r"[^\w\u4e00-\u9fff-]", "_", req.title)[:30]
            dest = music_dir / f"[Suno]{safe_title}_{ts}{os.path.splitext(f)[1].lower()}"
            shutil.copy2(f, dest)
            copied.append(str(dest))

    shutil.rmtree(tmp, ignore_errors=True)
    if not copied:
        raise ValueError("Suno 生成成功但没拿到音频文件（下载链路可能受 Suno schema drift 影响，见网页端）")

    update_fn(
        task_id, status="done", progress=100, stage="完成",
        result={"ok": True, "files": copied,
                "urls": [f"/api/audio/{MUSIC_SUBDIR}/{os.path.basename(c)}" for c in copied]},
    )


@app.post("/api/dialogue")
async def dialogue(req: dict):
    """提交多角色对话合成任务（异步）"""
    if "lines" not in req or not isinstance(req["lines"], list):
        raise HTTPException(400, "剧本格式错误，缺少台词 lines 列表")

    title = req.get("title", "未命名剧目")
    label = f"🎭 剧本: {title} ({len(req['lines'])} 句)"

    task_id = _submit_task("dialogue", label, req)
    return {"task_id": task_id, "status": "queued"}


@app.get("/api/audio/{subdir}/{filename}")
async def get_audio_subdir(subdir: str, filename: str):
    """获取子目录音频（out/music/...）"""
    safe_sub = os.path.basename(subdir)
    safe_name = os.path.basename(filename)
    path = OUT_DIR / safe_sub / safe_name
    if not path.exists():
        raise HTTPException(404, f"音频文件不存在: {safe_name}")
    media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(str(path), media_type=media_type, filename=safe_name)


@app.get("/api/cover/{track_id}")
async def get_cover(track_id: str):
    """
    作品封面。

    封面落在 publish/ 下（平台规定的目录结构，跟可随时清理的 out/ 分开），
    那一层没有静态挂载 —— 也不该挂：publish/ 里还有音频和 Excel，
    整个目录暴露出去没必要。按 track_id 单点取图即可。
    """
    from core import pipeline
    t = next((x for x in pipeline.list_tracks() if x["id"] == track_id), None)
    if not t or not t.get("cover_file"):
        raise HTTPException(404, "这首作品还没有封面")
    path = BASE_DIR / t["cover_file"]
    if not path.exists():
        raise HTTPException(404, f"封面文件不在了：{t['cover_file']}")
    return FileResponse(str(path), media_type=MEDIA_TYPES.get(path.suffix.lower(), "image/jpeg"),
                        headers={"Cache-Control": "no-store"})


# ── 启动入口 ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  VoxFlow 声流 Web UI")
    print("  http://localhost:8866")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8866)
