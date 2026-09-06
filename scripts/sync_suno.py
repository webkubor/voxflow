#!/usr/bin/env python3
"""
把 Suno 云端的生成记录同步进本地曲库。

    .venv/bin/python scripts/sync_suno.py [--dry-run]

## 为什么需要它

voxflow 的曲库原本只记**它自己发起的**那些生成。可 Suno 网页端出的歌、
早期用别的方式做的歌，云端都有、本地没有 —— 于是「我一共生成过多少首」
这个问题，本地库回答不了，只能翻网页端一页页数。

`suno list` 是**免费命令**（不消耗 credits，CLI 自己写明了），
所以这件事可以随时重跑，不用担心花钱。

## 只补不改

云端记录只用来**补齐本地没有的曲目**。本地已有的行一个字都不动 ——
本地那些字段（歌词、发布状态、平台链接、封面）是人和流水线攒出来的，
云端没有，覆盖过去等于把它们清空。

匹配用 clip id，不是标题：Suno 一次出两首**同名**歌，按标题匹配必然串行。
"""
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db  # noqa: E402
from core.paths import DATA_DIR  # noqa: E402

SUNO_BIN = os.path.expanduser("~/.cargo/bin/suno")
DRY = "--dry-run" in sys.argv


def fetch_all() -> list[dict]:
    """翻完所有分页。免费命令，可以放心翻到底。"""
    clips, cursor, pages = [], None, 0
    while True:
        cmd = [SUNO_BIN, "list", "--json"] + (["--cursor", cursor] if cursor else [])
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=60)
        try:
            data = json.loads(r.stdout or "{}").get("data") or {}
        except json.JSONDecodeError:
            print(f"❌ 第 {pages + 1} 页返回不是 JSON：{(r.stderr or r.stdout)[:200]}")
            break
        batch = data.get("clips") or []
        clips.extend(batch)
        pages += 1
        cursor = data.get("next_cursor")
        if not data.get("has_more") or not cursor or pages > 50:
            break
    print(f"云端拉到 {len(clips)} 首（{pages} 页）")
    return clips


def main() -> int:
    if not os.path.exists(SUNO_BIN):
        print(f"❌ 找不到 suno CLI：{SUNO_BIN}")
        return 1
    clips = fetch_all()
    if not clips:
        return 1

    db.init()
    with db.connect() as c:
        have = {r["clip_id"] for r in c.execute(
            "SELECT clip_id FROM tracks WHERE clip_id IS NOT NULL AND clip_id != ''")}
        titles = {r["title"] for r in c.execute("SELECT title FROM tracks")}

    added, skipped, timed = 0, 0, 0
    for cl in clips:
        cid = cl.get("id") or ""
        if not cid:
            continue
        meta = cl.get("metadata") or {}
        dur = meta.get("duration")
        seconds = None
        try:
            if dur:
                seconds = int(round(float(dur)))
        except (TypeError, ValueError):
            seconds = None
        if cid in have:
            # 已有曲目也回填时长 —— 匹配改名后的上架记录靠这个。
            if seconds and not DRY:
                with db.connect() as c:
                    cur = c.execute(
                        "UPDATE tracks SET duration=? WHERE clip_id=? AND (duration IS NULL OR duration=0)",
                        (seconds, cid))
                    timed += cur.rowcount
            # ── 同步标题改动 ──────────────────────────────────
            #
            # **标题的真源在 Suno**：人在网页端改了名，本地不跟着变的话，
            # 看板上就还是旧名字。2026-09-06 因此闹过一次 —— 用户在 Suno
            # 上把两首同名歌分别改成「长安月」和「灯火照关山」，本地却仍是
            # 两个「长安月」，看起来像去重没做，实际是从没更新过。
            #
            # 发行名（release_title）**不覆盖**：那是人在台账里定的发行身份，
            # 可能和 Suno 上不同（Suno 叫 demo_夜航、发行叫《夜航》）。
            # 只有当它原本就等于旧标题（说明是自动带出来的、没人改过）才跟着更新。
            title_now = (cl.get("title") or "").strip() or "未命名"
            with db.connect() as c:
                row = c.execute("SELECT title, release_title FROM tracks WHERE clip_id=? OR id=?",
                                (cid, cid)).fetchone()
                if row and (row["title"] or "") != title_now:
                    if DRY:
                        print(f"  ~ 改名 {row['title']} → {title_now}  ({cid[:8]})")
                    elif (row["release_title"] or "") in ("", row["title"] or ""):
                        c.execute("UPDATE tracks SET title=?, release_title=? WHERE clip_id=? OR id=?",
                                  (title_now, title_now, cid, cid))
                    else:
                        c.execute("UPDATE tracks SET title=? WHERE clip_id=? OR id=?",
                                  (title_now, cid, cid))
                    renamed += 1
            skipped += 1
            continue
        title = (cl.get("title") or "").strip() or "未命名"
        created = (cl.get("created_at") or "")[:19].replace("Z", "") or datetime.now().isoformat(timespec="seconds")
        note = "从 Suno 云端补录"
        if title in titles:
            # 同名不等于重复：Suno 一次出两首同名歌，两首都是真作品。
            # 但人看列表时会懵，所以标一下，别让人以为是重复数据。
            note += " · 与已有曲目同名（Suno 一次出两首，正常）"
        if DRY:
            print(f"  + {title}  {created}  {cl.get('model_name','')}  {seconds or '-'}s")
            added += 1
            continue
        with db.connect() as c:
            c.execute(
                """INSERT INTO tracks (id, title, stage, tags, clip_id, duration, note, created_at, updated_at)
                   VALUES (?,?,?,?,?,?,?,?,?)""",
                (cid, title, "generated", meta.get("tags", ""), cid, seconds, note, created, created),
            )
        added += 1

    print(f"{'（预演）' if DRY else ''}新增 {added} 首，已有 {skipped} 首，回填时长 {timed} 首，同步改名 {renamed} 首")
    if not DRY and added:
        print(f"库：{DATA_DIR / 'voxflow.db'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
