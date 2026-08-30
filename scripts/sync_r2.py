#!/usr/bin/env python3
"""
把本地有音频的作品同步到 R2 music 桶，位置写回台账。

    .venv/bin/python scripts/sync_r2.py [--dry-run] [--public]

## 同步什么

对每首**本地有音频**的作品，上传到 `masters/<year>/<slug>/`：

    masters/<year>/<slug>/master.wav   母带（优先取 audio_file 同目录的 .wav，
                                        那是 Suno 原始输出；只有 .mp3 就用它）
    masters/<year>/<slug>/cover.jpg    封面（有就传，保留原扩展名）
    masters/<year>/<slug>/meta.json    元数据（版权链凭证，格式对齐 R2 里
                                        已有的 jiang-yue-wu-sheng 条目）

`--public` 额外镜像一份到 `public/<slug>.<ext>`（对外播放版，官网外链用）。
默认不传 —— 母带目录是备份真源，public 需要时随时可从母带重建。

没有本地音频的作品跳过（那些只有平台回填的标题/封面，等 #5 判断过哪些老
作品还需要本地音频再说）。

## 位置写回台账

上传成功的作品，`cloud_backup` 写成：

    { "status": "backed_up",
      "location": "masters/2026/<slug>",        # R2 key 前缀
      "updated_at": "2026-08-31T00:00:00" }

失败重试 3 次后仍失败 → status "failed"。幂等：key 固定，重跑覆盖不重复。

## 凭证

- `CF_API_TOKEN` 环境变量优先；否则调 `cs kyvault get secret://cloudflare/api-token`
- `CF_ACCOUNT_ID` 环境变量优先；默认 webkubor 主账号
- 走 Cloudflare API 的 PUT（cs 内部同款通道），不用 S3 SigV4。
  桶名 `music`，公开域名 music.webkubor.online —— 见
  CortexOS/docs/rules/r2-assets.md（R2 位置与分类的唯一真源）。
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import pipeline as P                      # noqa: E402
from core.paths import DATA_DIR                     # noqa: E402

BUCKET = "music"
CDN = "https://music.webkubor.online"
ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "916ebb1b9f240bf4c8826021dd161692")

CONTENT_TYPES = {
    ".wav": "audio/wav",
    ".mp3": "audio/mpeg",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".png": "image/png",
    ".json": "application/json",
}


def api_token() -> str:
    """CF_API_TOKEN 环境变量优先，否则从 kyvault 取（取最后一行，排除多余输出）。"""
    env = os.environ.get("CF_API_TOKEN")
    if env:
        return env.strip()
    cs = os.environ.get("CORTEXOS_ROOT", str(Path.home() / "dev/gitlab/webkubor/CortexOS")) + "/bin/cs"
    out = subprocess.run([cs, "kyvault", "get", "secret://cloudflare/api-token"],
                         capture_output=True, text=True, check=True)
    token = out.stdout.strip().splitlines()[-1].strip()
    if not token:
        raise SystemExit("✗ 拿不到 CF API Token（kyvault 输出为空）")
    return token


def put_object(token: str, key: str, data: bytes, content_type: str) -> None:
    """上传一个对象到 music 桶。失败重试 3 次（R2 偶发 5xx，重试就好）。"""
    url = (f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}"
           f"/r2/buckets/{BUCKET}/objects/{key}")
    req = urllib.request.Request(url, data=data, method="PUT", headers={
        "Authorization": "Bearer " + token,
        "Content-Type": content_type,
    })
    last_err: Exception | None = None
    for attempt in range(3):
        try:
            with urllib.request.urlopen(req, timeout=120) as r:
                body = r.read()
            if r.status >= 300:
                raise RuntimeError(f"HTTP {r.status}: {body[:200]}")
            return
        except (urllib.error.URLError, RuntimeError, OSError) as e:
            last_err = e
            if attempt < 2:
                time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"重试 3 次仍失败: {last_err}")


def slug_of(track: dict) -> str:
    """kebab-case slug，优先用现成 ASCII 的 track id（nifeng-paoqilai 这种）。"""
    tid = track["id"]
    if re.fullmatch(r"[a-z0-9]+(-[a-z0-9]+)*", tid):
        return tid
    # 中文 id：有 pypinyin 就拼音化；没有就退回哈希名（极少见，只影响没音频的歌）
    try:
        from pypinyin import lazy_pinyin                      # type: ignore
        raw = "-".join(lazy_pinyin(track["title"]))
    except ImportError:
        raw = ""
    slug = re.sub(r"[^a-z0-9]+", "-", raw).strip("-").lower()
    if not slug:
        import hashlib
        slug = "track-" + hashlib.sha1(tid.encode()).hexdigest()[:8]
    return slug


def meta_json(track: dict, slug: str, platforms: dict, generated_at: str) -> dict:
    """meta.json —— 格式对齐 R2 里已有的 jiang-yue-wu-sheng 条目。"""
    published: dict = {}
    for plat, info in platforms.items():
        status = info.get("status") or ""
        url = info.get("song_url") or ""
        if status == "online" and url:
            published[plat] = url
        elif status:
            published[plat] = status
    return {
        "title": track["title"],
        "slug": slug,
        "model": "suno" if track.get("clip_id") or track.get("clip_ids") else "tts",
        "generated_at": generated_at,
        "suno_plan_at_generation": "⏳待核实（商用权凭证，上架前必填）",
        "published": published,
    }


def main() -> None:
    dry = "--dry-run" in sys.argv
    with_public = "--public" in sys.argv
    token = "" if dry else api_token()

    tracks = P.list_tracks()
    print(f"台账共 {len(tracks)} 首，开始扫描本地音频……\n")

    uploaded, skipped, failed = [], [], []
    for t in tracks:
        audio_rel = t.get("audio_file") or ""
        if not audio_rel:
            skipped.append((t["title"], "无本地音频（平台回填，等 #5）"))
            continue
        audio = DATA_DIR / audio_rel
        if not audio.exists():
            failed.append((t["title"], f"audio_file 指向的文件不存在: {audio_rel}"))
            continue

        # 母带优先取同目录 .wav（Suno 原始输出），只有 mp3 就用它
        wav = audio.with_suffix(".wav")
        master = wav if wav.exists() else audio
        slug = slug_of(t)
        # list_tracks() 不带 created_at，用文件 mtime 兜底取年份/日期
        created = (t.get("created_at") or "")[:10]
        if not created:
            created = time.strftime("%Y-%m-%d", time.localtime(master.stat().st_mtime))
        year = created[:4]
        prefix = f"masters/{year}/{slug}"
        key_master = f"{prefix}/master{master.suffix}"
        key_cover = f"{prefix}/cover{Path(t['cover_file']).suffix}" if t.get("cover_file") else ""
        key_meta = f"{prefix}/meta.json"

        print(f"▶ {t['title']}  →  {prefix}/")
        print(f"    母带 {master.name}（{master.stat().st_size / 1e6:.1f} MB）")

        if dry:
            print("    [dry-run] 不上传\n")
            uploaded.append(t["title"])
            continue

        try:
            put_object(token, key_master, master.read_bytes(), CONTENT_TYPES[master.suffix])
            if key_cover:
                cover = DATA_DIR / t["cover_file"]
                if cover.exists():
                    put_object(token, key_cover, cover.read_bytes(),
                               CONTENT_TYPES.get(cover.suffix, "application/octet-stream"))
                    print(f"    封面 {cover.name} → {key_cover}")
            put_object(token, key_meta,
                       json.dumps(meta_json(t, slug, t.get("platforms") or {}, created),
                                  ensure_ascii=False, indent=2).encode(),
                       "application/json")
            if with_public:
                key_public = f"public/{slug}{master.suffix}"
                put_object(token, key_public, master.read_bytes(), CONTENT_TYPES[master.suffix])
                print(f"    public 副本 → {key_public}")
        except Exception as e:                              # noqa: BLE001
            P.upsert(t["id"], cloud_backup={"status": "failed",
                                            "location": prefix,
                                            "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
            failed.append((t["title"], str(e)[:120]))
            print(f"    ✗ 上传失败: {str(e)[:120]}\n")
            continue

        P.upsert(t["id"], cloud_backup={"status": "backed_up",
                                        "location": prefix,
                                        "updated_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
        uploaded.append(t["title"])
        print(f"    ✓ 已备份，回写 cloud_backup（{CDN}/{key_master}）\n")

    print("─" * 60)
    print(f"已同步 {len(uploaded)} 首")
    if skipped:
        print(f"跳过 {len(skipped)} 首（无本地音频）：")
        for title, why in skipped:
            print(f"    {title} —— {why}")
    if failed:
        print(f"失败 {len(failed)} 首：")
        for title, why in failed:
            print(f"    {title} —— {why}")


if __name__ == "__main__":
    main()
