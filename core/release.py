"""发行资产准备 —— 把曲库里的原始文件整成平台能收的样子。

抽出来是因为两个调用方要用同一套规则：
  · scripts/publish_qishui_ego.py（ego-browser 驱动的外部脚本）
  · web/app.py 的 /api/release/*（浏览器插件 voxflow-publisher 拉资产）

规则只有一条但很关键：**WAV 先转 320k MP3**。汽水解析大 WAV 极慢，会在解析到半截时
同时报「音频无效」和「非纯音乐请填歌词」两条错——后一条尤其误导，看着像检测到人声，
实际是文件根本没传完。29MB 的 wav 必踩，转 320k mp3（约 6MB）解决。
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from core.exe import find_exe


def _ffmpeg() -> str:
    """ffmpeg 的绝对路径。裸名字在非交互式 shell 里找不到（homebrew 不在最小 PATH）。"""
    return find_exe("ffmpeg") or "ffmpeg"


def to_mp3(audio: Path) -> Path:
    """WAV 转 320k MP3；已经是别的格式就原样返回。

    **转完必须确认文件真的在** —— 路径拼了 `.mp3` 后缀但文件没转出来时，
    平台报的同样是「音频无效」，从报错看不出是本地转码失败。
    """
    if audio.suffix.lower() != ".wav" or not audio.is_file():
        return audio
    mp3 = audio.with_suffix(".mp3")
    if not mp3.is_file() or mp3.stat().st_mtime < audio.stat().st_mtime:
        subprocess.run([_ffmpeg(), "-y", "-i", str(audio), "-b:a", "320k", str(mp3)],
                       check=True, capture_output=True)
    if not mp3.is_file():
        raise RuntimeError(f"转码后文件不存在：{mp3}")
    return mp3
