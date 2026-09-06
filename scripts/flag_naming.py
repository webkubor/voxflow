#!/usr/bin/env python3
"""
标出「需要你定名」的行。

    .venv/bin/python scripts/flag_naming.py [--dry-run]

## 为什么需要它

Suno 一次生成出两首，**标题一模一样**，只有旋律不同。它们是两个独立作品，
各自上架、各自分成 —— 所以必须各有各的发行名。

但这件事系统此前从不提醒：两行躺在台账里都叫「破晓」，看起来很正常，
直到上架时才发现平台不接受同名，或者更糟 —— 发出去了，两首歌在平台上
互相抢自己的搜索位。

**名字只能由听过的人定。** 机器听不出「这首更燃、那首更沉」，
所以这里只负责**把该定名的行标出来**，不代填。

（2026-09-06 我替用户填过「破晓·贰」这种从属名，被指出是错的：
两首旋律不同、是独立作品，挂个「贰」等于告诉平台这是重复内容。）
"""
import sys
from collections import defaultdict
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import notify  # noqa: E402

DRY = "--dry-run" in sys.argv
FLAG = "⚠️ 与另一首同名，需各自定发行名"


def txt(v):
    if isinstance(v, list) and v and isinstance(v[0], dict):
        return v[0].get("text", "")
    if isinstance(v, dict):
        return v.get("link") or v.get("text", "")
    return v or ""


def main() -> int:
    acc = notify.account()
    base = acc.get("base") or {}
    if not base.get("app_token"):
        print("❌ 当前账户没配多维表格")
        return 1
    root = f"/open-apis/bitable/v1/apps/{base['app_token']}/tables/{base['table_id']}"
    recs = (notify._lark_json(acc, "GET", f"{root}/records",
                              params={"page_size": 500}).get("data") or {}).get("items", [])

    by_title = defaultdict(list)
    for r in recs:
        t = txt(r["fields"].get("曲名")).strip()
        if t:
            by_title[t].append(r)

    ups, clean = [], []
    for title, rows in by_title.items():
        if len(rows) < 2:
            continue
        releases = [txt(r["fields"].get("发行歌名")).strip() for r in rows]
        # 需要定名的条件：有人没填，或者填了但彼此相同
        needs = any(not x for x in releases) or len(set(filter(None, releases))) < len(releases)
        for r, rel in zip(rows, releases):
            note = txt(r["fields"].get("备注"))
            has = FLAG in note
            if needs and not has:
                ups.append({"record_id": r["record_id"],
                            "fields": {"备注": (FLAG + " · " + note).strip(" ·")}})
            elif not needs and has:
                # 已经各自定好名了，把提示撤掉 —— 留着的提示会变成噪音
                clean.append({"record_id": r["record_id"],
                              "fields": {"备注": note.replace(FLAG, "").strip(" ·")}})
        mark = "需定名" if needs else "已各自定名"
        print(f"  「{title}」×{len(rows)} → {mark}：{' / '.join(x or '(空)' for x in releases)}")

    todo = ups + clean
    if not todo:
        print("\n没有需要改的")
        return 0
    if DRY:
        print(f"\n（预演）加提示 {len(ups)} 行 · 撤提示 {len(clean)} 行")
        return 0
    res = notify._lark_json(acc, "POST", f"{root}/records/batch_update", {"records": todo})
    print(f"\n加提示 {len(ups)} · 撤提示 {len(clean)}:",
          "✓" if res.get("ok") else str(res.get("error"))[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
