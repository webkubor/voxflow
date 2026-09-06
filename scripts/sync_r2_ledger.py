#!/usr/bin/env python3
"""
本地音频 → R2 → 回填台账的「音乐地址」。

    .venv/bin/python scripts/sync_r2_ledger.py [--dry-run]

## 为什么要单独一个脚本

生成流程本来是「出歌 → 自动传 R2 → 写台账」一条龙。但 Suno 现在**停供
音频直链**（API 和 CDN 都 403，带合法 JWT 也一样，是服务端策略不是鉴权），
voxflow 拿不到文件，那一环就断了。

所以现在是：人在 suno.com 手动下载 → 丢进 `~/.voxflow/out/music/` →
跑这个脚本，把后半段接上。等哪天音频能自动拿了，这个脚本就退化成补漏工具。

## 怎么把文件对上台账的行

按**文件名里的歌名**匹配台账的「曲名」或「发行歌名」。
匹配不上的会列出来让人看，**不猜** —— 猜错了会把 A 歌的链接填到 B 歌那行，
而那行看起来完全正常，等到有人点开下载才发现拿错了歌。
"""
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import notify, r2  # noqa: E402
from core.paths import MUSIC_DIR  # noqa: E402

DRY = "--dry-run" in sys.argv
AUDIO = {".mp3", ".wav", ".flac", ".m4a", ".aac", ".ogg"}


def song_name(p: Path) -> str:
    """从文件名里剥出歌名：去掉 [Suno] 前缀和 _时间戳 后缀。"""
    n = re.sub(r"^\[[^\]]+\]", "", p.stem)
    return re.sub(r"_\d{8}_\d{6}$", "", n).strip()


def txt(v):
    if isinstance(v, list) and v and isinstance(v[0], dict):
        return v[0].get("text", "")
    if isinstance(v, dict):
        return v.get("link") or v.get("text", "")
    return v or ""


def main() -> int:
    if not r2.enabled():
        print("❌ R2 没配置（~/.voxflow/configs/r2.json）")
        return 1
    acc = notify.account()
    base = acc.get("base") or {}
    if not base.get("app_token"):
        print("❌ 当前账户没配多维表格")
        return 1
    root = f"/open-apis/bitable/v1/apps/{base['app_token']}/tables/{base['table_id']}"

    recs = (notify._lark_json(acc, "GET", f"{root}/records",
                              params={"page_size": 500}).get("data") or {}).get("items", [])
    # 一个歌名可能对应多行（同名两首），所以存列表
    # ⚠️ 两个索引分开，**发行歌名优先**。
    #
    # 一次生成出的两首「曲名」是一样的（都叫破晓），只有「发行歌名」不同
    # （破晓 / 长风起）。混在一个索引里的话，`破晓.wav` 会抢到先出现的那行
    # —— 可能正是「长风起」那行。结果是两首歌的音频对调，而表面上毫无异常，
    # 等到有人点开下载才发现拿错了歌。
    by_release: dict[str, list] = {}
    by_title: dict[str, list] = {}
    for r in recs:
        rel = txt(r["fields"].get("发行歌名")).strip()
        tit = txt(r["fields"].get("曲名")).strip()
        if rel:
            by_release.setdefault(rel, []).append(r)
        if tit:
            by_title.setdefault(tit, []).append(r)

    raw = [p for p in Path(MUSIC_DIR).glob("*") if p.suffix.lower() in AUDIO]
    # ⚠️ 同一首歌常有 .mp3 和 .wav 两份，**它们是同一首的两种格式，不是两首**。
    # 不去重的话会各占一行 —— 而那两行其实是旋律不同的两个 clip，
    # 于是「长风起」那行被填上了「破晓」的音频，看起来还完全正常。
    # 按歌名分组，每首只取一个：优先 mp3（体积小、平台都收）。
    PREF = {".mp3": 0, ".m4a": 1, ".aac": 2, ".flac": 3, ".wav": 4, ".ogg": 5}
    grouped: dict[str, Path] = {}
    for p_ in raw:
        n = song_name(p_)
        cur = grouped.get(n)
        if cur is None or PREF.get(p_.suffix.lower(), 9) < PREF.get(cur.suffix.lower(), 9):
            grouped[n] = p_
    files = sorted(grouped.values())
    if len(raw) != len(files):
        print(f"（{len(raw)} 个文件里有同名不同格式的，按歌名去重后 {len(files)} 首）")
    print(f"本地音频 {len(files)} 首，台账 {len(recs)} 行\n")

    done = skipped = unmatched = 0
    for p in sorted(files):
        name = song_name(p)
        # 先按发行歌名精确命中；命中不了才退回曲名
        rows = by_release.get(name) or by_title.get(name) or []
        # 已经有音乐地址的行不重复占用
        free = [r for r in rows if not txt(r["fields"].get("音乐地址"))]
        if not rows:
            print(f"  ? {p.name}  —— 台账里没有叫「{name}」的行，跳过（不猜）")
            unmatched += 1
            continue
        if not free:
            print(f"  = {p.name}  —— 对应的行都已有地址，跳过")
            skipped += 1
            continue
        if DRY:
            print(f"  + {p.name}  → 「{name}」（{len(free)} 行待填，取第 1 行）")
            done += 1
            continue
        url = r2.upload(str(p))
        if not url:
            print(f"  ✗ {p.name}  —— 上传失败，看日志")
            continue
        row = free[0]
        res = notify._lark_json(acc, "POST", f"{root}/records/batch_update", {"records": [
            {"record_id": row["record_id"],
             "fields": {"音乐地址": {"link": url, "text": p.name}}}]})
        ok = res.get("ok")
        print(f"  {'✓' if ok else '✗'} {p.name}  → {url}")
        done += ok

    print(f"\n{'（预演）' if DRY else ''}处理 {done} · 跳过 {skipped} · 对不上 {unmatched}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
