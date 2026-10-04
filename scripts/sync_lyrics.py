#!/usr/bin/env python3
"""
从网易云回填歌词到台账。

    .venv/bin/python scripts/sync_lyrics.py

## 为什么歌词要回填

台账里 37 首作品只有 1 首有歌词，其余 36 首是回填的只有标题和平台状态。
歌词是平台发布的必填项（汽水/网易云都要），存在台账里才能复用。

## 渠道

网易云公开接口 `/api/song/lyric`（带 Referer，跟 sync_netease.py 一样）。
曲目 id 从 track_platforms 表里取（netease 平台的 song_id）。

## 现实

实测 2026-08-31：33 首网易云作品全部返回空歌词 —— 它们是纯音乐/器乐作品，
平台本来就没有歌词。脚本仍保留：将来有歌词的歌（或新发带词作品）跑一遍就能补。

歌词存 LRC 格式（带时间戳）。导入时保留时间戳 —— 发布表单一般要纯文本，
需要时另转；但时间戳是原数据，丢了就没了。
"""

from __future__ import annotations

import json
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import pipeline as P                      # noqa: E402
from core import db                                  # noqa: E402

TIMESTAMP_RE = re.compile(r"^(\[\d+:\d+(\.\d+)?\])+")
# Suno 歌词自带的段落标记：[Verse 1] [Pre-Chorus] [Chorus] [Outro] [Bridge] …
# 2026-10-04 补：原先只剥时间码，这些会原样漏进发布表单。
SECTION_RE = re.compile(r"^\s*\[[^\]\d][^\]]*\]\s*")


def fetch_lyric(song_id: str) -> str:
    """网易云歌词接口。带 Referer 否则被当盗链拒掉。

    网易云 TLS 偶发断连（sync_netease.py 里封面下载也遇过），重试 3 次。
    """
    url = f"https://music.163.com/api/song/lyric?id={song_id}&lv=1&kv=1&tv=-1"
    for attempt in range(3):
        try:
            req = urllib.request.Request(
                url, headers={"User-Agent": "Mozilla/5.0", "Referer": "https://music.163.com/"})
            with urllib.request.urlopen(req, timeout=30) as r:
                data = json.loads(r.read().decode())
            if data.get("code") != 200:
                return ""
            return (data.get("lrc") or {}).get("lyric") or ""
        except Exception as e:                          # noqa: BLE001
            if attempt == 2:
                print(f"    ⚠ {song_id} 请求失败: {str(e)[:60]}")
            time.sleep(1.5 * (attempt + 1))
    return ""


def lyric_to_plain(lrc: str) -> str:
    """
    LRC / 带段落标记的原文 → 发布表单要的纯文本。

    要剥两类标记，少一类都会漏进表单：

    1. **时间戳** `[00:12.3]` —— LRC 的行内时间码
    2. **段落标记** `[Verse 1]` `[Chorus]` `[Pre-Chorus]` `[Outro]` ——
       Suno 出的词自带这些（存进台账的就是原文，见 `sync_suno.py:lyrics_from`）

    第 2 类是 2026-10-04 补的：原来的 `TIMESTAMP_RE` 只认数字时间码，
    `[Verse 1]` 不匹配，会**原样漏进发布表单**。纯音乐标记 `[Instrumental]`
    剥掉之后整行就空了，按空行处理。
    """
    lines = []
    for line in lrc.splitlines():
        if not line.strip():
            continue
        # 先时间戳，再段落标记 —— 顺序无所谓，两者互不重叠
        text = TIMESTAMP_RE.sub("", line)
        text = SECTION_RE.sub("", text).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def main() -> None:
    db.init()
    with db.connect() as c:
        rows = c.execute(
            "SELECT tp.track_id, t.title, tp.song_id FROM track_platforms tp "
            "JOIN tracks t ON t.id = tp.track_id "
            "WHERE tp.platform = 'netease' AND tp.song_id != '' "
            "AND (t.lyrics IS NULL OR t.lyrics = '')"
        ).fetchall()

    if not rows:
        print("没有需要补歌词的作品。")
        return

    got, empty = [], []
    for row in rows:
        title, song_id = row["title"], row["song_id"]
        lrc = fetch_lyric(song_id)
        if not lrc:
            empty.append((title, song_id))
            continue
        P.upsert(row["track_id"], lyrics=lyric_to_plain(lrc))
        got.append((title, len(lrc)))
        time.sleep(0.3)   # 别把公开接口打太狠

    print(f"✓ 回填 {len(got)} 首：")
    for title, n in got:
        print(f"    {title}  {n} 字")
    print(f"\n✗ 无歌词 {len(empty)} 首（纯音乐或平台没传）：")
    for title, sid in empty:
        print(f"    {title}  (song_id={sid})")


if __name__ == "__main__":
    main()
