"""VoxCraft 声坊 Web UI — FastAPI 后端

启动方式:
    .venv/bin/python -m web.app
    或
    .venv/bin/voice web
"""

import os
import sys
import json
import re
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
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

OUT_DIR = BASE_DIR / "out"
TEMP_DIR = BASE_DIR / "assets" / "temp"
REF_DIR = BASE_DIR / "assets" / "reference_audio"
PERSONAS_FILE = BASE_DIR / "configs" / "personas.json"
SCRIPTS_FILE = BASE_DIR / "configs" / "scripts.json"
MODELS_DIR = BASE_DIR / "models"

for d in [OUT_DIR, TEMP_DIR, REF_DIR]:
    d.mkdir(parents=True, exist_ok=True)

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
        except Exception as e:
            _update_task(task_id, status="error", error=str(e),
                         completed_at=datetime.now().strftime("%H:%M:%S"))


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
        temp_path = TEMP_DIR / f"当前参考_{display_name}.wav"
        if temp_path.exists():
            ref_path = temp_path
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
app = FastAPI(title="VoxCraft 声坊", version="0.2.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# 挂载静态文件
app.mount("/static", StaticFiles(directory=str(Path(__file__).parent / "static")), name="static")
# index.html 里的 logo 走 /assets/branding/...，但此前只挂了 /static，
# 于是首页左上角 logo 一直是碎图（README 里的截图也就跟着碎）。
_ASSETS_DIR = Path(__file__).parent.parent / "assets"
if _ASSETS_DIR.is_dir():
    app.mount("/assets", StaticFiles(directory=str(_ASSETS_DIR)), name="assets")


# ── 页面路由 ──────────────────────────────────────────────
@app.get("/")
async def index():
    return FileResponse(str(Path(__file__).parent / "static" / "index.html"))


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
    preset_dir = BASE_DIR / "configs" / "presets"
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
    display_name = pdata.get("name", key)

    # 优先 temp 样音
    temp_path = TEMP_DIR / f"当前参考_{display_name}.wav"
    if temp_path.exists():
        return FileResponse(str(temp_path), media_type="audio/wav")

    # 其次 ref
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
                name = val.get("name", key)
                temp_path = TEMP_DIR / f"当前参考_{name}.wav"
                ref_rel = val.get("ref", "")
                ref_path = BASE_DIR / ref_rel if ref_rel else None
                registered[key] = {
                    **val,
                    "source": "registered",
                    "has_temp": temp_path.exists(),
                    "has_ref": ref_path.exists() if ref_path else False,
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


@app.get("/api/llm/status")
async def llm_status():
    """检测 FreeLLMAPI 是否可用"""
    from core.llm_client import check_status
    return check_status()


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


# ── Suno AI 音乐（voxsuno 集成）────────────────────────────
#
# 声音一条龙工作台的最后一环：用 VoxCraft 复刻的声音（或任何已建 persona）
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


# ── 启动入口 ──────────────────────────────────────────────
if __name__ == "__main__":
    import uvicorn
    print("=" * 50)
    print("  VoxCraft 声坊 Web UI")
    print("  http://localhost:8866")
    print("=" * 50)
    uvicorn.run(app, host="0.0.0.0", port=8866)
