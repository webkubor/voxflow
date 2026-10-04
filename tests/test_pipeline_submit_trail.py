#!/usr/bin/env python3
"""
发行提交留痕 —— `.venv/bin/python tests/test_pipeline_submit_trail.py`

要锁住的性质：

1. `submit_release()` 只定发行身份（→ preparing），**不写 submitted_at**
2. `mark_submitted()` 把状态推进到 reviewing，并**写下提交时刻**
3. 重复调 `mark_submitted()` 不覆盖首次提交时刻（幂等）
4. 已上架的歌不能再标提交
5. 没定发行身份就标提交 → 明确报错，不静默
6. submitted_at 能从 `get_track()` 读回来（CLI 靠它显示）

背景：`submitted_at` 这个字段在 schema 里躺了很久，`db.py` 能存，
但全项目**没有任何一处传过值** —— 于是「什么时候交的」永远答不出来。
2026-09-26 提交的 5 首歌至今 submitted_at 为空。
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
    print(f"  ✓ {name}")


def listing(tid: str, plat: str) -> dict:
    for r in (P.get_track(tid) or {}).get("listings", []):
        if r.get("platform") == plat:
            return r
    return {}


def plat_of(track: dict, plat: str) -> dict:
    """submit_release / mark_submitted 返回的是**整首 track**，平台状态嵌在里面。"""
    return (track.get("platforms") or {}).get(plat) or {}


def main() -> int:
    db.init()

    print("备料阶段：submit_release 只锁身份，不写提交时刻")
    P.upsert("t-1", title="测试曲", stage="selected")
    res = plat_of(P.submit_release("t-1", "netease", "测试曲·发行"), "netease")
    check("submit_release 落到 preparing", res.get("status") == "preparing", res.get("status"))
    check("submit_release 不写 submitted_at", not res.get("submitted_at"),
          repr(res.get("submitted_at")))

    print("\n提交留痕：mark_submitted 推进到 reviewing 并记时刻")
    res = plat_of(P.mark_submitted("t-1", "netease", note="提交单 A-1"), "netease")
    check("状态转 reviewing", res.get("status") == "reviewing", res.get("status"))
    first_ts = res.get("submitted_at")
    check("写下了 submitted_at", bool(first_ts), repr(first_ts))
    check("submitted_at 能从 get_track 读回", bool(listing("t-1", "netease").get("submitted_at")))
    check("note 一起记上", listing("t-1", "netease").get("note") == "提交单 A-1")

    print("\n幂等：重复标提交不覆盖首次时刻")
    res2 = plat_of(P.mark_submitted("t-1", "netease", note="又点了一次"), "netease")
    check("状态仍是 reviewing", res2.get("status") == "reviewing")
    check("首次提交时刻没被覆盖", res2.get("submitted_at") == first_ts,
          f"{first_ts} → {res2.get('submitted_at')}")

    print("\n边界")
    P.upsert("t-2", title="另一首", stage="selected")
    try:
        P.mark_submitted("t-2", "netease")
        check("没备料就标提交应报错", False, "居然没报错")
    except ValueError as e:
        check("没备料就标提交 → 明确报错", "发行身份" in str(e), str(e))

    P.upsert("t-3", title="上架曲", stage="selected")
    P.submit_release("t-3", "qishui", "上架曲")
    P.set_platform_status("t-3", "qishui", "online", song_id="999")
    try:
        P.mark_submitted("t-3", "qishui")
        check("已上架再标提交应报错", False, "居然没报错")
    except ValueError as e:
        check("已上架再标提交 → 明确报错", "上架" in str(e), str(e))

    try:
        P.mark_submitted("t-1", "不存在的平台")
        check("未知平台应报错", False, "居然没报错")
    except ValueError as e:
        check("未知平台 → 明确报错", "未知平台" in str(e), str(e))

    print("\n阶段推导：reviewing 能推成 publishing")
    check("derived_stage 认得 reviewing", P.derived_stage({"netease": {"status": "reviewing"}}) == "publishing",
          P.derived_stage({"netease": {"status": "reviewing"}}))

    print("\nCLI 取值：歌名 / 完整 ID / ID 前缀都要认")
    import importlib
    import typer
    rel = importlib.import_module("cli.commands.release")
    # 用真 UUID 长度，才能测出「8 位前缀唯一」这件事
    uid = "0b722139-dcc3-4dc7-8370-6e36541d314b"
    P.upsert(uid, title="前缀测试曲", stage="selected")
    check("完整 ID", rel._resolve(uid) == uid)
    check("8 位 ID 前缀", rel._resolve(uid[:8]) == uid, rel._resolve(uid[:8]))
    check("歌名", rel._resolve("测试曲") == "t-1")
    check("发行歌名", rel._resolve("测试曲·发行") == "t-1")
    try:
        rel._resolve("查无此物的名字")
        check("查无此物应报错", False, "居然解析成功了")
    except typer.BadParameter:
        check("查无此物 → 明确报错", True)
    try:
        rel._resolve("t-")                     # t-1 / t-2 / t-3 都匹配
        check("歧义前缀应报错", False, "居然解析成功了")
    except typer.BadParameter:
        check("歧义前缀 → 明确报错", True)

    print(f"\n✅ {len(PASSED)} 条断言全过")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
