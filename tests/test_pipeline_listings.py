#!/usr/bin/env python3
"""
平台上架记录 ↔ Suno 原曲 —— `.venv/bin/python tests/test_pipeline_listings.py`

要锁住的性质：
1. 同一发行歌名可以出现在多个平台（汽水分发），但必须挂同一首原曲
2. 人手关联之后，song_id 还在
3. 重跑同步按 song_id 认领，不会把关联冲掉
4. 同一平台不能给一首再挂第二条（独家）
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="voxflow_test_")
os.environ["VOXFLOW_HOME"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db, pipeline as P  # noqa: E402

PASSED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        raise AssertionError(f"✗ {name}" + (f" —— {detail}" if detail else ""))
    PASSED.append(name)


def main() -> None:
    db.init()
    P.upsert("suno-luoxue", title="落雪", stage="generated",
             clip_id="clip-luoxue", audio_file="out/music/luoxue.mp3")
    P.submit_release("suno-luoxue", "qishui", "落雪")

    P.set_platform_status("suno-luoxue", "netease", "online",
                          song_id="111", platform_title="落雪")
    t = P.get_track("suno-luoxue")
    plats = {l["platform"] for l in t["listings"]}
    check("同名分发可以挂到第二个平台", plats == {"qishui", "netease"}, str(plats))

    P.upsert("orphan-same", title="落雪", stage="published", note="从网易云回填")
    P.set_platform_status("orphan-same", "tencent", "online",
                          song_id="333", platform_title="落雪")
    lid = P.get_track("orphan-same")["listings"][0]["id"]
    P.link_listing(lid, "suno-luoxue")
    check("同名分发关联后孤儿空壳被删", P.get_track("orphan-same") is None)
    t2 = P.get_track("suno-luoxue")
    check("关联后原曲有 3 条上架记录", len(t2["listings"]) == 3, str(len(t2["listings"])))

    P.upsert("orphan-diff", title="逆风少年", stage="published", note="从网易云回填")
    P.set_platform_status("orphan-diff", "netease", "online",
                          song_id="444", platform_title="逆风少年")
    lid2 = P.get_track("orphan-diff")["listings"][0]["id"]
    try:
        P.link_listing(lid2, "suno-luoxue")
        check("不同发行歌名不能挂到已定名的原曲", False)
    except ValueError as e:
        check("不同发行歌名不能挂到已定名的原曲",
              "统一" in str(e) or "独家" in str(e), str(e))

    hit = P.resolve_track_for_listing("tencent", "333", "随便什么名字")
    check("重跑同步按 song_id 认领，不冲掉关联", hit == "suno-luoxue", str(hit))

    by_release = P.resolve_track_for_listing("netease", "999", "落雪")
    check("按发行歌名能找到原曲", by_release == "suno-luoxue", str(by_release))

    none = P.resolve_track_for_listing("netease", "888", "从未见过的歌")
    check("完全对不上返回 None，让调用方建孤儿", none is None)

    print(f"\n{len(PASSED)} 项通过")


if __name__ == "__main__":
    main()
