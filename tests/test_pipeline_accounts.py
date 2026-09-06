#!/usr/bin/env python3
"""
平台账号合并的自检 —— `.venv/bin/python tests/test_pipeline_accounts.py`

要锁住的性质：三个发行平台始终都返回；没跑过同步脚本的平台
也能带上 artist.json 里的艺名，而不是整页「未接入」。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="voxflow_test_")
os.environ["VOXFLOW_HOME"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db, pipeline  # noqa: E402
from core.paths import CONFIG_DIR  # noqa: E402

PASSED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        raise AssertionError(f"✗ {name}" + (f" —— {detail}" if detail else ""))
    PASSED.append(name)


def write_artist() -> None:
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (CONFIG_DIR / "artist.json").write_text(json.dumps({
        "stage_name": "月栖洲",
        "roles": {"performer": "月栖洲", "lyricist": "月栖洲", "composer": "月栖洲"},
        "platform_profiles": [
            {"platform": "汽水音乐", "key": "qishui", "console_url": "https://music.douyin.com/console"},
            {"platform": "QQ音乐", "key": "tencent",
             "artist_url": "https://y.qq.com/n/ryqq_v2/singer/002Rcy0a0YpQ7L"},
            {"platform": "网易云音乐", "key": "netease",
             "artist_url": "https://music.163.com/#/artist?id=32462959"},
        ],
    }, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    db.init()
    write_artist()

    data = pipeline.list_platform_accounts()
    acc = data["accounts"]
    check("三个平台都在", set(acc) == {"qishui", "netease", "tencent"}, str(set(acc)))
    check("发行主体是艺名", data["stage_name"] == "月栖洲")
    check("角色短标签按唱词曲排", data["roles"][:3] == ["唱", "词", "曲"], str(data["roles"]))

    qs = acc["qishui"]
    check("汽水没同步也有艺名", qs["artist_name"] == "月栖洲")
    check("汽水标成未同步", qs["synced"] is False)
    check("汽水 song_count 是 0 不是 None", qs["song_count"] == 0)
    check("汽水标签是汽水音乐", qs["label"] == "汽水音乐")
    check("腾讯展示名是 QQ音乐 不是腾讯系", acc["tencent"]["label"] == "QQ音乐")

    pipeline.upsert_platform_account(
        "netease", label="网易云音乐", artist_name="月栖洲",
        artist_url="https://music.163.com/#/artist?id=32462959",
        song_count=33, album_count=6,
    )
    acc2 = pipeline.list_platform_accounts()["accounts"]
    check("同步过的平台 synced=True", acc2["netease"]["synced"] is True)
    check("同步过的平台保留后台歌曲数", acc2["netease"]["song_count"] == 33)
    check("QQ 主页从档案补上", "y.qq.com" in acc2["tencent"]["artist_url"])
    check("真实姓名不在账号接口里", "王恩博" not in json.dumps(acc2, ensure_ascii=False))

    print(f"\n{len(PASSED)} 项通过")


if __name__ == "__main__":
    main()
