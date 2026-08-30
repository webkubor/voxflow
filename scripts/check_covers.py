#!/usr/bin/env python3
"""
检查/修复作品封面尺寸是否满足平台要求。

    .venv/bin/python scripts/check_covers.py                # 只报告
    .venv/bin/python scripts/check_covers.py --fix qishui   # 不够的放大到汽水要求
    .venv/bin/python scripts/check_covers.py --fix netease  # 不够的放大到网易云要求

## 为什么有这一步

平台对封面有硬性尺寸要求：汽水 ≥1440×1440、网易云 ≥1400×1400。
从网易云回填的 36 首用的原图是 800~1328 不等，全都不达标 —— 直接拿去
发汽水会被拒或压糊。发新平台前先跑一遍，把不达标的挑出来。

`--fix` 用 LANCZOS 放大到目标尺寸，写入 `publish/covers/`（不覆盖原图，
文件名带尺寸后缀），不改台账 —— 用不用、用哪张是发布时人的决定。
放大只是兜底：有中台重绘机会时优先重绘（`docs/TODO.md` #11），
放大是「原图本身没问题、只是小」的情况下的最小动作。

## 真源

平台要求以 configs/platforms.json 各平台的 cover.min_size 为准，
这里只放检查用的兜底值，两边不一致时改 platforms.json。
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

from PIL import Image

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import DATA_DIR, PUBLISH_DIR          # noqa: E402

# 平台 → 最小边长（1:1 方图）。真源是 configs/platforms.json 的 cover.min_size
MIN_SIZE = {"qishui": 1440, "netease": 1400}

FIX = "--fix" in sys.argv
_target_idx = sys.argv.index("--fix") + 1 if FIX else -1
TARGET = sys.argv[_target_idx] if FIX and len(sys.argv) > _target_idx else ""
if FIX and TARGET not in MIN_SIZE:
    print(f"✗ --fix 需要目标平台：{'/'.join(MIN_SIZE)}")
    raise SystemExit(1)


def main() -> None:
    db = sqlite3.connect(str(DATA_DIR / "voxflow.db"))
    rows = db.execute("SELECT id, title, cover_file FROM tracks WHERE cover_file != ''").fetchall()

    ok, small, missing = [], [], []
    for tid, title, cf in rows:
        p = DATA_DIR / cf
        if not p.exists():
            missing.append((title, cf))
            continue
        im = Image.open(p)
        w, h = im.size
        if min(w, h) >= MIN_SIZE[TARGET if FIX else "netease"]:
            ok.append((title, im.size))
        else:
            small.append((title, im.size, p))

    print(f"封面检查：达标 {len(ok)} · 不达标 {len(small)} · 文件缺失 {len(missing)}")
    for title, size in ok:
        print(f"  ✓ {title}  {size[0]}×{size[1]}")
    for title, size, _ in small:
        print(f"  ✗ {title}  {size[0]}×{size[1]}")
    for title, cf in missing:
        print(f"  ⚠ {title}  缺文件 {cf}")

    if not FIX:
        return

    # ── 放大修复 ──
    target = MIN_SIZE[TARGET]
    out_dir = PUBLISH_DIR / "covers"
    out_dir.mkdir(parents=True, exist_ok=True)
    fixed = 0
    for title, (w, h), p in small:
        # 保持比例放大到最小边达标；超出的裁成方图（平台要 1:1）
        scale = target / min(w, h)
        nw, nh = max(target, round(w * scale)), max(target, round(h * scale))
        im = Image.open(p).convert("RGB").resize((nw, nh), Image.LANCZOS)
        left, top = (nw - target) // 2, (nh - target) // 2
        im = im.crop((left, top, left + target, top + target))
        safe = "".join(c for c in title if c not in '/\\:*?"<>|').strip() or "untitled"
        dst = out_dir / f"{safe}_{target}.jpg"
        im.save(dst, "JPEG", quality=92)
        fixed += 1
        print(f"  → {dst.name}  ({target}×{target})")
    print(f"✓ 放大 {fixed} 张到 {target}×{target}，写入 {out_dir}")


if __name__ == "__main__":
    main()
