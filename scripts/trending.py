#!/usr/bin/env python3
"""
热点风格追踪 —— 「哪个音乐火，做哪个风格」，但不抄袭。

    .venv/bin/python scripts/trending.py                 # 只打印榜单前 30
    .venv/bin/python scripts/trending.py --analyze       # 榜单 + LLM 风格分析

## 数据通道

- 榜单：网易云热歌榜公开 API（`/api/v6/playlist/detail?id=3778678`），
  拿 200 首按热度排名的歌（榜单顺序即热度），再 `/api/song/detail` 补艺人。
  真数据，不是爬页面 —— 网易云页面有反爬字符插入（见 sync_netease.py）。
- 风格提炼：core/llm_client.analyze_trending —— LLM 从榜单歌曲里提炼
  风格共性，产出 Suno 可直接用的风格标签。

## 不抄袭的边界

风格提炼的 system prompt 里写死了红线：只谈流派/编曲/情绪/主题的共性，
禁止复述任何单首歌的旋律、歌词、编曲细节，禁止点名任何歌曲当模板。
产出的是「可以创作全新作品的方向」，不是「模仿对象清单」。
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

HOT_CHART_ID = 3778678            # 网易云热歌榜
TOP_N = 30


def fetch(url: str) -> dict:
    """网易云接口，带 Referer；TLS 偶发断连，重试 3 次（见 sync_lyrics.py）。"""
    last = None
    for attempt in range(3):
        try:
            req = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"})
            with urllib.request.urlopen(req, timeout=30) as r:
                return json.loads(r.read().decode())
        except Exception as e:                            # noqa: BLE001
            last = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"网易云请求失败（重试 3 次）: {last}")


def get_hot_songs(n: int = TOP_N) -> list[dict]:
    """热歌榜 → [{rank, name, artist}]，按热度顺序。"""
    pl = fetch(f"https://music.163.com/api/v6/playlist/detail?id={HOT_CHART_ID}")
    track_ids = [t["id"] for t in (pl.get("playlist") or {}).get("trackIds") or []][:n]
    if not track_ids:
        return []

    # 分批（song/detail 一次最多约 200 个 id）
    songs = []
    for i in range(0, len(track_ids), 100):
        chunk = track_ids[i:i + 100]
        detail = fetch("https://music.163.com/api/song/detail?ids=" +
                       "[" + ",".join(str(i) for i in chunk) + "]")
        for s in detail.get("songs") or []:
            songs.append({
                "rank": track_ids.index(s["id"]) + 1,
                "name": s.get("name", ""),
                "artist": "、".join(a["name"] for a in (s.get("artists") or [])[:3]),
            })
        time.sleep(0.3)
    return songs


def main() -> None:
    analyze = "--analyze" in sys.argv
    songs = get_hot_songs()
    if not songs:
        print("✗ 拿不到热歌榜")
        raise SystemExit(1)

    print(f"热歌榜 Top {len(songs)}（网易云 · {time.strftime('%Y-%m-%d')}）：")
    for s in songs[:15]:
        print(f"  {s['rank']:>3}. {s['name']} — {s['artist']}")

    if not analyze:
        return

    print("\n── 风格分析（不抄袭：只提炼共性，不复制任何作品）──\n")
    from core.llm_client import analyze_trending
    result = analyze_trending(songs)
    print("主线：", result.get("trend", ""))
    print("Suno 标签：", result.get("tags", ""))
    print("情绪：", " / ".join(result.get("moods", [])))
    print("主题：", " / ".join(result.get("themes", [])))


if __name__ == "__main__":
    main()
