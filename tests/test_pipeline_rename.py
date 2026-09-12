#!/usr/bin/env python3
"""
发行前改名 —— `.venv/bin/python tests/test_pipeline_rename.py`

规则：交到平台后台（uploaded 及以后）之前可以改，之后不许；改名照样要全局唯一。
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
        check(name, expect in str(e), f"报错了但不是预期的那条：{e}")
        return
    raise AssertionError(f"✗ {name} —— 本该拒绝却放行了")


def main() -> int:
    db.init()
    P.upsert("t-rename", title="备料中的歌", stage="selected")
    P.submit_release("t-rename", "qishui", "初版歌名")

    # 1. 还在备料（preparing）→ 可以改
    P.rename_release("t-rename", "想好的歌名")
    check("preparing 时能改名", (P.get_track("t-rename") or {}).get("release_title") == "想好的歌名")

    # 2. 平台记录里的名字跟着一起改，不能两处打架
    plats = (P.get_track("t-rename") or {}).get("platforms") or {}
    titles = [v.get("platform_title") for v in plats.values()] if isinstance(plats, dict) else []
    check("平台备料记录同步改名", all(t == "想好的歌名" for t in titles if t), str(titles))

    # 3. 空名字不许
    rejects("空名字被挡", lambda: P.rename_release("t-rename", "   "), "不能空")

    # 4. 撞别人的发行名不许
    P.upsert("t-other", title="另一首", stage="selected")
    P.submit_release("t-other", "netease", "别人的名字")
    rejects("重名被挡", lambda: P.rename_release("t-rename", "别人的名字"), "必须唯一")

    # 5. 交到平台后台之后（uploaded）→ 锁死
    P.set_platform_status("t-rename", "qishui", "uploaded")
    rejects("uploaded 后锁死", lambda: P.rename_release("t-rename", "又想改"), "不能再改")

    # 6. 锁死后名字确实没被改动
    check("拒绝后名字没动", (P.get_track("t-rename") or {}).get("release_title") == "想好的歌名")

    for n in PASSED:
        print(f"✓ {n}")
    print(f"\n{len(PASSED)} 项通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
