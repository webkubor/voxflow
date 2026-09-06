#!/usr/bin/env python3
"""
平台上架记录 ↔ Suno 原曲 —— `.venv/bin/python tests/test_pipeline_listings.py`

要锁住的性质：
1. 同一首原曲可以挂同一平台的多条记录（拆分）
2. 平台歌名可以跟本地 title 不同（改名）
3. 人手关联之后，song_id 还在，只是换了所属原曲
4. 重跑同步按 song_id 认领，不会把关联冲掉
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

    P.set_platform_status("suno-luoxue", "netease", "online",
                          song_id="111", platform_title="落雪")
    P.set_platform_status("suno-luoxue", "netease", "online",
                          song_id="222", platform_title="落雪（片段）")
    t = P.get_track("suno-luoxue")
    check("同一平台可以挂两条", len(t["listings"]) == 2, str(len(t["listings"])))
    titles = {l["platform_title"] for l in t["listings"]}
    check("拆分后的平台歌名都留下", titles == {"落雪", "落雪（片段）"}, str(titles))

    P.upsert("orphan-wind", title="逆风少年", stage="published", note="从网易云回填")
    P.set_platform_status("orphan-wind", "netease", "online",
                          song_id="333", platform_title="逆风少年")
    orphan = P.get_track("orphan-wind")
    lid = orphan["listings"][0]["id"]
    P.link_listing(lid, "suno-luoxue")
    check("关联后孤儿空壳被删", P.get_track("orphan-wind") is None)
    t2 = P.get_track("suno-luoxue")
    check("关联后原曲有 3 条上架记录", len(t2["listings"]) == 3, str(len(t2["listings"])))
    check("改名后的平台歌名还在",
          any(l["platform_title"] == "逆风少年" and l["song_id"] == "333" for l in t2["listings"]))

    hit = P.resolve_track_for_listing("netease", "333", "随便什么名字")
    check("重跑同步按 song_id 认领，不冲掉关联", hit == "suno-luoxue", str(hit))

    miss = P.resolve_track_for_listing("netease", "999", "落雪")
    check("新 song_id 同名会挂到带 clip 的原曲", miss == "suno-luoxue", str(miss))

    none = P.resolve_track_for_listing("netease", "888", "从未见过的歌")
    check("完全对不上返回 None，让调用方建孤儿", none is None)

    print(f"\n{len(PASSED)} 项通过")


if __name__ == "__main__":
    main()
