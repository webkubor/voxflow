"""
推歌宣推引擎 —— 接入 reel-kit 自动化合成 1080×1920 竖版宣推短视频。

支持从曲库 Track 资产直连：
- 音频 (320k MP3) -> --bgm
- 歌词 (智能精选高潮句) -> --caps
- 官方 1440 封面 -> --assets
- 歌名 / 歌手 -> --title / --subtitle
- 平台搜索指引 -> --footer
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Optional

from core.paths import DATA_DIR, PROMO_DIR, ensure_dirs
from core import pipeline as P

REEL_CANDIDATES = [
    shutil.which("reel"),
    str(Path.home() / ".local/share/mise/shims/reel"),
    str(Path.home() / ".nvm/versions/node/current/bin/reel"),
    "/usr/local/bin/reel",
    "/opt/homebrew/bin/reel",
]


def find_reel_bin() -> Optional[str]:
    """定位本机 reel CLI 可执行文件。"""
    for cand in REEL_CANDIDATES:
        if cand and os.path.isfile(cand) and os.access(cand, os.X_OK):
            return cand
    return shutil.which("reel")


def check_promo_status() -> dict[str, Any]:
    """检查推歌环境就绪状态（reel-kit 安装与可用模板）。"""
    reel_bin = find_reel_bin()
    if not reel_bin:
        return {"available": False, "binary": None, "templates": [], "error": "未检测到 reel CLI，请运行 npm i -g @kubor/reel-kit"}

    try:
        proc = subprocess.run([reel_bin, "templates"], capture_output=True, text=True, timeout=5)
        lines = [l.strip() for l in proc.stdout.splitlines() if l.strip() and not l.startswith("可用模板")]
        return {
            "available": True,
            "binary": reel_bin,
            "templates": lines,
            "has_music_card": "music-card" in lines,
        }
    except Exception as e:
        return {"available": False, "binary": reel_bin, "templates": [], "error": str(e)}


def clean_lyrics_for_promo(lyrics: str, max_lines: int = 8) -> list[str]:
    """从整首歌词中筛选 6~8 句适合短视频展示的高潮/核心段落。"""
    if not lyrics:
        return ["新歌上线 全网首发", "戴上耳机 沉浸聆听", "前往各大音乐平台", "搜索曲目 立即收听"]

    raw_lines = lyrics.splitlines()
    parsed_lines: list[tuple[str, str]] = []  # (tag, text)
    current_tag = "verse"

    for line in raw_lines:
        line_s = line.strip()
        if not line_s:
            continue
        # 检测段落标签如 [Chorus], [Verse 1], [副歌] 等
        tag_match = re.match(r"^\[(.*?)\]", line_s)
        if tag_match:
            current_tag = tag_match.group(1).lower()
            remainder = line_s[tag_match.end():].strip()
            if remainder:
                parsed_lines.append((current_tag, remainder))
            continue
        if line_s.startswith("(") and line_s.endswith(")"):
            continue
        parsed_lines.append((current_tag, line_s))

    # 优先抽取 Chorus / 副歌
    chorus_lines = [text for tag, text in parsed_lines if "chorus" in tag or "副歌" in tag]
    if len(chorus_lines) >= 4:
        return chorus_lines[:max_lines]

    # 若无明确标签，取整首歌中前部最具张力的 6~8 行
    all_clean = [text for _, text in parsed_lines if len(text) >= 2]
    if not all_clean:
        return [
            "纯音乐新发 · 沉浸声流",
            "闭上双眼 · 随旋律自由共振",
            "心跳与音符交织的瞬间",
            "汽水音乐 · 独家首发收听",
        ]
    if len(all_clean) <= max_lines:
        return all_clean

    start_idx = 4 if len(all_clean) >= 12 else 0
    return all_clean[start_idx : start_idx + max_lines]


def _resolve_path(p: str | Path) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = DATA_DIR / path
    return path


def generate_promo_video(
    track_id: str,
    template: str = "music-card",
    per_shot: float = 2.8,
    accent1: str = "#ec4899",
    accent2: str = "#6366f1",
    footer: str = "",
    custom_caps: Optional[list[str]] = None,
) -> dict[str, Any]:
    """
    为指定 Track 生成竖版推歌短视频。
    """
    ensure_dirs()
    PROMO_DIR.mkdir(parents=True, exist_ok=True)

    reel_bin = find_reel_bin()
    if not reel_bin:
        raise RuntimeError("未找到 reel CLI，请确保 @kubor/reel-kit 已正确安装并在 PATH 中。")

    track = P.get_track(track_id)
    if not track:
        raise ValueError(f"台账中未找到曲目: {track_id}")

    title = track.get("release_title") or track.get("title") or "新歌"
    artist = track.get("artist") or "月栖洲"
    subtitle = f"演唱 / 词曲：{artist}"
    if not footer:
        footer = f"汽水音乐 / 抖音 搜索《{title}》全曲收听"

    # 1. 解析音频（优先 MP3，若只有 WAV 自动转码 320k MP3）
    audio_path = _resolve_path(track.get("audio_file") or "")
    if not audio_path.exists():
        raise FileNotFoundError(f"曲目音频文件不存在: {audio_path}")

    if audio_path.suffix.lower() == ".wav":
        mp3_cand = audio_path.with_suffix(".mp3")
        if not mp3_cand.exists() or mp3_cand.stat().st_mtime < audio_path.stat().st_mtime:
            subprocess.run(
                ["ffmpeg", "-y", "-i", str(audio_path), "-b:a", "320k", str(mp3_cand)],
                check=True,
                capture_output=True,
            )
        audio_path = mp3_cand

    # 2. 解析封面
    cover_path = _resolve_path(track.get("cover_file") or "")
    if not cover_path.exists():
        raise FileNotFoundError(f"曲目封面文件不存在: {cover_path}")

    # 3. 解析文案
    if custom_caps and len(custom_caps) > 0:
        caps = [c.strip() for c in custom_caps if c.strip()]
    else:
        caps = clean_lyrics_for_promo(track.get("lyrics", ""))

    safe_title = re.sub(r'[^\w\s\-_一-龥]', '', title).strip().replace(' ', '_')
    timestamp = int(time.time())
    caps_file = PROMO_DIR / f"{track_id[:8]}_{safe_title}_caps.txt"
    caps_file.write_text("\n".join(caps), encoding="utf-8")

    out_file = PROMO_DIR / f"{safe_title}_promo_{timestamp}.mp4"

    # 4. 组装 reel make 命令
    cmd = [
        reel_bin,
        "make",
        "--template",
        template,
        "--title",
        title,
        "--subtitle",
        subtitle,
        "--footer",
        footer,
        "--assets",
        str(cover_path),
        "--caps",
        str(caps_file),
        "--bgm",
        str(audio_path),
        "--per-shot",
        str(per_shot),
        "--accent1",
        accent1,
        "--accent2",
        accent2,
        "--out",
        str(out_file),
    ]

    proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if proc.returncode != 0:
        raise RuntimeError(f"reel make 合成失败 (exit {proc.returncode}):\nSTDOUT: {proc.stdout}\nSTDERR: {proc.stderr}")

    # 5. 探查输出视频信息
    duration = round(len(caps) * per_shot, 1)
    file_size = out_file.stat().st_size if out_file.exists() else 0

    return {
        "track_id": track_id,
        "title": title,
        "video_path": str(out_file),
        "filename": out_file.name,
        "duration": duration,
        "shots_count": len(caps),
        "file_size": file_size,
        "template": template,
        "caps": caps,
        "created_at": timestamp,
    }


def list_promo_videos() -> list[dict[str, Any]]:
    """列出所有已生成的宣推短视频。"""
    ensure_dirs()
    if not PROMO_DIR.exists():
        return []

    results = []
    for f in sorted(PROMO_DIR.glob("*_promo_*.mp4"), key=lambda x: x.stat().st_mtime, reverse=True):
        stat = f.stat()
        results.append({
            "filename": f.name,
            "path": str(f),
            "size": stat.st_size,
            "mtime": int(stat.st_mtime),
            "size_mb": round(stat.st_size / (1024 * 1024), 2),
        })
    return results
