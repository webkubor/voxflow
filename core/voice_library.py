"""音色库领域规则 —— Web 与 CLI 共用的唯一出处。

## 为什么单独成模块

这些规则原来只写在 web/app.py 里，CLI 各自又写了一套更宽松的：
`voice voice rm` 能删已收藏音色、`voice preset run` 生成的文件名 Web 认不出
（模板永远显示「未生成」、可被重复生成）、`voice voice import` 非原子整份覆盖。
同一份数据两套规则，等于没有规则。所以凡是「什么算已生成 / 能不能删 /
怎么写 personas.json」的判断，只在这里写一次。

## 约定

- personas.json 的读改写一律在 `personas_lock()` 内完成，写入走临时文件 +
  os.replace；锁文件与 core.utils.upsert_persona_mapping 是同一个，跨进程互斥。
- 没写 favorite 字段的旧音色视为已收藏 —— 升级后历史资产不能突然变得可删。
- 删除音色只删映射，不删参考音频；生成库文件只有在关联音色未收藏时才可删。
- 失败抛 VoiceLibraryError 的子类，带 status（与 HTTP 语义一致），
  Web 转 HTTPException，CLI 转退出码。
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from core import paths

AUDIO_EXTS = {".wav", ".mp3", ".m4a", ".flac", ".ogg"}
_DESIGN_FILE_RE = re.compile(r"^\[设计\](.+?)_(?:[0-9a-f]{8}_)?\d{8}_\d{6}\.wav$")


class VoiceLibraryError(Exception):
    status = 400


class NotFound(VoiceLibraryError):
    status = 404


class Conflict(VoiceLibraryError):
    status = 409


# ── 路径（调用时取值，便于测试用 VOXFLOW_HOME / patch 隔离）─────────────

def _personas_file(personas_file: Optional[Path] = None) -> Path:
    return Path(personas_file or paths.PERSONAS_FILE)


def _out_dir(out_dir: Optional[Path] = None) -> Path:
    return Path(out_dir or paths.OUT_DIR)


# ── 设计文件命名与模板「已生成」识别 ────────────────────────────────

def safe_voice_name(voice_name: str) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff-]", "_", voice_name)


def name_fingerprint(voice_name: str) -> str:
    return hashlib.sha256(voice_name.encode("utf-8")).hexdigest()[:8]


def design_filename(voice_name: str, ts: Optional[str] = None) -> str:
    """设计产物文件名。Web、CLI、预设批量必须都用它，模板状态才认得出。"""
    ts = ts or datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"[设计]{safe_voice_name(voice_name)}_{name_fingerprint(voice_name)}_{ts}.wav"


def write_design_sidecar(audio_path: Path, ref_text: str) -> None:
    """保存样音实际念的原文，之后「试听满意再收藏」时不用再手填。"""
    Path(audio_path).with_suffix(".json").write_text(
        json.dumps({"ref_text": ref_text}, ensure_ascii=False), encoding="utf-8")


def find_preset_audio(voice_name: str, data_dir: Optional[Path] = None) -> Optional[Path]:
    """模板对应的最新生成样音；按结构化文件名精确匹配，不做模糊匹配。"""
    data_dir = Path(data_dir or paths.DATA_DIR)
    design_root = data_dir / "out" / "design"
    search_dirs = [data_dir / "assets" / "temp", data_dir / "out"]
    if design_root.is_dir():
        search_dirs += sorted((d for d in design_root.iterdir() if d.is_dir()), reverse=True)
    safe, fid = safe_voice_name(voice_name), name_fingerprint(voice_name)
    legacy = re.compile(rf"^{re.escape(safe)}_\d{{8}}_\d{{6}}\.wav$")
    designed = re.compile(rf"^\[设计\]{re.escape(safe)}_(?:{fid}_)?\d{{8}}_\d{{6}}\.wav$")
    candidates = []
    for d in search_dirs:
        if not d.exists():
            continue
        for f in d.glob("*.wav"):
            if designed.fullmatch(f.name) or legacy.fullmatch(f.name) or f.name == f"当前参考_{voice_name}.wav":
                candidates.append(f)
    if not candidates:
        return None
    return max(candidates, key=lambda x: x.stat().st_mtime)


def preset_dirs(data_dir: Optional[Path] = None, project_dir: Optional[Path] = None) -> list[Path]:
    """用户模板目录在前（同名覆盖内置），内置模板目录在后。"""
    return [Path(data_dir or paths.DATA_DIR) / "configs" / "presets",
            Path(project_dir or paths.PROJECT_DIR) / "configs" / "presets"]


def preset_files(data_dir: Optional[Path] = None, project_dir: Optional[Path] = None) -> list[Path]:
    files: dict[str, Path] = {}
    for directory in preset_dirs(data_dir, project_dir):
        if directory.is_dir():
            for p in directory.glob("*.json"):
                files.setdefault(p.name, p)
    return sorted(files.values(), key=lambda p: p.name)


def scan_design_presets(data_dir: Optional[Path] = None, project_dir: Optional[Path] = None) -> list[dict]:
    """全部 VoiceDesign 模板及其生成状态。"""
    result = []
    for f in preset_files(data_dir, project_dir):
        try:
            cfg = json.loads(f.read_text(encoding="utf-8"))
        except Exception:
            continue
        if not isinstance(cfg, dict) or cfg.get("model_type") != "VoiceDesign":
            continue
        voice_name = str(cfg.get("voice_name", "")).strip()
        if not voice_name:
            continue
        audio = find_preset_audio(voice_name, data_dir)
        result.append({
            "voice_name": voice_name,
            "config_file": f.name,
            "config_path": str(f),
            "tone": cfg.get("tone", ""),
            "emotion": cfg.get("emotion", ""),
            "text": cfg.get("text", ""),
            "has_generated": audio is not None,
            "audio_file": audio.name if audio else None,
            "audio_path": str(audio) if audio else None,
        })
    return result


@contextmanager
def preset_generation_lock(voice_name: str, data_dir: Optional[Path] = None):
    """模板生成的跨进程互斥。

    Web 的「正在生成」判断只在自己进程的任务队列里，CLI 同时跑同一模板它看不见。
    这把非阻塞锁让第二个生成者立刻失败（Conflict），持锁后调用方还要再查一次
    「已生成」，两步合起来才是「一个模板只生成一次」。
    """
    from fcntl import flock, LOCK_EX, LOCK_NB, LOCK_UN
    lock_dir = Path(data_dir or paths.DATA_DIR) / "out" / ".locks"
    lock_dir.mkdir(parents=True, exist_ok=True)
    with open(lock_dir / f"design-{name_fingerprint(voice_name)}.lock", "a") as lock:
        try:
            flock(lock.fileno(), LOCK_EX | LOCK_NB)
        except BlockingIOError as exc:
            raise Conflict("该模板正在生成，请等待任务完成") from exc
        try:
            if find_preset_audio(voice_name, data_dir) is not None:
                raise Conflict("该模板已经生成，请在生成库中查看")
            yield
        finally:
            flock(lock.fileno(), LOCK_UN)


# ── personas.json 读写 ─────────────────────────────────────────────

@contextmanager
def personas_lock(personas_file: Optional[Path] = None):
    """与 core.utils.upsert_persona_mapping 同一把跨进程锁。"""
    from fcntl import flock, LOCK_EX, LOCK_UN
    pf = _personas_file(personas_file)
    pf.parent.mkdir(parents=True, exist_ok=True)
    with open(str(pf) + ".lock", "a") as lock:
        flock(lock.fileno(), LOCK_EX)
        try:
            yield pf
        finally:
            flock(lock.fileno(), LOCK_UN)


def load_personas(personas_file: Optional[Path] = None) -> dict:
    pf = _personas_file(personas_file)
    if not pf.exists():
        return {}
    data = json.loads(pf.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise VoiceLibraryError("personas.json 格式错误；保留原文件，请先修复")
    return data


def write_personas_atomic(data: dict, personas_file: Optional[Path] = None) -> None:
    """临时文件 + os.replace；中途中断不会截断音色库。调用方须持有 personas_lock。"""
    pf = _personas_file(personas_file)
    temp_path = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", dir=pf.parent, delete=False) as f:
            temp_path = f.name
            json.dump(data, f, ensure_ascii=False, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, pf)
    finally:
        if temp_path and os.path.exists(temp_path):
            os.unlink(temp_path)


def is_favorite(entry) -> bool:
    return not isinstance(entry, dict) or bool(entry.get("favorite", True))


def describe_voice(key: str, entry, data_dir: Optional[Path] = None) -> dict:
    data_dir = Path(data_dir or paths.DATA_DIR)
    e = entry if isinstance(entry, dict) else {"name": entry}
    ref = str(e.get("ref", "") or "")
    return {
        "key": key,
        "name": e.get("name", key),
        "favorite": is_favorite(entry),
        "ref": ref,
        "has_audio": bool(ref) and (data_dir / ref).is_file(),
        "ref_text": e.get("ref_text", ""),
        "instruction": e.get("instruction", ""),
        "desc": e.get("desc", ""),
        "source_filename": e.get("source_filename", ""),
    }


def list_voices(favorites_only: bool = False, personas_file: Optional[Path] = None,
                data_dir: Optional[Path] = None) -> list[dict]:
    voices = [describe_voice(k, v, data_dir) for k, v in load_personas(personas_file).items()]
    return [v for v in voices if v["favorite"]] if favorites_only else voices


def update_voice(key: str, name: Optional[str] = None, desc: Optional[str] = None,
                 favorite: Optional[bool] = None, personas_file: Optional[Path] = None) -> dict:
    """改名 / 改描述 / 收藏状态。只改字段，不动任何音频文件。"""
    with personas_lock(personas_file) as pf:
        data = load_personas(pf)
        if key not in data:
            raise NotFound(f"音色 {key} 不存在")
        entry = data[key] if isinstance(data[key], dict) else {"name": data[key]}
        if name is not None:
            if not name.strip():
                raise VoiceLibraryError("音色名称不能为空")
            entry["name"] = name.strip()
        if desc is not None:
            entry["desc"] = desc.strip()
        if favorite is not None:
            entry["favorite"] = bool(favorite)
        data[key] = entry
        write_personas_atomic(data, pf)
    return describe_voice(key, entry)


def delete_voice(key: str, personas_file: Optional[Path] = None, confirm: bool = False) -> dict:
    """删除音色映射；参考音频保留。

    confirm=False（默认）是程序化调用的安全网：已收藏的音色拒绝删除。
    人在界面上看过「将同时从收藏音色库移除、参考音频保留」之后，
    调用方带 confirm=True 再删 —— 不能因为用户收藏了就永远删不掉。
    """
    with personas_lock(personas_file) as pf:
        data = load_personas(pf)
        if key not in data:
            raise NotFound(f"音色 {key} 不存在")
        if is_favorite(data[key]) and not confirm:
            raise Conflict("已收藏的音色不能直接删除；确认影响后请带确认标记重试")
        removed = describe_voice(key, data.pop(key))
        write_personas_atomic(data, pf)
    return removed


def import_voices(imported: dict, overwrite: bool = False,
                  personas_file: Optional[Path] = None) -> dict:
    """合并导入。默认跳过已存在的音色，不覆盖；overwrite 也不会覆盖已收藏音色。"""
    if not isinstance(imported, dict):
        raise VoiceLibraryError("导入文件必须是 JSON 对象")
    added, updated, skipped = [], [], []
    with personas_lock(personas_file) as pf:
        data = load_personas(pf)
        for k, v in imported.items():
            if k in data and (not overwrite or is_favorite(data[k])):
                skipped.append(k)
                continue
            (updated if k in data else added).append(k)
            data[k] = v
        if added or updated:
            write_personas_atomic(data, pf)
    return {"added": added, "updated": updated, "skipped": skipped, "total": len(data)}


def register_voice(key: str, audio_path: Path, ref_text: str, name: Optional[str] = None,
                   instruction: str = "", processor=None, data_dir: Optional[Path] = None) -> dict:
    """注册自己录制 / 导入的参考音频。重名在文件锁内判定，绝不覆盖已有音色。"""
    from core.utils import sanitize_path_component, upsert_persona_mapping
    data_dir = Path(data_dir or paths.DATA_DIR)
    display = (name or key).strip()
    safe_key = sanitize_path_component(key, fallback="unknown")
    if not display or not isinstance(ref_text, str) or not 1 <= len(ref_text.strip()) <= 1000:
        raise VoiceLibraryError("请填写音色名称与对应录音原文（1–1000 字）")
    if safe_key in load_personas(Path(data_dir) / "configs" / "personas.json"):
        raise Conflict("音色标识已存在，请使用新标识")
    if processor is None:
        from core.processor import AudioProcessor
        processor = AudioProcessor(str(data_dir))
    try:
        sample = processor.prepare_clone_reference(str(audio_path), ref_text)
    except ValueError as exc:
        raise VoiceLibraryError(str(exc)) from exc
    ref_rel = os.path.relpath(sample, data_dir).replace("\\", "/")
    try:
        upsert_persona_mapping(str(data_dir), persona_key=safe_key, persona_name=display,
                               ref_rel=ref_rel, ref_text=ref_text, instruction=instruction or "",
                               create_only=True)
    except FileExistsError as exc:
        Path(sample).unlink(missing_ok=True)
        raise Conflict(str(exc)) from exc
    except Exception:
        Path(sample).unlink(missing_ok=True)
        raise
    return {"key": safe_key, "name": display, "ref": ref_rel, "ref_text": ref_text.strip()}


# ── 生成库 ─────────────────────────────────────────────────────────

def voice_for_audio(filename: str, personas: dict) -> Optional[dict]:
    """生成文件关联的已入库音色。

    新记录按 source_filename 精确关联；旧版本入库的设计音色没有这个字段，
    只在文件名里的音色名与已注册音色 key 或名称**完全相同**时视为关联。
    """
    for k, v in personas.items():
        if isinstance(v, dict) and v.get("source_filename") == filename:
            return {"key": k, "favorite": is_favorite(v), "name": v.get("name", k)}
    m = _DESIGN_FILE_RE.match(filename)
    if not m:
        return None
    for k, v in personas.items():
        if isinstance(v, dict) and not v.get("source_filename") and m.group(1) in (k, v.get("name")):
            return {"key": k, "favorite": is_favorite(v), "name": v.get("name", k), "legacy": True}
    return None


def audio_kind(filename: str) -> str:
    for tag, kind in (("[设计]", "design"), ("[克隆]", "clone"), ("[对话]", "dialogue"), ("[试听]", "preview")):
        if filename.startswith(tag):
            return kind
    return "other"


def list_generated(out_dir: Optional[Path] = None, personas_file: Optional[Path] = None,
                   kinds: Optional[Iterable[str]] = None) -> list[dict]:
    out = _out_dir(out_dir)
    personas = load_personas(personas_file)
    kinds = set(kinds) if kinds else None
    files = []
    if out.exists():
        for f in sorted(out.iterdir(), key=lambda x: x.stat().st_mtime, reverse=True):
            if not f.is_file() or f.suffix.lower() not in AUDIO_EXTS:
                continue
            kind = audio_kind(f.name)
            if kinds and kind not in kinds:
                continue
            st = f.stat()
            sidecar = f.with_suffix(".json")
            ref_text = ""
            if sidecar.is_file():
                try:
                    ref_text = json.loads(sidecar.read_text(encoding="utf-8")).get("ref_text", "")
                except Exception:
                    ref_text = ""
            files.append({
                "filename": f.name,
                "path": str(f),
                "kind": kind,
                "size": st.st_size,
                "created": datetime.fromtimestamp(st.st_mtime).strftime("%Y-%m-%d %H:%M:%S"),
                "ref_text": ref_text,
                "voice": voice_for_audio(f.name, personas),
            })
    return files


def delete_generated(filename: str, out_dir: Optional[Path] = None,
                     personas_file: Optional[Path] = None, confirm: bool = False) -> dict:
    """删除生成库文件；关联音色已收藏时拒绝（除非调用方确认）。

    音色映射不动 —— 这里删的只是生成的音频文件，语义和 delete_voice 不同。
    """
    safe = os.path.basename(filename)
    path = _out_dir(out_dir) / safe
    with personas_lock(personas_file) as pf:
        if not path.is_file():
            raise NotFound(f"音频文件不存在: {safe}")
        voice = voice_for_audio(safe, load_personas(pf))
        if voice and voice["favorite"] and not confirm:
            raise Conflict("该生成文件关联的音色已收藏；确认影响后请带确认标记重试")
        path.unlink()
    return {"filename": safe, "voice": voice}


def save_design(filename: str, voice_name: str, instruction: str = "", ref_text: str = "",
                processor=None, data_dir: Optional[Path] = None,
                out_dir: Optional[Path] = None) -> dict:
    """把已生成的设计样音收藏进音色库（不重新生成，不改动原文件）。"""
    from core.utils import (resolve_design_voice_key, sanitize_path_component,
                            upsert_persona_mapping, write_generation_json)
    data_dir = Path(data_dir or paths.DATA_DIR)
    name = (voice_name or "").strip()
    if not name:
        raise VoiceLibraryError("voice_name 不能为空")
    src = _out_dir(out_dir) / os.path.basename(filename)
    if not src.is_file():
        raise NotFound(f"找不到音频：{filename}")
    ref_text = (ref_text or "").strip()
    sidecar = src.with_suffix(".json")
    if not ref_text and sidecar.is_file():
        ref_text = json.loads(sidecar.read_text(encoding="utf-8")).get("ref_text", "")
    voice_key = resolve_design_voice_key({"voice_name": name})
    if processor is None:
        from core.processor import AudioProcessor
        processor = AudioProcessor(str(data_dir))
    try:
        seed = processor.prepare_clone_reference(str(src), ref_text)
    except ValueError as exc:
        raise VoiceLibraryError(str(exc)) from exc
    try:
        upsert_persona_mapping(
            str(data_dir), persona_key=voice_key, persona_name=name,
            ref_rel=os.path.relpath(str(seed), str(data_dir)).replace("\\", "/"),
            ref_text=ref_text,
            design_rel=f"voice_designs/{sanitize_path_component(name, fallback='未命名音色')}.json",
            instruction=instruction or "", create_only=True,
            source_filename=src.name, favorite=True,
        )
    except FileExistsError as exc:
        Path(seed).unlink(missing_ok=True)
        raise Conflict(str(exc)) from exc
    except Exception:
        Path(seed).unlink(missing_ok=True)
        raise
    write_generation_json(str(data_dir), voice_key, source="voice_design")
    return {"persona_key": voice_key, "name": name, "source_filename": src.name}
