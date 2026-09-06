#!/usr/bin/env python3
"""
独家授权 + 发行歌名唯一 —— `.venv/bin/python tests/test_pipeline_exclusive.py`
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
    P.upsert("clip-a", title="落雪", stage="selected", clip_id="aaa")
    P.upsert("clip-b", title="落雪", stage="selected", clip_id="bbb")
    check("生成歌名可以重复", P.get_track("clip-a")["title"] == P.get_track("clip-b")["title"])

    P.submit_release("clip-a", "qishui", "落雪")
    a = P.get_track("clip-a")
    check("发行后记下独家平台", a["release_platform"] == "qishui")
    check("发行歌名独立于生成名", a["release_title"] == "落雪")

    try:
        P.submit_release("clip-a", "netease", "落雪")
        check("独家不能再投第二个平台", False)
    except ValueError as e:
        check("独家不能再投第二个平台", "独家" in str(e), str(e))

    try:
        P.submit_release("clip-b", "qishui", "落雪")
        check("发行歌名不能撞车", False)
    except ValueError as e:
        check("发行歌名不能撞车", "唯一" in str(e) or "占用" in str(e), str(e))

    P.submit_release("clip-b", "qishui", "落雪·夜版")
    check("第二首换发行歌名就能发", P.get_track("clip-b")["release_title"] == "落雪·夜版")

    try:
        P.submit_release("clip-b", "qishui", "落雪·改名")
        check("发行歌名一旦定下必须统一", False)
    except ValueError as e:
        check("发行歌名一旦定下必须统一", "统一" in str(e), str(e))

    print(f"\n{len(PASSED)} 项通过")


if __name__ == "__main__":
    main()
