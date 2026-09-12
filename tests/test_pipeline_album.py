#!/usr/bin/env python3
"""
本地草稿专辑 —— `.venv/bin/python tests/test_pipeline_album.py`

规则：发行前就能把几首歌组成一张辑；一首歌同时只能在一张辑里；曲序按加入顺序。
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


def rejects(name: str, fn, expect: str) -> None:
    try:
        fn()
    except ValueError as e:
        check(name, expect in str(e), f"报错了但不是预期那条：{e}")
        return
    raise AssertionError(f"✗ {name} —— 本该拒绝却放行了")


def main() -> int:
    db.init()
    for i in (1, 2, 3):
        P.upsert(f"t{i}", title=f"第{i}首", stage="selected")

    # 1. 建辑并带上曲目
    a = P.create_album("搞笑BGM合集", "qishui", ["t1", "t2"], description="短视频用")
    check("建辑成功", a["title"] == "搞笑BGM合集")
    check("草稿 album_id 带前缀", a["album_id"].startswith(P.DRAFT_ALBUM_PREFIX), a["album_id"])
    check("曲目进去了", [t["id"] for t in a["tracks"]] == ["t1", "t2"], str(a["tracks"]))
    check("曲序按加入顺序", [t["no"] for t in a["tracks"]] == [1, 2], str(a["tracks"]))
    check("track_count 对", a["track_count"] == 2, str(a["track_count"]))

    aid = a["album_id"]

    # 2. 追加
    a = P.add_to_album(aid, "qishui", ["t3"])
    check("追加排在末尾", [t["no"] for t in a["tracks"]] == [1, 2, 3], str(a["tracks"]))

    # 3. 一首歌不能同时在两张辑
    b = P.create_album("另一张", "qishui", [])
    rejects("跨辑被挡", lambda: P.add_to_album(b["album_id"], "qishui", ["t1"]), "已经在另一张专辑里")

    # 4. 同平台重名被挡
    rejects("专辑重名被挡", lambda: P.create_album("搞笑BGM合集", "qishui", []), "已经有一张")

    # 5. 空名被挡
    rejects("空专辑名被挡", lambda: P.create_album("  ", "qishui", []), "不能空")

    # 6. 移出
    a = P.remove_from_album(aid, "qishui", "t2")
    check("移出后只剩两首", [t["id"] for t in a["tracks"]] == ["t1", "t3"], str(a["tracks"]))
    check("移出后 track_count 同步", a["track_count"] == 2, str(a["track_count"]))

    # 7. 加进专辑不该把已备料的歌打回 draft
    P.submit_release("t1", "qishui", "第一首的发行名")
    before = P.get_track("t1")["platforms"]["qishui"]["status"]
    P.add_to_album(aid, "qishui", [])          # 无操作，只是确认不炸
    after = P.get_track("t1")["platforms"]["qishui"]["status"]
    check("状态不被专辑操作打回", before == after == "preparing", f"{before} → {after}")

    for n in PASSED:
        print(f"✓ {n}")
    print(f"\n{len(PASSED)} 项通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
