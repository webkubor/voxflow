#!/usr/bin/env python3
"""
热点风格追踪 —— 「哪个音乐火，做哪个风格」，但不抄袭。

    .venv/bin/python scripts/trending.py                 # 合并热度榜 Top
    .venv/bin/python scripts/trending.py --analyze       # 榜单 + LLM 风格分析

## 数据通道（多平台交叉验证）

- 网易云热歌榜：`/api/v6/playlist/detail?id=3778678`（200 首按热度排），
  `/api/song/detail` 补艺人。真数据，不是爬页面（页面有反爬字符插入）。
- QQ 音乐热歌榜：`musicu.fcg` 的 `musicToplist.ToplistInfoServer/GetDetail`
  （topId=26）。两榜的歌高度重叠 —— 同一首歌两边都火，趋势更可信。

## 合并与热度打分

同一首歌按「歌名 + 艺人」合并（歌名去掉括号注释后匹配，艺人首名匹配）。
每首歌热度分：

    score = (100 - 网易云排名) + (100 - QQ 排名)     # 双榜自然更高分

双榜都进前 30 的歌热度最高 —— 这正是「交叉验证」的意义：
单榜可能是平台算法偏差，双榜同火才是真趋势。

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
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

NCM_HOT_CHART_ID = 3778678       # 网易云热歌榜
QQ_TOP_ID = 26                   # QQ 音乐热歌榜
TOP_N = 30


def fetch(url: str) -> dict:
    """带 Referer 抓 JSON；TLS 偶发断连，重试 3 次（见 sync_lyrics.py）。"""
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
    raise RuntimeError(f"请求失败（重试 3 次）: {last}")


def _norm_name(name: str) -> str:
    """归一化歌名用于跨榜匹配：去掉括号注释（live 版/伴奏/括号标注）。"""
    return re.sub(r"[（(].*?[)）]|\s+", "", name or "").strip().lower()


def _first_artist(song: dict) -> str:
    artists = song.get("artists") or song.get("singer") or []
    if not artists:
        return ""
    first = artists[0]
    return first.get("name", "") if isinstance(first, dict) else str(first)


# ── 网易云 ────────────────────────────────────────────────

def _ncm_songs(n: int = TOP_N) -> list[dict]:
    pl = fetch(f"https://music.163.com/api/v6/playlist/detail?id={NCM_HOT_CHART_ID}")
    track_ids = [t["id"] for t in (pl.get("playlist") or {}).get("trackIds") or []][:n]
    if not track_ids:
        return []
    out = []
    for i in range(0, len(track_ids), 100):
        chunk = track_ids[i:i + 100]
        detail = fetch("https://music.163.com/api/song/detail?ids=" +
                       "[" + ",".join(str(x) for x in chunk) + "]")
        for s in detail.get("songs") or []:
            out.append({
                "rank": track_ids.index(s["id"]) + 1,
                "name": s.get("name", ""),
                "artist": "、".join(a["name"] for a in (s.get("artists") or [])[:3]),
                "artists": [a["name"] for a in (s.get("artists") or [])[:3]],
            })
        time.sleep(0.3)
    return out


# ── QQ 音乐 ───────────────────────────────────────────────

def _qq_songs(n: int = TOP_N) -> list[dict]:
    payload = {"comm": {"ct": 24}, "toplist": {
        "module": "musicToplist.ToplistInfoServer", "method": "GetDetail",
        "param": {"topId": QQ_TOP_ID, "offset": 0, "num": n}}}
    data = urllib.parse.quote(json.dumps(payload, ensure_ascii=False), safe="")
    resp = fetch(f"https://u.y.qq.com/cgi-bin/musicu.fcg?format=json&data={data}")
    songs = resp.get("toplist", {}).get("data", {}).get("songInfoList") or []
    out = []
    for i, s in enumerate(songs):
        si = s.get("songInfo") or s
        out.append({
            "rank": i + 1,
            "name": si.get("name", ""),
            "artist": "、".join(a.get("name", "") for a in (si.get("singer") or [])[:3]),
            "artists": [a.get("name", "") for a in (si.get("singer") or [])[:3]],
        })
    return out


# ── 合并打分 ──────────────────────────────────────────────

def get_hot_songs(n: int = TOP_N) -> list[dict]:
    """网易云 + QQ 双榜合并去重，按热度分排序。

    返回 [{rank, name, artist, score, platforms}], rank 是合并后的名次。
    """
    ncm, qq = _ncm_songs(n), _qq_songs(n)
    merged: dict[str, dict] = {}

    def add(song: dict, platform: str) -> None:
        key = (_norm_name(song["name"]), _first_artist(song))
        if not key[0]:
            return
        item = merged.setdefault(key, {
            "name": song["name"], "artist": song["artist"],
            "score": 0, "platforms": [], "ranks": {},
        })
        score = max(0, 100 - song["rank"]) * 2   # 单榜满分 200
        item["score"] += score
        item["platforms"].append(platform)
        item["ranks"][platform] = song["rank"]

    for s in ncm:
        add(s, "netease")
    for s in qq:
        add(s, "qq")

    ranked = sorted(merged.values(), key=lambda x: x["score"], reverse=True)[:n]
    for i, item in enumerate(ranked):
        item["rank"] = i + 1
    return ranked


def main() -> None:
    analyze = "--analyze" in sys.argv
    songs = get_hot_songs()
    if not songs:
        print("✗ 拿不到热歌榜")
        raise SystemExit(1)

    print(f"合并热度榜 Top {len(songs)}（网易云+QQ · {time.strftime('%Y-%m-%d')}）：")
    for s in songs[:15]:
        tag = " 🔥双榜" if len(s["platforms"]) > 1 else ""
        print(f"  {s['rank']:>3}. {s['name']} — {s['artist']}  [{s['score']}]{tag}")

    if not analyze:
        return

    print("\n── 风格分析（不抄袭：只提炼共性，不复制任何作品）──\n")
    from core.llm_client import analyze_trending
    result = analyze_trending(songs)
    print("主线：", result.get("trend", ""))
    print("Suno 标签：", result.get("tags", ""))
    print("情绪：", " / ".join(result.get("moods", [])))
    print("主题：", " / ".join(result.get("themes", [])))
    if result.get("hotness") is not None:
        print("值得做程度：", result.get("hotness"), "——", result.get("hotness_reason", ""))


if __name__ == "__main__":
    main()
