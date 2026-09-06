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
from datetime import datetime, timezone
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

from core import obs  # noqa: E402

# BASE_DIR 是数据根 —— personas.json 里的 ref 存的是相对它的路径
BASE_DIR = DATA_DIR
ensure_dirs()

# 建表 + 清过期日志。都是幂等的，放启动路径上跑一次比另起一个定时器省事得多。
try:
    from core import db as _db  # noqa: E402
    _db.init()
except Exception as _e:  # 库起不来不该让服务起不来 —— 台账坏了合成还能用
    obs.log("db_init_failed", level="error", error=str(_e))
obs.prune_logs()

# 版本号的唯一来源是 pyproject.toml。之前这个文件里硬编码了三处
# （FastAPI title、启动日志、发给中台的 User-Agent），发版时改一处漏两处，
# 于是日志里写着 0.3.0、接口文档写着 0.2.0，排查时根本不知道跑的是哪版。
# 先读 pyproject.toml 而不是 importlib.metadata：这是个用 editable install
# 装的本地工具，metadata 是**安装那一刻的快照**，改了 pyproject 也不会更新
# （实测改成 0.4.0 后 metadata 仍报 0.3.0）。源码文件才是跑着的那份代码的真源。
try:
    import tomllib  # noqa: E402
    VERSION = tomllib.loads(
        (_PROJECT_DIR / "pyproject.toml").read_text(encoding="utf-8")
    )["project"]["version"]
except Exception:
    try:
        from importlib.metadata import version as _pkg_version  # noqa: E402
        VERSION = _pkg_version("voxflow")
    except Exception:
        # 读不到就说 unknown —— 比写一个可能已经过期的常量诚实。
        VERSION = "unknown"

obs.log("server_start", version=VERSION)

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


def _audio_seconds_of(task: dict) -> float:
    """
    任务产出的音频有多长（秒）。量不出来就返回 0，调用方退回按「次」计。

    用 soundfile 读文件头而不是整段读进来：只要 frames/samplerate 两个数，
    没必要为了算个时长把几十 MB 的 wav 解码一遍。
    """
    res = (task.get("result") or {})
    names = res.get("files") or ([res["filename"]] if res.get("filename") else [])
    total = 0.0
    for n in names:
        try:
            import soundfile as sf  # noqa: PLC0415
            path = n if os.path.isabs(n) else str(OUT_DIR / n)
            info = sf.info(path)
            total += info.frames / info.samplerate
        except Exception:
            continue
    return round(total, 2)


def _notify_music_task(task_id: str):
    """音乐任务结束 → 推群卡片 + 写台账。

    挂在 worker 的 finally 里，和计量同一个收口：六种任务都从这过，
    挂一处覆盖全部。**只推音乐**（suno / suno_cover）——
    本地 TTS 一天几十次，全推进去等于把群和台账都刷废。

    整段包在 try 里：通知是旁路，**它挂了不能把生成搞挂**。
    """
    try:
        from core import notify
        from core.paths import ARTIST_FILE

        with _tasks_lock:
            task = dict(_tasks.get(task_id) or {})
        if task.get("type") not in ("suno", "suno_cover"):
            return
        params = task.get("params") or {}
        result = task.get("result") or {}
        failed = task.get("status") == "error"
        title = params.get("title") or task.get("label", "未命名")

        artist = ""
        try:
            artist = json.loads(ARTIST_FILE.read_text(encoding="utf-8")).get("stage_name", "")
        except (OSError, json.JSONDecodeError, AttributeError):
            pass

        files = result.get("files") or []
        clips = result.get("clips") or []
        warning = result.get("warning") or ""
        acc = notify.account()
        buttons = []
        if (doc := acc.get("doc_url")):
            buttons.append({"text": "使用说明", "url": doc})
        if (base_url := (acc.get("base") or {}).get("url")):
            buttons.append({"text": "打开台账", "url": base_url, "type": "primary"})

        # 任务失败 ≠ 歌没了。CLI 常在下载那步 403，歌已经在 Suno 上，
        # 甚至已经交到汽水审核。先问台账，再决定群里喊什么。
        from core import pipeline as _pipe
        release = _pipe.release_status_for_title(title)
        if failed and release:
            notify.notify(
                f"🎵 {title} · {release['label']}",
                {
                    "艺人": artist,
                    "状态": release["label"],
                    "说明": "生成任务报错，但台账显示歌已经在发版流程里，不是没生成。",
                    "任务报错": (task.get("error") or "")[:160],
                },
                level="done",
                buttons=buttons,
                event="music_done",
                dedupe_key=f"voxflow-{task_id}",
            )
            return
        if failed and warning:
            failed = False              # 已确认 Suno 上有歌，只是音频没取回

        head = ("❌ 音乐生成失败：" if failed
                else ("🎵 已生成，请下载音频：" if warning else "🎵 新音乐已生成："))
        notify.notify(
            head + title,
            {
                "艺人": artist,
                "类型": "翻唱" if task["type"] == "suno_cover" else "AI 音乐",
                "风格": params.get("tags", ""),
                "模型": params.get("model", ""),
                "文件": (str(len(files)) + " 个") if files
                        else (f"{len(clips)} 首在 Suno 上 · 音频需手动下载" if clips else ""),
                "源链接": ("\n" + "\n".join(
                    f"· [{c.get('title') or c['id'][:8]}](https://suno.com/song/{c['id']})"
                    for c in clips if c.get("id"))) if clips else "",
                "说明": warning,
                "失败原因": (task.get("error") or "")[:200] if failed else "",
            },
            level="error" if failed else ("warn" if warning else "done"),
            buttons=buttons,
            event="music_failed" if failed else "music_done",
            dedupe_key=f"voxflow-{task_id}",
        )
        if failed:
            return                      # 失败的不进台账，台账只记真作品

        # ── 一个文件 = 一条 R2 链接 = 一行台账 ──────────────────────
        #
        # Suno 一次出两首，**必须拆成两行**：它们会各自定名、各自上架、
        # 各自归属，塞进一行就再也分不开了。
        #
        # 对应关系靠**文件名**锚定，不靠额外的映射表：
        # 文件名自带时间戳（[Suno]标题_20260906_143012.mp3），
        # R2 的 key 就是 prefix + 文件名，所以链接可以从文件名重算出来 ——
        # 存一张映射表反而多一个会和现实脱节的地方。
        #
        # 上传失败不拦台账：先把行记下来（人能看到有这首歌），
        # 「音乐地址」空着，比整条丢掉强。
        from core import r2

        now_ms = int(time.time() * 1000)
        for f in files or [""]:
            url = r2.upload(f) if f else ""
            notify.ledger_add({
                "曲名": title,
                "状态": "未发行",
                "音乐地址": url,
                "艺人署名": artist,
                "风格标签": params.get("tags", ""),
                "生成模型": params.get("model", ""),
                "生成时间": now_ms,          # 飞书日期字段收毫秒时间戳
                # 文件名是这一行和那个文件之间唯一的锚。**别删这一栏。**
                # 只填机器知道的：发行歌名 / 资产归属 / 授权方式 / 负责账号
                # 都留空等人填 —— 机器猜个默认值填进去，人扫一眼觉得
                # 「已经有了」就不会去改，等到结算才发现归属全是错的。
                "备注": (os.path.basename(f) if f else "无音频文件")
                        + f" · task {task_id}"
                        + ("" if url or not f else " · R2 上传失败"),
            })
    except Exception as e:                # noqa: BLE001 —— 旁路，绝不影响主流程
        obs.log("notify_hook_failed", level="warn", task_id=task_id, error=str(e)[:200])


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

        # 计量埋在 worker 这一层，不埋在每个 _run_*_task 里：四种任务都从这里过，
        # 埋一处覆盖全部，将来加第五种任务也自动被计上。
        # 例外是 suno —— 它要记 credits，只有它自己知道扣了多少，所以由
        # _run_suno_task 自己记，这里跳过，免得记两遍。
        _t0 = time.perf_counter()
        _err = ""
        try:
            if task["type"] == "clone":
                _run_clone_task(task_id, task["params"], _update_task)
            elif task["type"] == "design":
                _run_design_task(task_id, task["params"], _update_task)
            elif task["type"] == "suno":
                _run_suno_task(task_id, task["params"], _update_task)
            elif task["type"] == "dialogue":
                _run_dialogue_task(task_id, task["params"], _update_task)
            elif task["type"] == "cover":
                _run_cover_task(task_id, task["params"], _update_task)
            elif task["type"] == "cover_upscale":
                _run_cover_upscale_task(task_id, task["params"], _update_task)
            elif task["type"] == "suno_cover":
                _run_suno_cover_task(task_id, task["params"], _update_task)
        except Exception as e:
            _err = str(e)
            _update_task(task_id, status="error", error=_err,
                         completed_at=datetime.now().strftime("%H:%M:%S"))
            obs.log("task_failed", level="error", task_type=task["type"],
                    task_id=task_id, label=task.get("label", ""), error=_err[:2000])   # 别再截到 300：真正的错因常在后半段
        finally:
            _notify_music_task(task_id)
            if task["type"] not in ("suno", "suno_cover", "cover", "cover_upscale"):
                # 本地 TTS 单价是 0，但**量**要记 —— 「本月本地合成了多少秒」
                # 乘上对标商业 API 的单价，就是本地方案实际省下的钱。
                # 不记量的话，这个工具最大的价值恰好是唯一看不见的那个。
                _audio_s = _audio_seconds_of(task)
                obs.meter("tts", task["type"], qty=_audio_s or 1, credits=0,
                          track_id="", duration_ms=int((time.perf_counter() - _t0) * 1000),
                          ok=not _err, unit="seconds" if _audio_s else "calls")


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
    # title 可空 —— 下方 save_script 里 `req.title.strip() or req.content[:20]`
    # 就是为「没填标题」兜底的，但模型里标 required 会让前端少传 title 时
    # 直接 422，兜底逻辑永远走不到。
    title: str = ""
    content: str


# ── FastAPI 应用 ──────────────────────────────────────────
app = FastAPI(title="VoxFlow 声流", version=VERSION)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def _observe(request, call_next):
    """
    每个 API 请求记一条耗时 + 失败时记一条错误日志。

    为什么按「方法 + 路由模板」而不是完整 URL 聚合：/api/audio/xxx.wav 每个文件
    一个 URL，按完整路径分组的话指标表会被几百个只出现一次的 key 撑爆，
    什么也看不出来。这里只取前三段做 key，够区分端点又不会爆。

    静态资源不记 —— 它们量大、恒定成功、耗时只反映磁盘，混进来会把
    真正的 API 分位数稀释掉。
    """
    path = request.url.path
    if not path.startswith("/api/"):
        return await call_next(request)
    key = f"{request.method} /" + "/".join(path.strip("/").split("/")[:3])
    t0 = time.perf_counter()
    status = 500
    try:
        resp = await call_next(request)
        status = resp.status_code
        return resp
    except Exception as e:
        obs.log("request_error", level="error", route=key, error=str(e)[:300],
                error_type=type(e).__name__)
        raise
    finally:
        ms = (time.perf_counter() - t0) * 1000
        obs.record_latency(key, ms, ok=status < 500)
        # 只有慢请求和失败请求写日志。全量写的话一天几万行，
        # 真正要找的那条反而被淹掉了 —— 量的信息已经在 metrics 里。
        if status >= 400 or ms > 3000:
            obs.log("request", level="warn" if status >= 400 else "info",
                    route=key, status=status, ms=round(ms, 1))

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
def index():
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
def get_status():
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


# ── 可观测性：健康 / 指标 / 日志 / 成本 ────────────────────
#
# 四个端点分工明确，别合并成一个大而全的 /api/debug：
#   health     现在能不能干活（给人和监控看的红绿灯）
#   metrics    快不快、错多少（性能回归）
#   logs       刚才为什么失败（排查）
#   economics  花了多少、回本没有（生意）
# 合成一个的话，想看一眼健康状态得等它把日志和聚合查询也跑完。

@app.get("/api/health")
def health():
    """
    深度健康检查。**不是** ping —— ping 只能证明进程还在，
    而这里真正会坏的是磁盘满了、库锁了、模型没下完。

    三档而不是布尔：degraded 是最有用的那一档（还能出歌但快没空间了），
    只有 ok/down 两档的话，degraded 会被算成 ok，等发现时已经是 down。
    """
    checks = {}

    # 库：真的读一次，不是看文件在不在
    try:
        from core import db
        with db.connect() as c:
            n = c.execute("SELECT COUNT(*) FROM tracks").fetchone()[0]
        checks["database"] = {"ok": True, "detail": f"{n} 首作品在库"}
    except Exception as e:
        checks["database"] = {"ok": False, "detail": f"{type(e).__name__}: {str(e)[:80]}"}

    # 数据目录可写：只读挂载 / 权限错乱时，症状是「合成成功但没有文件」，
    # 极难猜。这里直接写一个字节验证。
    try:
        probe = DATA_DIR / ".health_probe"
        probe.write_text("1")
        probe.unlink()
        checks["data_dir"] = {"ok": True, "detail": str(DATA_DIR)}
    except Exception as e:
        checks["data_dir"] = {"ok": False, "detail": f"不可写: {str(e)[:80]}"}

    # 磁盘：模型 8.4 GB、每首歌几十 MB，空间是这个工具最现实的死法
    try:
        du = shutil.disk_usage(DATA_DIR)
        free_gb = du.free / 1024**3
        checks["disk"] = {
            "ok": free_gb > 5, "warn": 5 <= free_gb < 20,
            "free_gb": round(free_gb, 1), "used_pct": round(du.used / du.total * 100),
            "detail": f"剩余 {free_gb:.1f} GB",
        }
    except Exception as e:
        checks["disk"] = {"ok": False, "detail": str(e)[:80]}

    # 模型：**没下 ≠ 坏了**。
    #
    # 这里之前把「模型没下」判成 ok=False，于是刚装好的用户打开就看到红色的
    # 「有项目坏了」—— 而那恰恰是全新安装的正常状态，第一印象直接变成
    # 「这东西是不是装坏了」。真正的 down 要留给「库读不出、目录不可写」
    # 这种确实坏了的情况。
    #
    # 所以分三种：都在 = ok；缺一部分 = warn（对应的功能不可用，别的照跑）；
    # 全没有 = 仍然 ok 但 warn，因为**不下模型也能用**：AI 音乐、发行台账、
    # 运营台都不碰本地模型。
    base_ok = _check_model_dir("Base")
    design_ok = _check_model_dir("VoiceDesign")
    downloading = _model_downloading("Base") or _model_downloading("VoiceDesign")
    checks["tts_models"] = {
        "ok": True,
        "warn": not (base_ok and design_ok),
        "base": base_ok, "design": design_ok, "downloading": downloading,
        "detail": ("Base + VoiceDesign 就绪" if base_ok and design_ok
                   else "Base 就绪，VoiceDesign 未下载（音色设计不可用）" if base_ok
                   else "模型下载中…" if downloading
                   else "本地模型未下载 —— 语音合成不可用，AI 音乐和发行台账照常"),
    }

    # 任务队列积压：worker 是单线程，堵住了前端只会一直转圈
    with _tasks_lock:
        queued = sum(1 for t in _tasks.values() if t["status"] == "queued")
        running = sum(1 for t in _tasks.values() if t["status"] == "running")
    checks["task_queue"] = {"ok": queued < 20, "warn": queued >= 5,
                            "queued": queued, "running": running,
                            "detail": f"排队 {queued} · 执行中 {running}"}

    failed = [k for k, v in checks.items() if not v.get("ok")]
    warned = [k for k, v in checks.items() if v.get("ok") and v.get("warn")]
    status = "down" if failed else ("degraded" if warned else "ok")
    if failed:
        obs.log("health_degraded", level="error", failed=failed)
    return {"status": status, "failed": failed, "warned": warned,
            "checks": checks, "uptime_s": obs.metrics()["uptime_s"]}


@app.get("/api/metrics")
def metrics_endpoint():
    """进程指标：各端点的量、错误率、P50/P95。性能回归的对照基线。"""
    m = obs.metrics()
    with _tasks_lock:
        by_status: dict[str, int] = {}
        for t in _tasks.values():
            by_status[t["status"]] = by_status.get(t["status"], 0) + 1
    m["tasks"] = by_status
    m["models_loaded"] = {"base": _base_engine is not None,
                          "design": _design_engine is not None}
    return m


@app.get("/api/logs")
def logs_endpoint(limit: int = 200, level: str = "", event: str = "", days: int = 3):
    """最近的结构化日志，倒序。前端「运行日志」面板的数据源。"""
    return {"logs": obs.read_logs(limit=min(limit, 1000), level=level,
                                  event=event, days=min(days, 14))}


@app.get("/api/economics")
def economics(days: int = 30):
    """
    单位经济学 —— 这门生意的账。

    为什么它值得一个端点：本地 TTS 免费、Suno 走订阅、出图烧中台积分，
    三条成本链路各记各的，**没有任何一个地方能回答「这首歌到底花了多少、
    发出去回本了吗」**。不合起来看，就只能凭感觉判断要不要继续做。

    回本播放数按各平台公开分成率算；分成率没证实的平台（腾讯系）返回 0
    表示算不了 —— 见 configs/pricing.json 里为什么不填猜的数。
    """
    summary = obs.usage_summary(days)
    costs = obs.track_costs()

    titles: dict[str, str] = {}
    stages: dict[str, str] = {}
    release_plat: dict[str, str] = {}
    release_title: dict[str, str] = {}
    listings_by: dict[str, list] = {}
    try:
        from core import db
        db.init()
        with db.connect() as c:
            for r in c.execute(
                "SELECT id, title, stage, "
                "IFNULL(release_platform,'') rp, IFNULL(release_title,'') rt "
                "FROM tracks"
            ):
                titles[r["id"]] = r["title"]
                stages[r["id"]] = r["stage"]
                if r["rp"]:
                    release_plat[r["id"]] = r["rp"]
                if r["rt"]:
                    release_title[r["id"]] = r["rt"]
            for r in c.execute(
                "SELECT track_id, platform, status, "
                "IFNULL(platform_title,'') title FROM track_platforms"
            ):
                listings_by.setdefault(r["track_id"], []).append({
                    "platform": r["platform"],
                    "status": r["status"],
                    "title": r["title"],
                })
    except Exception as e:
        # 查不到不能把整本账弄没，但必须留下痕迹 —— 运营台缺发布平台
        # 就是这样被静默 except 吃掉、看起来像「从来没有这个字段」。
        obs.log("economics_track_lookup_failed", level="error", error=str(e)[:300])

    # 收入侧。回本播放数优先用**实测**千播单价（后台的累计收益 ÷ 累计播放），
    # 它比公开资料的区间中位数准 —— 实测已经包含了这个账号的实际权益档位。
    revenue = obs.platform_revenue()
    rates = {k: (v["cny_per_1k_plays"] if v["rate_source"] == "measured" else None)
             for k, v in revenue.items()}

    # 单曲实际收入（音乐人后台抓的，可能为空 —— 为空就如实说没有，不摊派）
    track_rev = obs.track_revenue()

    # 有成本或有收入的作品都要出现：只赚不花（历史作品）和只花不赚（还没发）
    # 都是这门生意里真实存在的状态，漏掉哪一边看到的都是残缺的账。
    all_ids = set(costs) | set(track_rev) | set(listings_by)
    tracks = []
    for tid in all_ids:
        c = costs.get(tid) or {"total_cny": 0.0, "by_provider": {}}
        rev = track_rev.get(tid) or {}
        cost = round(c["total_cny"], 2)
        earned = round(rev.get("earned_cny", 0.0), 2)
        plats = listings_by.get(tid) or []
        exclusive = release_plat.get(tid) or (plats[0]["platform"] if plats else "")
        tracks.append({
            "track_id": tid,
            "title": titles.get(tid, tid),
            "stage": stages.get(tid, ""),
            "release_title": release_title.get(tid, ""),
            "release_platform": exclusive,
            "platforms": plats,
            "cost_cny": cost,
            "by_provider": c["by_provider"],
            # 有后台数据才给，没有就是 None —— 前端据此显示「暂无数据」
            # 而不是显示一个 0（0 会被读成「一分没赚」，那是另一回事）。
            "earned_cny": earned if rev else None,
            "plays": rev.get("plays") if rev else None,
            "roi": (round(earned / cost, 2) if rev and cost > 0 else None),
            "net_cny": (round(earned - cost, 2) if rev else None),
            "breakeven_plays": {
                p: obs.breakeven_plays(cost, p, rate_override=rates.get(p))
                for p in ("qishui", "netease", "tencent")
            },
        })
    # 有真实收入的排前面（那是最该看的），其次按成本从高到低
    tracks.sort(key=lambda x: (x["earned_cny"] is None, -(x["earned_cny"] or 0), -x["cost_cny"]))

    priced = [t for t in tracks if t["cost_cny"] > 0]
    avg = round(sum(t["cost_cny"] for t in priced) / len(priced), 2) if priced else 0.0

    # 盈亏。**收入是累计的、成本只统计最近 N 天** —— 两个口径不同，
    # 不能直接相减当成「这个月赚了多少」，所以字段名写清楚是 lifetime，
    # 并且把两个口径一起返回，让界面能如实标注而不是含糊地放一个「净利润」。
    earned = round(sum(v["earned_cny"] for v in revenue.values()), 2)
    plays = sum(v["plays"] for v in revenue.values())
    lifetime_cost = round(sum(t["cost_cny"] for t in tracks), 2)
    return {
        "summary": summary,
        "revenue": revenue,
        "pnl": {
            "lifetime_earned_cny": earned,
            "lifetime_cost_cny": lifetime_cost,
            "net_cny": round(earned - lifetime_cost, 2),
            "total_plays": plays,
            # 单位经济学的那个数：每一次播放实际带来多少钱。
            "cny_per_1k_plays_measured": round(earned / plays * 1000, 4) if plays else 0.0,
        },
        "avg_cost_per_track_cny": avg,
        "avg_breakeven_plays": obs.breakeven_plays(
            avg, "netease", rate_override=rates.get("netease")),
        "tracks": tracks[:100],
        "pricing": obs.pricing(),
        # 计过量的作品数 vs 台账总数 —— 差额就是「历史作品没有成本数据」，
        # 直接说出来，免得看到 0 元以为是免费做出来的。
        "covered": len(costs), "total_tracks": len(titles),
        # 有多少首拿到了单曲维度的收入数据。0 表示还没跑过
        # scripts/ncm_track_stats.py（要登录音乐人后台）。
        "revenue_covered": len(track_rev),
    }


# ── 模型下载 ─────────────────────────────────────────────
#
# 为什么要在界面里做：新用户装好之后打开的第一屏是「声音克隆」，而模型没下 ——
# 空音色库、灰按钮、一条「请回终端运行 ./install.sh」。整屏都是死路，
# 而这时候 Suno、发行台账、运营台其实全都能用，只是他看不到。
#
# 进度读取（_model_download_progress）早就写好了，一直缺的只是**触发的入口**。
# 补上之后，下载这 7 GB 的等待期里人可以去用别的功能，而不是盯着终端。

_download_procs: dict[str, object] = {}
_MODEL_REPOS = {
    "Base": "Qwen/Qwen3-TTS-12Hz-1.7B-Base",
    "VoiceDesign": "Qwen/Qwen3-TTS-12Hz-1.7B-VoiceDesign",
}


@app.post("/api/models/download")
def start_model_download(model: str = Form(...)):
    """
    起一个后台子进程下模型。幂等：已经在下或已经下完的直接返回现状，
    不会重复起进程 —— 连点两下按钮就下两份 7 GB 是很容易发生的。
    """
    if model not in _MODEL_REPOS:
        raise HTTPException(400, f"未知模型 {model}，只能是 Base 或 VoiceDesign")
    if _check_model_dir(model):
        return {"ok": True, "status": "already_done", "detail": f"{model} 已就绪"}

    proc = _download_procs.get(model)
    if proc is not None and getattr(proc, "poll", lambda: 0)() is None:
        return {"ok": True, "status": "downloading", "detail": f"{model} 正在下载"}

    target = MODELS_DIR / f"{model}-1.7B"
    target.mkdir(parents=True, exist_ok=True)
    import subprocess                                             # noqa: PLC0415
    # 用当前解释器跑 modelscope，不依赖 PATH 里有没有它 —— 服务是用
    # .venv/bin/python 起的，那个环境里一定装了（install.sh 装的）。
    cmd = [sys.executable, "-m", "modelscope.cli.cli", "download",
           "--model", _MODEL_REPOS[model], "--local_dir", str(target)]
    log_path = obs.LOG_DIR / f"download-{model}.log"
    obs.LOG_DIR.mkdir(parents=True, exist_ok=True)
    try:
        # 输出重定向到文件而不是管道：管道没人读满了就会把子进程卡死，
        # 而下载要跑十几分钟，没人会一直读。
        logf = log_path.open("ab")
        _download_procs[model] = subprocess.Popen(
            cmd, stdout=logf, stderr=subprocess.STDOUT, cwd=str(PROJECT_DIR))
    except Exception as e:
        obs.log("model_download_failed", level="error", model=model, error=str(e)[:200])
        raise HTTPException(500, f"起下载进程失败：{type(e).__name__} {e}")

    obs.log("model_download_started", model=model, repo=_MODEL_REPOS[model],
            target=str(target))
    return {"ok": True, "status": "downloading",
            "detail": f"{model} 开始下载（约 3.4 GB），可以先去用别的功能",
            "log": str(log_path)}


@app.get("/api/models/download")
def model_download_status():
    """
    两个模型的下载进度 + 「现在能做什么」。

    第二部分才是新用户真正需要的：只说「模型没下」是在说他不能做什么，
    而这时候 AI 音乐、发行台账、运营台全都不碰本地模型，照常可用。
    """
    out = {}
    for name in _MODEL_REPOS:
        prog = _model_download_progress(name)
        proc = _download_procs.get(name)
        alive = proc is not None and getattr(proc, "poll", lambda: 0)() is None
        out[name] = {**prog, "ready": _check_model_dir(name), "running": alive}

    base_ready = out["Base"]["ready"]
    caps_now = ["AI 音乐（Suno）", "作品看板与全网发行台账", "运营台（成本 / 健康 / 日志）"]
    caps_after = ["声音克隆", "多角色剧本合成"] + (
        [] if out["VoiceDesign"]["ready"] else ["音色设计（需 VoiceDesign）"])
    return {
        "models": out,
        "can_do_now": caps_now if not base_ready else caps_now + caps_after,
        "needs_base": [] if base_ready else caps_after,
    }


@app.get("/api/persona-audio")
def get_persona_audio(key: str):
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
def list_personas():
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


class DesignCommitRequest(BaseModel):
    filename: str                 # 设计任务产出的 [设计]xxx.wav
    voice_name: str
    instruction: str = ""


@app.post("/api/design/commit")
def design_commit(req: DesignCommitRequest):
    """把**已经生成好的**设计音色存进音色库。

    ## 为什么需要这个端点

    设计任务原本只有一条入库路径：提交时把 `commit` 开关打开。
    可那个开关上写的是「满意后存入」—— 而它必须在**生成之前**拨，
    人根本没法先听再决定。于是要么盲开、要么听完发现不错却存不了，
    只能改改参数重生成一遍碰运气。

    实测后果：15 个设计产物，音色库里只有 2 个。

    这个端点让「满意后存入」名副其实：生成完、听过、觉得行，再点一下。
    """
    from core.utils import (  # noqa: PLC0415
        resolve_design_voice_key, sanitize_path_component,
        upsert_persona_mapping, write_generation_json,
    )

    name = (req.voice_name or "").strip()
    if not name:
        raise HTTPException(400, "voice_name 不能为空")
    src = OUT_DIR / os.path.basename(req.filename)
    if not src.is_file():
        raise HTTPException(404, f"找不到音频：{req.filename}")

    voice_key = resolve_design_voice_key({"voice_name": name})
    safe_name = sanitize_path_component(name, fallback="未命名音色")
    seed = _get_processor().extract_voice_seed(str(src), name, max_sec=10, skip_start_ms=0)
    upsert_persona_mapping(
        str(BASE_DIR),
        persona_key=voice_key,
        persona_name=name,
        ref_rel=os.path.relpath(str(seed), str(BASE_DIR)).replace("\\", "/"),
        design_rel=f"voice_designs/{safe_name}.json",
        instruction=req.instruction or "",
    )
    write_generation_json(str(BASE_DIR), voice_key, source="voice_design")
    obs.log("design_committed", persona_key=voice_key, name=name)
    return {"ok": True, "persona_key": voice_key, "name": name}


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
def update_persona(key: str, name: str = Form(None), desc: str = Form(None)):
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
def delete_persona(key: str):
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
def clone(req: CloneRequest):
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
def design(req: DesignRequest):
    """提交音色设计任务（异步）"""
    if not (req.tone or req.emotion):
        raise HTTPException(400, "必须提供 tone 或 emotion（至少一个）")
    if req.text and len(req.text) > 45:
        raise HTTPException(400, f"设计文本过长（{len(req.text)} > 45 字）")

    label = f"{req.voice_name} — {req.tone or req.emotion}"
    task_id = _submit_task("design", label, req.model_dump())
    return {"task_id": task_id, "status": "queued"}


@app.get("/api/tasks")
def list_tasks():
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
def cancel_task(task_id: str):
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
def list_scripts():
    """列出所有保存的文案"""
    if not SCRIPTS_FILE.exists():
        return {"scripts": []}
    try:
        with open(SCRIPTS_FILE, "r", encoding="utf-8") as f:
            return {"scripts": json.load(f)}
    except Exception:
        return {"scripts": []}


@app.post("/api/scripts")
def save_script(req: ScriptSaveRequest):
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
def delete_script(script_id: str):
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
def audio_list():
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
def get_audio(filename: str):
    """获取音频文件"""
    # 防止路径穿越
    safe = os.path.basename(filename)
    path = OUT_DIR / safe
    if not path.exists():
        raise HTTPException(404, f"音频文件不存在: {safe}")
    media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(str(path), media_type=media_type, filename=safe)


@app.delete("/api/audio/{filename}")
def delete_audio(filename: str):
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
def llm_status():
    """检测 LLM 后端是否可用"""
    from core.llm_client import check_status
    return check_status()


# ── 作品流水线（可观测：每首歌走到哪一步）──────────────────

@app.get("/api/inbox")
def inbox_scan():
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
def inbox_import(req: dict):
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
def pipeline_list():
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
def publish_board():
    """发布账号、已发布曲目与云备份状态的同源看板数据。"""
    from core import pipeline
    return pipeline.publication_board()


@app.get("/api/artist")
def get_artist():
    """获取艺人档案与平台绑定信息"""
    from core.paths import ARTIST_FILE
    import json
    if not ARTIST_FILE.exists():
        return {
            "real_name": "",
            "stage_name": "",
            "roles": {},
            "platform_profiles": [],
            "defaults": {}
        }
    try:
        return json.loads(ARTIST_FILE.read_text(encoding="utf-8"))
    except Exception as e:
        raise HTTPException(500, f"读取艺人档案失败: {str(e)}")


class ArtistUpdateRequest(BaseModel):
    real_name: str | None = None
    stage_name: str | None = None
    roles: dict | None = None
    platform_profiles: list | None = None
    defaults: dict | None = None


@app.post("/api/artist")
def update_artist(req: ArtistUpdateRequest):
    """更新艺人档案"""
    from core.paths import CONFIG_DIR, ARTIST_FILE
    import json
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    
    current_data = {}
    if ARTIST_FILE.exists():
        try:
            current_data = json.loads(ARTIST_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass

    # 局部更新
    if req.real_name is not None:
        current_data["real_name"] = req.real_name
    if req.stage_name is not None:
        current_data["stage_name"] = req.stage_name
    if req.roles is not None:
        current_data["roles"] = req.roles
    if req.platform_profiles is not None:
        current_data["platform_profiles"] = req.platform_profiles
    if req.defaults is not None:
        current_data["defaults"] = req.defaults

    try:
        ARTIST_FILE.write_text(json.dumps(current_data, ensure_ascii=False, indent=2), encoding="utf-8")
        return {"ok": True, "artist": current_data}
    except Exception as e:
        raise HTTPException(500, f"保存艺人档案失败: {str(e)}")


class PipelineStageRequest(BaseModel):
    track_id: str
    stage: str


@app.get("/api/notify/owner")
def notify_owner():
    """「我是谁」—— 用于看板的「只看我负责的」。

    读通知配置里的 assignees.owner：那份配置本来就是分配责任人用的真源，
    不另存一份「当前用户」，省得两处不同步。没配就返回空，前端的筛选
    自然筛不出东西 —— 比编一个默认用户强。
    """
    from core import notify  # noqa: PLC0415

    owner = ((notify.account() or {}).get("assignees") or {}).get("owner") or {}
    return {"name": owner.get("name", ""), "open_id": owner.get("open_id", "")}


@app.get("/api/pipeline/readiness")
def pipeline_readiness(track_id: str, platform: str):
    """这首歌发这个平台，备料齐了没有 —— 缺哪几项、每项怎么补。

    「备料中」原本是个空状态：点了确认发版就写上它，然后什么都不发生，
    也没有任何东西告诉你算不算完、下一步点哪儿。这个端点就是那一环。
    """
    from core import pipeline  # noqa: PLC0415 —— 与本文件其余 pipeline 端点一致，延迟导入

    if not track_id or not platform:
        raise HTTPException(400, "缺少 track_id 或 platform")
    r = pipeline.readiness(track_id, platform)
    if r.get("错误"):
        raise HTTPException(404, r["错误"])
    return r


@app.post("/api/pipeline/import")
async def pipeline_import(
    audio: UploadFile = File(...),
    title: str = Form(""),
    album: str = Form(""),
    cover: UploadFile = File(None),
):
    """导入一个外部音频，直接进发行流程。

    ## 这是「发布助手」模式的入口

    voxflow 有两类用户，需求完全不重叠：

    - **做歌的**：本地 TTS + Suno 生成 → 发行。要下 7GB 模型、要 Suno 会员。
    - **发歌的**：拿到别人做好的音频 → 上架、跟进度、看收益。
      **不需要模型、不需要 Suno**，甚至不需要懂 AI。

    此前曲目只能从生成流程进库，第二类人 clone 下来面对的是一个空看板 ——
    明明发歌记录、全网发行、运营台这几屏都不依赖模型，却没东西可放。

    这个端点就是那个口子：传一个音频进来就是一首待发的歌。

    ## 为什么直接落到 selected 阶段

    外部音频意味着「歌已经定了」—— draft/generated/selected 这三个阶段
    是给「还在挑哪一版」用的，导入的人没有这个问题，让他从头点三下没意义。
    """
    from core import db, pipeline, r2  # noqa: PLC0415
    from core.utils import sanitize_path_component  # noqa: PLC0415

    ext = os.path.splitext(audio.filename or "")[1].lower()
    if ext not in AUDIO_EXTS:
        raise HTTPException(400, f"不支持的音频格式 {ext or '(无扩展名)'}，支持 {', '.join(sorted(AUDIO_EXTS))}")

    name = (title or os.path.splitext(audio.filename or "")[0] or "未命名").strip()
    safe = sanitize_path_component(name, fallback="未命名")
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    music_dir = OUT_DIR / MUSIC_SUBDIR
    music_dir.mkdir(parents=True, exist_ok=True)
    dest = music_dir / f"[导入]{safe}_{ts}{ext}"
    dest.write_bytes(await audio.read())

    cover_path = ""
    if cover is not None and cover.filename:
        cext = os.path.splitext(cover.filename)[1].lower() or ".jpg"
        cdest = OUT_DIR / "covers" / f"{safe}_{ts}{cext}"
        cdest.parent.mkdir(parents=True, exist_ok=True)
        cdest.write_bytes(await cover.read())
        cover_path = str(cdest)

    track_id = uuid.uuid4().hex[:12]
    db.init()
    rel = os.path.relpath(str(dest), str(BASE_DIR)).replace("\\", "/")
    pipeline.upsert(track_id, title=name, stage="selected", audio_file=rel,
                    cover_file=cover_path, album_desc=album,
                    note=f"外部导入 {audio.filename}")

    # 传 R2 拿公网直链 —— 导入的人多半就是要把它发给别人/上传平台，
    # 本地路径对那两件事都没用。没配 R2 就跳过，不拦流程。
    url = r2.upload(str(dest)) if r2.enabled() else ""
    obs.log("track_imported", track_id=track_id, title=name[:40], r2=bool(url))
    return {"ok": True, "track_id": track_id, "title": name,
            "audio_url": f"/api/audio/{MUSIC_SUBDIR}/{dest.name}", "r2_url": url}


@app.post("/api/pipeline/stage")
def pipeline_set_stage(req: PipelineStageRequest):
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
def pipeline_upsert(req: PipelineTrackRequest):
    """登记或更新一首作品。"""
    from core import pipeline
    return {"ok": True, "track": pipeline.upsert(
        req.track_id, title=req.title, voice=req.voice,
        clip_id=req.clip_id, note=req.note,
    )}


class PipelineReleaseRequest(BaseModel):
    track_id: str
    platform: str
    release_title: str


@app.post("/api/pipeline/release")
def pipeline_release(req: PipelineReleaseRequest):
    """确认发版：独家授权只能投一个平台，发行歌名必须唯一。"""
    from core import pipeline
    try:
        track = pipeline.submit_release(req.track_id, req.platform, req.release_title)
        pipeline.set_stage(req.track_id, "publishing")
        return {"ok": True, "track": pipeline.get_track(req.track_id) or track}
    except ValueError as e:
        raise HTTPException(400, str(e))


class PipelinePlatformRequest(BaseModel):
    track_id: str
    platform: str
    status: str
    url: str | None = None
    note: str | None = None


@app.post("/api/pipeline/platform")
def pipeline_platform(req: PipelinePlatformRequest):
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


class PipelineLinkRequest(BaseModel):
    listing_id: int
    track_id: str


@app.post("/api/pipeline/link")
def pipeline_link(req: PipelineLinkRequest):
    """把一条平台上架记录挂到某首 Suno/本地原曲上。改名、拆分都走这里。"""
    from core import pipeline
    try:
        return {"ok": True, "track": pipeline.link_listing(req.listing_id, req.track_id)}
    except ValueError as e:
        raise HTTPException(400, str(e))


@app.get("/api/pipeline/sources")
def pipeline_sources():
    """能当原曲被关联的作品（有 Suno clip 或本地音频）。"""
    from core import pipeline
    return {"tracks": pipeline.source_candidates()}


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
            # 顶栏要显示「用的什么模型」，不能只说「本地模型」——
            # 四个绿灯长得一样，人根本分不出哪个是哪个。
            return {
                "ready": ok,
                "model": "Qwen3-TTS 1.7B" if ok else "",
                "detail": "Qwen3-TTS 1.7B（Base + VoiceDesign，本地推理）" if ok
                          else "模型未下载，跑 ./install.sh",
            }
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
                    "plan": plan, "model": "Suno v5.5",
                    "detail": f"Suno v5.5 · {plan} · 剩 {left} 积分"}
        except Exception:
            return {"ready": False, "credits": 0, "detail": "未登录或 CLI 不可用"}

    def _probe_museav():
        from core import cover as _cover                       # noqa: PLC0415
        if not _cover.available():
            return {"ready": False, "identity": "",
                    "detail": "museav CLI 未登录（museav login）"}
        try:
            bal = _cover.balance()
            credits = bal.get("credits", 0)
            unmetered = bal.get("unmetered", False)
            who = bal.get("identity") or "museav"
            return {"ready": True, "identity": who, "model": who,
                    "credits": credits, "unmetered": unmetered,
                    "credits_total": None,
                    "detail": (f"museav CLI · {who} · 自家租户，不限额"
                               if unmetered else
                               f"museav CLI · {who} · 剩 {credits} 积分"
                               f"（够出 {credits // _cover.CREDITS_PER_COVER} 张封面）"
                               if credits else
                               f"museav CLI · {who} · 余额闸门拦住，出图会被拒")}
        except Exception as e:
            kind = type(e).__name__
            msg = str(e)[:80]
            return {"ready": False, "identity": "",
                    "detail": f"museav CLI 失败：{kind} {msg}"}

    def _probe_llm():
        try:
            from core.llm_client import check_status
            st = check_status()      # 内部有 60 秒缓存，不会每次都真打一次
            return {"ready": bool(st.get("available")), "model": st.get("model", ""),
                    "detail": st.get("error") or st.get("model", "")}
        except Exception as e:
            return {"ready": False, "model": "", "detail": str(e)[:60]}

    names = ["tts", "suno", "museav", "llm"]
    probes = [_probe_tts, _probe_suno, _probe_museav, _probe_llm]
    results = await asyncio.gather(*[asyncio.to_thread(f) for f in probes],
                                   return_exceptions=True)
    # key 用 museav 而不是泛称 studio —— 这是「museav 中台」这个具体的服务，
    # 换个中台就是换个 key，不该用一个模糊的通用名把它盖住。
    caps = {}
    for name, res in zip(names, results):
        caps[name] = res if isinstance(res, dict) else {"ready": False, "detail": "探测失败"}
    return caps


@app.post("/api/llm/generate")
def llm_generate(req: LLMGenerateRequest):
    """AI 文案生成"""
    from core.llm_client import generate_script
    try:
        result = generate_script(req.prompt, req.word_count)
        return {"ok": True, "text": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/llm/polish")
def llm_polish(req: LLMPolishRequest):
    """AI 文案润色"""
    from core.llm_client import polish_script
    try:
        result = polish_script(req.text, req.style)
        return {"ok": True, "text": result}
    except Exception as e:
        return {"ok": False, "error": str(e)}


@app.post("/api/llm/lyrics")
def llm_lyrics(req: LLMLyricsRequest):
    """生成可直接提交给 Suno 的结构化歌词。"""
    if not req.prompt.strip():
        raise HTTPException(400, "请填写歌词主题，或先填写歌曲标题和风格标签")
    from core.llm_client import generate_lyrics
    try:
        return {"ok": True, "text": generate_lyrics(req.prompt, req.style)}
    except Exception as e:
        return {"ok": False, "error": str(e)}


# ── 热点风格追踪（测试1：哪个音乐火做哪个风格，但不抄袭）──
# 网易云热歌榜（API 真数据）→ LLM 提炼风格共性 → Suno 风格标签。
# 反抄袭边界在 core/llm_client._TREND_SYSTEM 里写死：只谈流派/编曲/情绪
# 共性，禁止复述任何单首歌的旋律/歌词/编曲。
_trend_cache: dict = {"at": 0.0, "data": None}
_TREND_TTL = 30 * 60   # 榜单和风格分析缓存 30 分钟，别每次点都打榜+调 LLM


@app.get("/api/trending")
def trending():
    now = time.time()
    if _trend_cache["data"] and now - _trend_cache["at"] < _TREND_TTL:
        return _trend_cache["data"]
    try:
        from scripts.trending import get_hot_songs          # noqa: PLC0415
        from core.llm_client import analyze_trending        # noqa: PLC0415
        songs = get_hot_songs()
        if not songs:
            return {"ok": False, "error": "拿不到热歌榜"}
        result = analyze_trending(songs)
        data = {"ok": True, "updated": time.strftime("%Y-%m-%d %H:%M"),
                "songs": songs[:5], "trend": result}
        # LLM 翻车时（空标签）不缓存 —— 下次点会重试，别把坏结果锁 30 分钟
        if result.get("tags"):
            _trend_cache.update(at=now, data=data)
        return data
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


def _clear_stale_solver(port: int = 9233) -> None:
    """清掉 suno 遗留的验证码 Chrome。

    Suno 生成时会拉一个 headless Chrome 去解 hCaptcha，正常退出时自己清理。
    但**上一次失败/超时就会留下孤儿**，它一直占着 9233 端口，
    于是**之后每一次生成都失败** —— 而报错文案说的是
    「Chrome not found，或设置 SUNO_CHROME_PATH」，把人往完全错误的方向带
    （实测 Chrome 一直找得到，`suno doctor` 也一直是 pass）。

    2026-09-06 三首 BGM 就这么全挂了：任务失败、队列清空、额度一分没扣，
    界面上只看到「没反应」。真凶要跑 `suno doctor` 才看得见：
    `solver_chrome: warn — something is still listening on solver port 9233`。

    只杀**它自己那个 profile** 的进程 —— 用户日常的 Chrome、
    ego-browser 的 Chrome 都是别的 user-data-dir，绝不能误伤。
    """
    try:
        r = subprocess.run(["lsof", "-nP", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
                           capture_output=True, text=True, timeout=5)
        for pid in [x for x in r.stdout.split() if x.isdigit()]:
            cmd = subprocess.run(["ps", "-o", "command=", "-p", pid],
                                 capture_output=True, text=True, timeout=5).stdout
            # 认 suno 自己的 profile 路径，认不出来就不动
            if "suno-cli" in cmd and "--headless" in cmd:
                os.kill(int(pid), 15)
                obs.log("suno_stale_solver_killed", level="warn", pid=pid, port=port)
    except Exception:      # noqa: BLE001 —— 清理失败不该拦住生成
        pass


def _suno_env() -> dict[str, str]:
    """调 suno CLI 时的环境。

    ## 为什么要显式传 Chrome 路径

    Suno 的验证码环节要拉起一个 Chrome。CLI 自己会去几个常见位置找，
    **在交互 shell 里找得到**（`suno doctor` 显示 chrome: pass），
    但 web 服务是后台进程、环境不一样，同一台机器上就找不到了，
    报 `Configuration error: Chrome ... or set SUNO_CHROME_PATH`。

    2026-09-06 三首 BGM 就这么全军覆没：任务失败、队列清空、
    额度一分没扣，而人在界面上只看到「没反应」。

    与其猜两个环境差在哪，不如显式钉死路径 —— 找得到就传，
    找不到也不拦（让 CLI 自己去找，它可能有别的办法）。
    """
    _clear_stale_solver()
    env = dict(os.environ)
    if env.get("SUNO_CHROME_PATH"):
        return env
    for cand in (
        "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
        "/Applications/Chromium.app/Contents/MacOS/Chromium",
        "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
    ):
        if os.path.exists(cand):
            env["SUNO_CHROME_PATH"] = cand
            break
    return env
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
def suno_status():
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
def suno_generate(req: SunoGenerateRequest):
    """提交 Suno 音乐生成任务（异步，走现有任务队列）"""
    task_id = _submit_task("suno", f"🎵 {req.title or 'Suno 音乐'}", req.model_dump())
    return {"task_id": task_id, "status": "queued"}


class SunoBatchItem(BaseModel):
    title: str = "Untitled"
    tags: str = ""
    lyrics: str = ""
    persona: Optional[str] = None
    model: str = "v5.5"


class SunoBatchRequest(BaseModel):
    items: list[SunoBatchItem]
    wait: bool = False           # 是否等全部完成再返回
    poll_interval_sec: float = 5
    timeout_sec: int = 600       # 单首最久等 10 分钟


@app.post("/api/suno/batch")
async def suno_batch(req: SunoBatchRequest):
    """
    批量提交 Suno 生成任务。

    前端批量面板、自动化脚本（scripts/batch_bgm.py）都调这个。
    每个 item 走现有 _submit_task，跟单首的 /api/suno/generate 同一条任务队列，
    不需要 suno CLI 直接调用。

    wait=True 时同步等到全部完成才返回（最久的那个完成才返回），
    适合脚本"一行命令跑完"的场景；wait=False 时立刻返回 task_ids，
    调用方自己轮询 /api/tasks。
    """
    import asyncio

    if not req.items:
        raise HTTPException(400, "items 不能为空")

    if len(req.items) > 20:
        # 一次最多 20 —— 避免单次请求堆太多任务把队列塞爆
        raise HTTPException(400, f"一次最多 20 首，实际 {len(req.items)}")

    # 顺序提交，避免瞬时 burst 触发 Suno 速率限制
    task_ids = []
    for i, item in enumerate(req.items):
        # 自动追加 instrumental（如果是空的 lyrics 字段，UI 标记为 BGM）
        item_dict = item.model_dump()
        if not item_dict.get("lyrics"):
            tags = item_dict.get("tags", "")
            if "instrumental" not in tags.lower():
                item_dict["tags"] = (tags.rstrip(", ") + ", instrumental").strip(", ")
        task_id = _submit_task("suno", f"🎵 {item.title or 'Suno 音乐'}", item_dict)
        task_ids.append({"title": item.title, "task_id": task_id})
        # 提交之间间隔 2 秒（前端面板是 3 秒，脚本是 2 秒避免太慢）
        if i < len(req.items) - 1:
            await asyncio.sleep(2)

    if not req.wait:
        return {"task_ids": task_ids, "queued": len(task_ids)}

    # 同步等：轮询所有 task_id 直到全部 done / error / 超时
    import time
    start = time.time()
    while time.time() - start < req.timeout_sec:
        await asyncio.sleep(req.poll_interval_sec)
        all_done = True
        statuses = []
        for entry in task_ids:
            t = _tasks.get(entry["task_id"])
            if not t:
                statuses.append({"title": entry["title"], "status": "unknown"})
                continue
            statuses.append({"title": entry["title"], "status": t.get("status", "running")})
            if t.get("status") in ("queued", "running"):
                all_done = False
        if all_done:
            break

    # 最终状态
    results = []
    for entry in task_ids:
        t = _tasks.get(entry["task_id"], {})
        results.append({
            "title": entry["title"],
            "task_id": entry["task_id"],
            "status": t.get("status", "unknown"),
            "files": (t.get("result") or {}).get("files", []) if isinstance(t.get("result"), dict) else [],
        })
    return {"results": results, "elapsed_sec": round(time.time() - start, 1)}


# 网易云歌词开头那一坨制作人员名单（作词/作曲/编曲/混音/统筹/推广…）。
# 它们和歌词混在同一个字段里，直接喂给 Suno 会被**当歌词唱出来**。
#
# 判据看**结构不看词表**：枚举职能词是走不通的 —— 试过一版列了二十个词，
# 仍然漏掉「音频统筹」（开头不是「统筹」）和「发行营销顾问」（压根没列）。
# 这类名单的真正特征是格式：`短词 + 空格 + 冒号 + 空格 + 人名`。
# 歌词极少这么写，而网易云的 credits 一律是这个形状。
#
# 只剥**开头连续**的那一段，遇到第一行不像名单的就停 —— 正文里的对白
# （「他说 : 走吧」）不会被误伤。
_CREDIT_LINE = re.compile(r"^\s*[^\s:：]{1,12}\s+[:：]\s+\S")


def _strip_credits(text: str) -> str:
    lines = text.splitlines()
    i = 0
    while i < len(lines) and (not lines[i].strip() or _CREDIT_LINE.match(lines[i])):
        i += 1
    # 全被剥光说明判据太凶（整首歌都是这个格式？），那就原样退回去 ——
    # 宁可多几行名单，也不能把歌词吃掉。
    rest = "\n".join(lines[i:]).strip()
    return rest if rest else text.strip()


@app.get("/api/lyrics/search")
def lyrics_search(q: str, limit: int = 8):
    """
    按歌名搜网易云的歌，给翻唱取词用。

    走公开接口（和 scripts/sync_lyrics.py 同一套，带 Referer 否则被当盗链拒掉），
    **只读、不花任何额度**。

    只返回歌名/歌手/id —— 歌词单独一个端点取，因为搜索结果里大多数条目
    用户看一眼就排除了，没必要为每条都去拉一次歌词。
    """
    import urllib.parse, urllib.request  # noqa: PLC0415
    kw = (q or "").strip()
    if not kw:
        raise HTTPException(400, "搜什么？关键词是空的")
    url = ("https://music.163.com/api/search/get?s="
           + urllib.parse.quote(kw) + f"&type=1&limit={min(limit, 20)}")
    try:
        rq = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"})
        with urllib.request.urlopen(rq, timeout=20) as r:
            d = json.loads(r.read().decode())
    except Exception as e:
        obs.log("lyrics_search_failed", level="warn", q=kw[:40], error=str(e)[:120])
        raise HTTPException(502, f"搜索失败：{type(e).__name__} {str(e)[:60]}")

    songs = ((d.get("result") or {}).get("songs") or [])
    return {"songs": [{
        "id": str(x.get("id", "")),
        "name": x.get("name", ""),
        "artists": "/".join(a.get("name", "") for a in (x.get("artists") or [])),
        "album": (x.get("album") or {}).get("name", ""),
        "duration_ms": x.get("duration", 0),
    } for x in songs]}


@app.get("/api/lyrics/{song_id}")
def lyrics_get(song_id: str):
    """
    取一首歌的歌词，去掉时间戳。

    解析复用 scripts/sync_lyrics.py 的 `lyric_to_plain` —— 那边已经处理了
    「一行多个时间戳」这种情况，不在这里再写一份。
    """
    import urllib.request  # noqa: PLC0415
    from scripts.sync_lyrics import lyric_to_plain  # noqa: PLC0415
    url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1"
    try:
        rq = urllib.request.Request(url, headers={
            "User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"})
        with urllib.request.urlopen(rq, timeout=20) as r:
            d = json.loads(r.read().decode())
    except Exception as e:
        raise HTTPException(502, f"取歌词失败：{type(e).__name__} {str(e)[:60]}")

    if d.get("code") != 200:
        raise HTTPException(404, f"网易云返回 code={d.get('code')}")
    lrc = (d.get("lrc") or {}).get("lyric") or ""
    plain = _strip_credits(lyric_to_plain(lrc)) if lrc else ""
    # 纯音乐/器乐作品本来就没词 —— 这不是错误，得说清楚，
    # 否则人会以为接口坏了然后反复重试。
    return {"song_id": song_id, "lyrics": plain, "has_lyrics": bool(plain),
            "note": "" if plain else "这首没有歌词（多半是纯音乐/器乐作品）"}


class SunoCoverRequest(BaseModel):
    """
    翻唱：把 Suno 库里**已有的一首 clip** 换个风格重做。

    ⚠️ 注意它接的是 `clip_id`，**不是上传音频** —— `suno cover` 只认库里的
    clip（`suno cover <CLIP_ID>`，没有上传参数）。想翻唱外部歌曲，得先在
    Suno 网页端 Upload Audio 把它变成一个 clip，再拿那个 id 过来。
    这一步绕不开，CLI 没有对应能力。
    """
    clip_id: str
    tags: str = ""                       # 新风格；留空则沿用原 clip 的风格
    model: str = "v5.5"
    # 原曲对结果的影响强度 0-100。留 None 用 Suno 默认 ——
    # 传一个我们自己拍的数不如让上游决定。
    audio_influence: Optional[int] = None
    title: str = ""                      # 只用于任务标签和产物文件名


@app.get("/api/suno/clips")
def suno_clips(limit: int = 40):
    """
    列出 Suno 库里的作品，给翻唱选源用。

    直接透传 CLI 的结果，不在这里重新组织字段 —— 那边加了字段这边自动就有。
    只挑界面要用的几个，免得把 audio_url 这类一次性签名地址塞进前端缓存。
    """
    import subprocess  # noqa: PLC0415
    if not os.path.exists(SUNO_BIN):
        raise HTTPException(400, f"suno CLI 不存在：{SUNO_BIN}")
    import subprocess  # noqa: PLC0415 —— 与本文件其余 suno 调用一致，延迟导入

    try:
        r = subprocess.run([SUNO_BIN, "list", "--json"], env=_suno_env(),
                           capture_output=True, text=True, timeout=30)
        clips = (json.loads(r.stdout or "{}").get("data") or {}).get("clips") or []
    except Exception as e:
        obs.log("suno_list_failed", level="error", error=str(e)[:200])
        raise HTTPException(502, f"读 Suno 库失败：{type(e).__name__} {str(e)[:80]}")
    return {"clips": [{
        "id": c.get("id", ""),
        "title": c.get("title") or "(未命名)",
        "tags": c.get("metadata", {}).get("tags", "") if isinstance(c.get("metadata"), dict) else "",
        "model": c.get("model_name", ""),
        "image_url": c.get("image_url", ""),
        "created_at": c.get("created_at", ""),
        "status": c.get("status", ""),
    } for c in clips[:limit]]}


@app.post("/api/suno/cover")
def suno_cover(req: SunoCoverRequest):
    """提交翻唱任务（异步）。走和生成同一条队列。"""
    if not req.clip_id.strip():
        raise HTTPException(400, "要翻唱哪一首？缺 clip_id")
    label = f"🎤 翻唱：{req.title or req.clip_id[:8]}"
    return {"task_id": _submit_task("suno_cover", label, req.model_dump()),
            "status": "queued"}


def _run_suno_cover_task(task_id: str, params: dict, update_fn):
    """
    执行翻唱：`suno cover <clip_id>` → 产物拷回 out/music。
    与 _run_suno_task 同形状，区别只在命令和标签。
    """
    import subprocess, shutil, glob, tempfile  # noqa: PLC0415

    req = SunoCoverRequest(**params)
    if not os.path.exists(SUNO_BIN):
        raise ValueError(f"suno CLI 不存在: {SUNO_BIN}（先 cargo install suno）")

    music_dir = OUT_DIR / MUSIC_SUBDIR
    music_dir.mkdir(parents=True, exist_ok=True)
    tmp = tempfile.mkdtemp(prefix="voxcover_")

    cmd = [SUNO_BIN, "cover", req.clip_id, "--model", req.model,
           "--wait", "--download", tmp]
    if req.tags.strip():
        cmd += ["--tags", req.tags.strip()]
    if req.audio_influence is not None:
        cmd += ["--audio-influence", str(req.audio_influence)]

    update_fn(task_id, progress=25, stage="Suno 翻唱中（约 1-3 分钟）...")
    _t0 = time.perf_counter()
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=420,
                       env=_suno_env())
    _ms = int((time.perf_counter() - _t0) * 1000)
    _cr = float((obs.pricing().get("providers", {}).get("suno") or {}).get("credits_per_call", 10))

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-500:]
        obs.meter("suno", "cover", credits=_cr, track_id=req.title[:40],
                  duration_ms=_ms, ok=False, model=req.model,
                  source_clip=req.clip_id[:12], error=err[-120:])
        shutil.rmtree(tmp, ignore_errors=True)
        raise ValueError(f"翻唱失败: {err}")

    obs.meter("suno", "cover", credits=_cr, track_id=req.title[:40],
              duration_ms=_ms, ok=True, model=req.model,
              source_clip=req.clip_id[:12], tags=req.tags[:60])

    update_fn(task_id, progress=85, stage="入库音频库...")
    copied = []
    for f in glob.glob(os.path.join(tmp, "*")):
        if os.path.splitext(f)[1].lower() in AUDIO_EXTS:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe = re.sub(r"[^\w\u4e00-\u9fff-]", "_", req.title or "cover")[:30]
            dest = music_dir / f"[翻唱]{safe}_{ts}{os.path.splitext(f)[1].lower()}"
            shutil.copy2(f, dest)
            copied.append(str(dest))
    shutil.rmtree(tmp, ignore_errors=True)
    if not copied:
        raise ValueError("翻唱成功但没拿到音频文件（Suno 下载链路问题，去网页端看）")

    update_fn(task_id, status="done", progress=100, stage="完成",
              result={"ok": True, "files": copied,
                      "urls": [f"/api/audio/{MUSIC_SUBDIR}/{os.path.basename(c)}" for c in copied]},
              completed_at=datetime.now().strftime("%H:%M:%S"))


class CoverRequest(BaseModel):
    """
    出封面。prompt 留空时由 title/tags 拼一句 —— 大多数时候不需要人自己想词。
    """
    track_id: str = ""
    title: str = ""
    tags: str = ""
    prompt: str = ""
    # 任意 W:H。默认方形（专辑封面就是方的），但**不限枚举** —— 中台的
    # 中台支持任意尺寸，写死枚举等于把上游能力阉掉一半。
    # 合法性由中台判定（它是尺寸规则的真源），这里只挡格式明显写错的。
    ratio: str = "1:1"
    # 留空则按 ratio 自动算一个短边 ≥1440 的合法尺寸（平台要求：汽水 ≥1440、
    # 网易云 ≥1400）。中台按 ratio 自动算的尺寸更保守，短边够不到 1440。
    size: str = ""
    # **留空**。传 "high" 会让中台按 hd 档扣 2 分，而对照实验证明：
    # 传与不传出来的图尺寸体积完全一样（1254×1254），画质也一样
    # （中台不传时本来就按高画质出）。见 core/cover.py 文件头。
    #
    # 这里当初漏改过一次：改了 cover.generate() 的默认值却没改这个 Pydantic
    # 模型的，于是「默认」实际上仍然是 high —— 一个默认值分散在两处，
    # 只改一处就是这种下场。
    quality: str = ""


@app.post("/api/cover/generate")
def cover_generate(req: CoverRequest):
    """
    提交封面出图任务（异步）。

    为什么走任务队列而不是同步等：中台出图要几十秒到几分钟，同步等会让
    前端一直转圈、还占着一个线程池的位置。而队列这套（进度、取消、失败原因）
    早就为 Suno 和 TTS 建好了，封面是第五种任务而已。
    """
    from core import cover
    if not cover.available():
        raise HTTPException(400, "museav CLI 未登录。终端跑一次 `museav login` 即可。")
    if not (req.prompt.strip() or req.title.strip()):
        raise HTTPException(400, "至少要有标题或提示词")
    # 比例写错是用户输入问题，要在提交时就 400 挡掉 —— 丢进任务队列再失败的话，
    # 人得等到任务跑起来才看到「看不懂的比例」，中间还白等一次调度。
    try:
        cover.normalize_ratio(req.ratio)
    except cover.CoverError as e:
        raise HTTPException(400, str(e))
    label = f"🖼 封面：{req.title or req.track_id or '未命名'}"
    return {"task_id": _submit_task("cover", label, req.model_dump()), "status": "queued"}


class CoverUpscaleRequest(BaseModel):
    track_id: str


@app.post("/api/cover/upscale")
def cover_upscale(req: CoverUpscaleRequest):
    """本地 GPU 超分现有封面到 1440，不花中台积分。"""
    from core import pipeline
    t = pipeline.get_track(req.track_id)
    if not t or not t.get("cover_file"):
        raise HTTPException(400, "这首还没有封面可超分")
    label = f"🖼 超分：{t.get('title') or req.track_id}"
    return {"task_id": _submit_task("cover_upscale", label, req.model_dump()),
            "status": "queued"}


@app.get("/api/cover/status")
def cover_status():
    """中台能不能出图、一张多少积分。界面用它决定按钮是可点还是灰掉。"""
    from core import cover
    unit = obs.unit_price("museav")
    bal = cover.balance()
    est = round(cover.CREDITS_PER_COVER * unit, 2)
    return {
        "available": cover.available(),
        # 给界面填下拉用。**不是白名单** —— 用户填别的照样放行，
        # 能不能出由中台判定。
        "common_ratios": [{"value": v, "label": lb} for v, lb in cover.COMMON_RATIOS],
        # 目标边长与各比例算出的实际尺寸 —— 界面能直接告诉人「你会拿到多大的图」
        "cover_side": cover.COVER_SIDE,
        "sizes": {v: cover._size_for(v) for v, _ in cover.COMMON_RATIOS},
        "credits_per_cover": cover.CREDITS_PER_COVER,
        "est_cny": est,
        "credits": bal["credits"],
        "unmetered": bal.get("unmetered", False),
        "covers_left": bal.get("covers_left", 0),
        # 能不能真的出图 = 接了中台**且**（不受额度约束 或 余额够）。
        #
        # 只看 available 的话按钮是亮的、点下去必然失败；只看余额的话，
        # 自家租户余额恒为 0 但出图正常，按钮会一直是灰的 —— 两种误判
        # 都会让人朝错误方向排查。
        "can_generate": bool(cover.available() and
                             (bal.get("unmetered") or bal["credits"] >= cover.CREDITS_PER_COVER)),
        "detail": (f"{bal['detail']}，一张约 ¥{est:.2f}"
                   if cover.available() else "museav CLI 未登录"),
    }


def _run_cover_task(task_id: str, params: dict, update_fn):
    """执行封面出图：中台出图 → 下载 → 回填台账的 cover_file。"""
    from core import cover, pipeline

    req = CoverRequest(**params)
    prompt = req.prompt.strip() or cover.build_prompt(req.title, req.tags)

    result = cover.generate(
        prompt,
        track_id=req.track_id,
        ratio=req.ratio,
        size=req.size,
        quality=req.quality,
        on_progress=lambda pct, stage: update_fn(task_id, progress=pct, stage=stage),
    )

    # 回填台账。出了图不落台账等于没出 —— 下次打开看板还是没封面，
    # 人会以为失败了然后再出一张，白烧一次积分。
    if req.track_id:
        try:
            pipeline.upsert(req.track_id, cover_file=result["path"])
        except Exception as e:                                    # noqa: BLE001
            obs.log("cover_ledger_write_failed", level="warn",
                    track_id=req.track_id, error=str(e)[:200])

    # 比例被上游改掉时把话说明白 —— 图是好图，但画幅不是要的那个，
    # 拿去当封面会被平台裁掉或留白。不静默通过。
    note = ""
    if result.get("ratio_ok") is False:
        note = (f"⚠️ 上游没按 {result['ratio_requested']} 出图，"
                f"实际 {result.get('width')}×{result.get('height')} —— "
                f"换个上游重出可能就对了")

    update_fn(task_id, status="done", progress=100, stage="完成",
              result={"ok": True, "prompt": prompt, "note": note, **result},
              completed_at=datetime.now().strftime("%H:%M:%S"))


def _run_cover_upscale_task(task_id: str, params: dict, update_fn):
    """本地 GPU 超分现有封面到 1440，回填台账。不花中台积分。"""
    from pathlib import Path
    from core import cover, pipeline
    from core.paths import DATA_DIR, PUBLISH_DIR

    tid = (params.get("track_id") or "").strip()
    t = pipeline.get_track(tid)
    if not t or not t.get("cover_file"):
        raise ValueError("这首还没有封面可超分")
    src = Path(t["cover_file"])
    if not src.is_absolute():
        src = DATA_DIR / src
    title = t.get("release_title") or t.get("title") or tid
    dest = PUBLISH_DIR / "covers" / f"{title}_1440.jpg"
    result = cover.upscale_local(
        src, dest,
        on_progress=lambda pct, stage: update_fn(task_id, progress=pct, stage=stage),
    )
    rel = str(result.relative_to(DATA_DIR)) if str(result).startswith(str(DATA_DIR)) else str(result)
    pipeline.upsert(tid, cover_file=rel)
    update_fn(task_id, status="done", progress=100, stage="完成",
              result={"ok": True, "path": rel},
              completed_at=datetime.now().strftime("%H:%M:%S"))


def _clip_ids_from(stdout: str) -> list[dict]:
    """从 `suno generate --json` 的回包里取 clip 列表。

    回包结构在不同版本里换过几次，所以这里**认字段不认路径**：
    递归找带 id 的对象。写死路径的话，Suno 一改 schema 就静默拿不到 ——
    而拿不到的表现是「提交成功但没有 id」，看起来像生成失败。
    """
    try:
        data = json.loads(stdout or "{}")
    except json.JSONDecodeError:
        return []
    out: list[dict] = []

    def walk(node):
        if isinstance(node, dict):
            cid = node.get("id") or node.get("clip_id")
            if isinstance(cid, str) and len(cid) == 36 and cid.count("-") == 4:
                out.append({"id": cid, "title": node.get("title", ""),
                            "status": node.get("status", "")})
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)

    walk(data)
    seen, uniq = set(), []
    for c in out:
        if c["id"] not in seen:
            seen.add(c["id"])
            uniq.append(c)
    return uniq


def _clip_status(ids: list[str]) -> list[dict]:
    """查一批 clip 的状态。查不到就返回空 —— 调用方按「还没好」处理，
    不当成失败（网络抖一下不该让一次成功的生成前功尽弃）。"""
    import subprocess  # noqa: PLC0415

    if not ids:
        return []
    try:
        r = subprocess.run([SUNO_BIN, "status", *ids, "--json"], env=_suno_env(),
                           capture_output=True, text=True, timeout=60)
        return _clip_ids_from(r.stdout)
    except (subprocess.SubprocessError, OSError):
        return []


def _recent_clips_titled(title: str, since_ts) -> list[dict]:
    """去 Suno 问：这个标题、这个时间点之后，有没有新出的 clip。

    用来在 CLI 报错时判断「到底生成没生成」。`suno list` 是免费命令，
    问一次不花钱，而问错的代价是：积分照扣、歌明明在、人以为白花了。

    按**标题 + 时间**匹配，不按标题单独匹配 —— 同名歌很常见
    （Suno 一次就出两首同名的），只看标题会把上次的旧歌错认成这次的。
    """
    import subprocess  # noqa: PLC0415 —— 与本文件其余 suno 调用一致，延迟导入

    try:
        r = subprocess.run([SUNO_BIN, "list", "--json"], env=_suno_env(),
                           capture_output=True, text=True, timeout=60)
        clips = (json.loads(r.stdout or "{}").get("data") or {}).get("clips") or []
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError, ValueError):
        return []
    out = []
    for c in clips:
        if (c.get("title") or "").strip() != (title or "").strip():
            continue
        try:
            made = datetime.fromisoformat((c.get("created_at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if made >= since_ts:
            out.append({"id": c.get("id"), "title": c.get("title"),
                        "status": c.get("status"), "created_at": c.get("created_at")})
    return out


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

    # ⚠️ **不加 --wait。**
    #
    # 生成本身是异步的：提交之后 Suno 那边排队、渲染，两三分钟出结果。
    # `--wait` 把它硬跑成同步 —— CLI 阻塞在那儿，voxflow 只能设个超时，
    # 于是「CLI 超时/中途出错」就被当成了「生成失败」。
    #
    # 2026-09-06 连栽两次：歌在 Suno 上好好的、积分也扣了，voxflow 却报失败、
    # 群里推失败卡片。错的不是判断逻辑，是**用同步的方式跑异步的事**。
    #
    # 现在：提交立刻拿 clip id → 轮询 status 直到 complete。
    # CLI 只负责发起，进度由我们自己看着，中间断了也不影响 Suno 那边。
    update_fn(task_id, progress=10, stage="提交到 Suno...")
    cmd = [SUNO_BIN, "generate", "--title", req.title, "--model", req.model, "--json"]
    if req.tags:
        cmd += ["--tags", req.tags]
    if req.lyrics:
        cmd += ["--lyrics", req.lyrics]
    elif req.lyrics_file and os.path.exists(req.lyrics_file):
        cmd += ["--lyrics-file", req.lyrics_file]
    if persona_id:
        cmd += ["--persona", persona_id]

    import tempfile
    tmp = tempfile.mkdtemp(prefix="voxsuno_")

    _t0 = time.perf_counter()
    _started_at = datetime.now(timezone.utc)
    # ⚠️ env=_suno_env() 不能漏 —— 它顺带清掉上一次残留的验证码 Chrome。
    # 漏了的后果：残留进程占着同一个 profile，新的 Chrome 一起来就退，
    # 报「Chrome was spawned but never opened the CDP port」，于是
    # **之后每一次生成都失败**。2026-09-06 就是只给翻唱那处加了、
    # 漏了这处生成，白排查一轮。
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=360,
                       env=_suno_env())
    _ms = int((time.perf_counter() - _t0) * 1000)
    # 每次调用扣的 credits 从 pricing.json 读，不写死在这里 ——
    # 换模型/套餐时改配置，不用改代码。
    _cr = float((obs.pricing().get("providers", {}).get("suno") or {}).get("credits_per_call", 10))
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-800:]
        # 提交这一步失败才是真失败 —— 任务根本没进 Suno 的队列。
        # 但仍要回查一次：提交成功、只是回包没读到的情况也存在。
        clips = _recent_clips_titled(req.title, since_ts=_started_at) or _clip_ids_from(r.stdout)
        if not clips:
            obs.meter("suno", "generate", credits=_cr, track_id=req.title[:40],
                      duration_ms=_ms, ok=False, model=req.model, error=err[-120:])
            raise ValueError(f"Suno 提交失败: {err}")
    else:
        clips = _clip_ids_from(r.stdout) or _recent_clips_titled(req.title, since_ts=_started_at)

    if not clips:
        raise ValueError(f"提交成功但没拿到 clip id：{(r.stdout or r.stderr)[-300:]}")

    # ── 轮询，而不是阻塞等 ────────────────────────────────────────
    #
    # 生成在 Suno 服务端跑，这里只是**看着**。中间网络断了、进程被重启，
    # 都不影响那边的任务 —— 重新查一次状态就能接上，不会把一次成功的生成
    # 判成失败。这正是 `--wait` 做不到的：它一断，信息就没了。
    ids = [c["id"] for c in clips]
    obs.meter("suno", "generate", credits=_cr, track_id=req.title[:40],
              duration_ms=_ms, ok=True, model=req.model, tags=req.tags[:60],
              clips=len(ids))
    update_fn(task_id, progress=25, stage=f"Suno 生成中（{len(ids)} 首）...")

    deadline = time.time() + 900          # 15 分钟，比 Suno 正常出歌久得多
    done = []
    while time.time() < deadline:
        time.sleep(10)
        st = _clip_status(ids)
        done = [c for c in st if c.get("status") == "complete"]
        # 进度按「完成几首」算，不再是写死的 30% —— 那个数字骗了人很久：
        # 卡在 30% 看起来像卡住了，其实一直在正常生成。
        pct = 25 + int(60 * len(done) / max(len(ids), 1))
        update_fn(task_id, progress=pct,
                  stage=f"Suno 生成中 {len(done)}/{len(ids)} 首...")
        if len(done) == len(ids):
            break
        if any(c.get("status") == "error" for c in st):
            raise ValueError(f"Suno 报告生成错误：{[c.get('id','')[:8] for c in st if c.get('status')=='error']}")
    if not done:
        raise ValueError(f"等了 15 分钟仍未完成（clip: {', '.join(i[:8] for i in ids)}）—— "
                         f"任务还在 Suno 上，稍后可在网页端查看")

    update_fn(task_id, progress=85, stage="入库音频库...")
    copied = []
    for f in glob.glob(os.path.join(tmp, "*")):
        if os.path.splitext(f)[1].lower() in AUDIO_EXTS:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            safe = re.sub(r"[^\w\u4e00-\u9fff-]", "_", req.title or "cover")[:30]
            dest = music_dir / f"[翻唱]{safe}_{ts}{os.path.splitext(f)[1].lower()}"
            shutil.copy2(f, dest)
            copied.append(str(dest))
    shutil.rmtree(tmp, ignore_errors=True)
    if not copied:
        raise ValueError("翻唱成功但没拿到音频文件（Suno 下载链路问题，去网页端看）")

    update_fn(task_id, status="done", progress=100, stage="完成",
              result={"ok": True, "files": copied,
                      "urls": [f"/api/audio/{MUSIC_SUBDIR}/{os.path.basename(c)}" for c in copied]},
              completed_at=datetime.now().strftime("%H:%M:%S"))


class CoverRequest(BaseModel):
    """
    出封面。prompt 留空时由 title/tags 拼一句 —— 大多数时候不需要人自己想词。
    """
    track_id: str = ""
    title: str = ""
    tags: str = ""
    prompt: str = ""
    # 任意 W:H。默认方形（专辑封面就是方的），但**不限枚举** —— 中台的
    # 中台支持任意尺寸，写死枚举等于把上游能力阉掉一半。
    # 合法性由中台判定（它是尺寸规则的真源），这里只挡格式明显写错的。
    ratio: str = "1:1"
    # 留空则按 ratio 自动算一个短边 ≥1440 的合法尺寸（平台要求：汽水 ≥1440、
    # 网易云 ≥1400）。中台按 ratio 自动算的尺寸更保守，短边够不到 1440。
    size: str = ""
    # **留空**。传 "high" 会让中台按 hd 档扣 2 分，而对照实验证明：
    # 传与不传出来的图尺寸体积完全一样（1254×1254），画质也一样
    # （中台不传时本来就按高画质出）。见 core/cover.py 文件头。
    #
    # 这里当初漏改过一次：改了 cover.generate() 的默认值却没改这个 Pydantic
    # 模型的，于是「默认」实际上仍然是 high —— 一个默认值分散在两处，
    # 只改一处就是这种下场。
    quality: str = ""


@app.post("/api/cover/generate")
def cover_generate(req: CoverRequest):
    """
    提交封面出图任务（异步）。

    为什么走任务队列而不是同步等：中台出图要几十秒到几分钟，同步等会让
    前端一直转圈、还占着一个线程池的位置。而队列这套（进度、取消、失败原因）
    早就为 Suno 和 TTS 建好了，封面是第五种任务而已。
    """
    from core import cover
    if not cover.available():
        raise HTTPException(400, "museav CLI 未登录。终端跑一次 `museav login` 即可。")
    if not (req.prompt.strip() or req.title.strip()):
        raise HTTPException(400, "至少要有标题或提示词")
    # 比例写错是用户输入问题，要在提交时就 400 挡掉 —— 丢进任务队列再失败的话，
    # 人得等到任务跑起来才看到「看不懂的比例」，中间还白等一次调度。
    try:
        cover.normalize_ratio(req.ratio)
    except cover.CoverError as e:
        raise HTTPException(400, str(e))
    label = f"🖼 封面：{req.title or req.track_id or '未命名'}"
    return {"task_id": _submit_task("cover", label, req.model_dump()), "status": "queued"}


class CoverUpscaleRequest(BaseModel):
    track_id: str


@app.post("/api/cover/upscale")
def cover_upscale(req: CoverUpscaleRequest):
    """本地 GPU 超分现有封面到 1440，不花中台积分。"""
    from core import pipeline
    t = pipeline.get_track(req.track_id)
    if not t or not t.get("cover_file"):
        raise HTTPException(400, "这首还没有封面可超分")
    label = f"🖼 超分：{t.get('title') or req.track_id}"
    return {"task_id": _submit_task("cover_upscale", label, req.model_dump()),
            "status": "queued"}


@app.get("/api/cover/status")
def cover_status():
    """中台能不能出图、一张多少积分。界面用它决定按钮是可点还是灰掉。"""
    from core import cover
    unit = obs.unit_price("museav")
    bal = cover.balance()
    est = round(cover.CREDITS_PER_COVER * unit, 2)
    return {
        "available": cover.available(),
        # 给界面填下拉用。**不是白名单** —— 用户填别的照样放行，
        # 能不能出由中台判定。
        "common_ratios": [{"value": v, "label": lb} for v, lb in cover.COMMON_RATIOS],
        # 目标边长与各比例算出的实际尺寸 —— 界面能直接告诉人「你会拿到多大的图」
        "cover_side": cover.COVER_SIDE,
        "sizes": {v: cover._size_for(v) for v, _ in cover.COMMON_RATIOS},
        "credits_per_cover": cover.CREDITS_PER_COVER,
        "est_cny": est,
        "credits": bal["credits"],
        "unmetered": bal.get("unmetered", False),
        "covers_left": bal.get("covers_left", 0),
        # 能不能真的出图 = 接了中台**且**（不受额度约束 或 余额够）。
        #
        # 只看 available 的话按钮是亮的、点下去必然失败；只看余额的话，
        # 自家租户余额恒为 0 但出图正常，按钮会一直是灰的 —— 两种误判
        # 都会让人朝错误方向排查。
        "can_generate": bool(cover.available() and
                             (bal.get("unmetered") or bal["credits"] >= cover.CREDITS_PER_COVER)),
        "detail": (f"{bal['detail']}，一张约 ¥{est:.2f}"
                   if cover.available() else "museav CLI 未登录"),
    }


def _run_cover_task(task_id: str, params: dict, update_fn):
    """执行封面出图：中台出图 → 下载 → 回填台账的 cover_file。"""
    from core import cover, pipeline

    req = CoverRequest(**params)
    prompt = req.prompt.strip() or cover.build_prompt(req.title, req.tags)

    result = cover.generate(
        prompt,
        track_id=req.track_id,
        ratio=req.ratio,
        size=req.size,
        quality=req.quality,
        on_progress=lambda pct, stage: update_fn(task_id, progress=pct, stage=stage),
    )

    # 回填台账。出了图不落台账等于没出 —— 下次打开看板还是没封面，
    # 人会以为失败了然后再出一张，白烧一次积分。
    if req.track_id:
        try:
            pipeline.upsert(req.track_id, cover_file=result["path"])
        except Exception as e:                                    # noqa: BLE001
            obs.log("cover_ledger_write_failed", level="warn",
                    track_id=req.track_id, error=str(e)[:200])

    # 比例被上游改掉时把话说明白 —— 图是好图，但画幅不是要的那个，
    # 拿去当封面会被平台裁掉或留白。不静默通过。
    note = ""
    if result.get("ratio_ok") is False:
        note = (f"⚠️ 上游没按 {result['ratio_requested']} 出图，"
                f"实际 {result.get('width')}×{result.get('height')} —— "
                f"换个上游重出可能就对了")

    update_fn(task_id, status="done", progress=100, stage="完成",
              result={"ok": True, "prompt": prompt, "note": note, **result},
              completed_at=datetime.now().strftime("%H:%M:%S"))


def _run_cover_upscale_task(task_id: str, params: dict, update_fn):
    """本地 GPU 超分现有封面到 1440，回填台账。不花中台积分。"""
    from pathlib import Path
    from core import cover, pipeline
    from core.paths import DATA_DIR, PUBLISH_DIR

    tid = (params.get("track_id") or "").strip()
    t = pipeline.get_track(tid)
    if not t or not t.get("cover_file"):
        raise ValueError("这首还没有封面可超分")
    src = Path(t["cover_file"])
    if not src.is_absolute():
        src = DATA_DIR / src
    title = t.get("release_title") or t.get("title") or tid
    dest = PUBLISH_DIR / "covers" / f"{title}_1440.jpg"
    result = cover.upscale_local(
        src, dest,
        on_progress=lambda pct, stage: update_fn(task_id, progress=pct, stage=stage),
    )
    rel = str(result.relative_to(DATA_DIR)) if str(result).startswith(str(DATA_DIR)) else str(result)
    pipeline.upsert(tid, cover_file=rel)
    update_fn(task_id, status="done", progress=100, stage="完成",
              result={"ok": True, "path": rel},
              completed_at=datetime.now().strftime("%H:%M:%S"))


def _recent_clips_titled(title: str, since_ts) -> list[dict]:
    """去 Suno 问：这个标题、这个时间点之后，有没有新出的 clip。

    用来在 CLI 报错时判断「到底生成没生成」。`suno list` 是免费命令，
    问一次不花钱，而问错的代价是：积分照扣、歌明明在、人以为白花了。

    按**标题 + 时间**匹配，不按标题单独匹配 —— 同名歌很常见
    （Suno 一次就出两首同名的），只看标题会把上次的旧歌错认成这次的。
    """
    import subprocess  # noqa: PLC0415 —— 与本文件其余 suno 调用一致，延迟导入

    try:
        r = subprocess.run([SUNO_BIN, "list", "--json"], env=_suno_env(),
                           capture_output=True, text=True, timeout=60)
        clips = (json.loads(r.stdout or "{}").get("data") or {}).get("clips") or []
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError, ValueError):
        return []
    out = []
    for c in clips:
        if (c.get("title") or "").strip() != (title or "").strip():
            continue
        try:
            made = datetime.fromisoformat((c.get("created_at") or "").replace("Z", "+00:00"))
        except ValueError:
            continue
        if made >= since_ts:
            out.append({"id": c.get("id"), "title": c.get("title"),
                        "status": c.get("status"), "created_at": c.get("created_at")})
    return out


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

    # ⚠️ **不加 --wait。**
    #
    # 生成本身是异步的：提交之后 Suno 那边排队、渲染，两三分钟出结果。
    # `--wait` 把它硬跑成同步 —— CLI 阻塞在那儿，voxflow 只能设个超时，
    # 于是「CLI 超时/中途出错」就被当成了「生成失败」。
    #
    # 2026-09-06 连栽两次：歌在 Suno 上好好的、积分也扣了，voxflow 却报失败、
    # 群里推失败卡片。错的不是判断逻辑，是**用同步的方式跑异步的事**。
    #
    # 现在：提交立刻拿 clip id → 轮询 status 直到 complete。
    # CLI 只负责发起，进度由我们自己看着，中间断了也不影响 Suno 那边。
    update_fn(task_id, progress=10, stage="提交到 Suno...")
    cmd = [SUNO_BIN, "generate", "--title", req.title, "--model", req.model, "--json"]
    if req.tags:
        cmd += ["--tags", req.tags]
    if req.lyrics:
        cmd += ["--lyrics", req.lyrics]
    elif req.lyrics_file and os.path.exists(req.lyrics_file):
        cmd += ["--lyrics-file", req.lyrics_file]
    if persona_id:
        cmd += ["--persona", persona_id]

    import tempfile
    tmp = tempfile.mkdtemp(prefix="voxsuno_")

    _t0 = time.perf_counter()
    _started_at = datetime.now(timezone.utc)
    # ⚠️ env=_suno_env() 不能漏 —— 它顺带清掉上一次残留的验证码 Chrome。
    # 漏了的后果：残留进程占着同一个 profile，新的 Chrome 一起来就退，
    # 报「Chrome was spawned but never opened the CDP port」，于是
    # **之后每一次生成都失败**。2026-09-06 就是只给翻唱那处加了、
    # 漏了这处生成，白排查一轮。
    r = subprocess.run(cmd, capture_output=True, text=True, timeout=360,
                       env=_suno_env())
    _ms = int((time.perf_counter() - _t0) * 1000)
    # 每次调用扣的 credits 从 pricing.json 读，不写死在这里 ——
    # 换模型/套餐时改配置，不用改代码。
    _cr = float((obs.pricing().get("providers", {}).get("suno") or {}).get("credits_per_call", 10))
    if r.returncode != 0:
        err = (r.stderr or r.stdout or "")[-500:]
        # ⚠️ **CLI 退出码不等于「没生成出来」。**
        #
        # 2026-09-06：三首 BGM 的 CLI 全部报错（challenge-expired / 下载 403），
        # voxflow 于是标成失败、任务从队列消失。可去 Suno 一看，歌**好好地在那儿**
        # ——积分照扣，人以为白花了。
        #
        # 生成是在 Suno 服务端完成的，CLI 只是发起和取回。取回那一段坏了
        # （Suno 现在不给音频直链，见 _pull_suno_clips 的注释），
        # 不代表生成失败。所以报错之后必须**去问一次 Suno**，
        # 有对得上的新 clip 就按成功记，只是音频要另外拿。
        found = _recent_clips_titled(req.title, since_ts=_started_at)
        if found:
            obs.meter("suno", "generate", credits=_cr, track_id=req.title[:40],
                      duration_ms=_ms, ok=True, model=req.model,
                      note="CLI 报错但 Suno 已生成")
            update_fn(task_id, status="done", progress=100,
                      stage=f"已生成 {len(found)} 首（音频需手动下载）",
                      result={"ok": True, "files": [], "clips": found,
                              "warning": "CLI 取回失败，歌在 Suno 上，音频要去网页端下载"})
            obs.log("suno_cli_failed_but_generated", level="warn",
                    title=req.title[:40], clips=len(found), error=err[-200:])
            return
        # 失败也计量：Suno 生成失败照样扣积分，只记成功的话账对不上，
        # 而「失败率 × 单价」正是最该被看见的那笔浪费。
        obs.meter("suno", "generate", credits=_cr, track_id=req.title[:40],
                  duration_ms=_ms, ok=False, model=req.model, error=err[-120:])
        raise ValueError(f"Suno 生成失败: {err}")
    obs.meter("suno", "generate", credits=_cr, track_id=req.title[:40],
              duration_ms=_ms, ok=True, model=req.model, tags=req.tags[:60])

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
        # **没拿到音频 ≠ 生成失败。** 歌已经在 Suno 上了、积分也扣了，
        # 只是取回那一段坏了（Suno 现在不给音频直链，API 和 CDN 都 403）。
        # 报成失败会让人以为白花钱，还会往群里推一张失败卡片。
        update_fn(task_id, status="done", progress=100,
                  stage=f"已生成 {len(done)} 首 · 音频需在 suno.com 下载",
                  result={"ok": True, "files": [], "clips": done,
                          "warning": "Suno 已停止提供音频直链，音频请去网页端下载"})
        obs.log("suno_audio_not_pulled", level="warn",
                title=req.title[:40], clips=len(done))
        return

    update_fn(
        task_id, status="done", progress=100, stage="完成",
        result={"ok": True, "files": copied,
                "urls": [f"/api/audio/{MUSIC_SUBDIR}/{os.path.basename(c)}" for c in copied]},
    )


@app.post("/api/dialogue")
def dialogue(req: dict):
    """提交多角色对话合成任务（异步）"""
    if "lines" not in req or not isinstance(req["lines"], list):
        raise HTTPException(400, "剧本格式错误，缺少台词 lines 列表")

    title = req.get("title", "未命名剧目")
    label = f"🎭 剧本: {title} ({len(req['lines'])} 句)"

    task_id = _submit_task("dialogue", label, req)
    return {"task_id": task_id, "status": "queued"}


@app.get("/api/audio/{subdir}/{filename}")
def get_audio_subdir(subdir: str, filename: str):
    """获取子目录音频（out/music/...）"""
    safe_sub = os.path.basename(subdir)
    safe_name = os.path.basename(filename)
    path = OUT_DIR / safe_sub / safe_name
    if not path.exists():
        raise HTTPException(404, f"音频文件不存在: {safe_name}")
    media_type = MEDIA_TYPES.get(path.suffix.lower(), "application/octet-stream")
    return FileResponse(str(path), media_type=media_type, filename=safe_name)


@app.get("/api/platform-accounts")
def platform_accounts():
    """
    各平台账号资产：我是谁、发了多少首、主页在哪。

    数据来自 scripts/sync_*.py 从平台抓回来的真实状态，不是手填的 ——
    手填的台账会随时间变假（今天发一首、明天下架一首，没人记得回来改）。

    返回里带 local_online_count：平台自报的数与台账实际在线数对不对得上，
    数字自己会说话，比在界面上写「同步成功」有用。
    """
    from core import pipeline
    return pipeline.list_platform_accounts()


@app.get("/api/albums")
def albums_endpoint(platform: str = None):
    """
    专辑 + 每张专辑的曲目。

    专辑是**独立实体**，不是歌的附属字段：有自己的封面、发行时间、简介、
    曲目数，发别的平台时整张一起走。

    曲目的 join 在 SQL 里做（core/pipeline.list_albums）—— 以前是在这里
    手写双重循环把两份 JSON 读进内存自己配对，那不叫查询。
    """
    from core import pipeline
    return {"albums": {a["key"]: a for a in pipeline.list_albums(platform)}}


@app.get("/api/album-cover/{album_key}")
def album_cover(album_key: str):
    """专辑封面（同步时下到本地那份，不依赖平台图床 —— 图床 URL 会失效）。"""
    from core import pipeline
    from core.paths import DATA_DIR
    a = next((x for x in pipeline.list_albums() if x["key"] == album_key), None)
    if not a or not a.get("cover_local"):
        raise HTTPException(404, "这张专辑没有本地封面")
    path = DATA_DIR / a["cover_local"]
    if not path.exists():
        raise HTTPException(404, "封面文件不在了")
    return FileResponse(str(path), media_type="image/jpeg",
                        headers={"Cache-Control": "no-store"})


@app.get("/api/cover/{track_id}")
def get_cover(track_id: str):
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
