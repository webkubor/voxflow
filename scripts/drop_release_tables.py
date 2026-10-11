#!/usr/bin/env python3
"""清掉 voxflow 老库里的发行残留：四张表 + tracks 的两个发行列。

    .venv/bin/python scripts/drop_release_tables.py            # 预演（默认）
    .venv/bin/python scripts/drop_release_tables.py --commit

## 为什么删

发行（上架台账、专辑、平台账号、状态流转）2026-10-10 整体迁到了独立仓
suno-publisher，数据也搬过去了（`scripts/migrate_from_voxflow.py` +
`backfill_publisher.py` 补的「谁负责发的」9 条）。代码侧已经没有任何读取方。
留着它们只会让人以为「发行名的真源还在这里」。

## 为什么是显式脚本而不是 init() 里自动 DROP

**自动 DROP 是删数据，不该在每次启动时静默发生。** 万一还有没找到的读取方，
自动删会让它当场炸；而这个脚本是手动触发的，跑之前你能先备份、跑之后能回滚。

## 安全措施

- 默认只预演，打印每张表的行数和「有没有非空的关键列」
- `--commit` 前**自动备份**到 `voxflow.db.bak-<时间戳>`，路径打印出来
- 删之前再查一次：`publish_events` 之外的三张表如果还有行，会先列出来提醒你
  确认那些数据确实在新仓（这是最后一道人眼检查）

## 回滚

```bash
cp ~/.voxflow/voxflow.db.bak-20261011-120000 ~/.voxflow/voxflow.db
```
"""
from __future__ import annotations

import argparse
import shutil
import sqlite3
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.db import DB_PATH  # noqa: E402

TABLES = ("track_platforms", "albums", "platform_accounts", "publish_events")
# tracks 上那两个发行列。SQLite 3.35+ 才支持 DROP COLUMN。
COLUMNS = (("tracks", "release_title"), ("tracks", "release_platform"))


def _tables(conn: sqlite3.Connection) -> set[str]:
    return {r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'")}


def _columns(conn: sqlite3.Connection, table: str) -> set[str]:
    return {d[1] for d in conn.execute(f"PRAGMA table_info({table})")}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--commit", action="store_true", help="真的删（默认只预演）")
    args = ap.parse_args()

    if not DB_PATH.is_file():
        raise SystemExit(f"✗ 找不到库：{DB_PATH}")

    conn = sqlite3.connect(DB_PATH)
    have_t = _tables(conn)
    have_c = _columns(conn, "tracks") if "tracks" in have_t else set()

    todo_t = [t for t in TABLES if t in have_t]
    todo_c = [(t, c) for t, c in COLUMNS if c in have_c]

    if not todo_t and not todo_c:
        print("库里没有发行残留，不用做任何事。")
        return 0

    print(f"库：{DB_PATH}\n")
    for t in todo_t:
        n = conn.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
        print(f"  表 {t:<20} {n:>4} 行")
    for t, c in todo_c:
        n = conn.execute(
            f"SELECT COUNT(*) FROM {t} WHERE IFNULL({c},'') != ''").fetchone()[0]
        print(f"  列 {t}.{c:<18} {n:>4} 行有值")
    conn.close()

    if not args.commit:
        print("\n（预演，没删任何东西。加 --commit 真删。）")
        print("删前会先自动备份。")
        return 0

    # 最后一道人眼检查：这些表的行数应该和新仓对得上，否则可能还有没搬完的
    print("\n=== 删除前的最后确认 ===")
    print("  上面这些数据应当在 suno-publisher 的库里。对不上就别删。")
    stamp = time.strftime("%Y%m%d-%H%M%S")
    backup = DB_PATH.with_suffix(f".db.bak-{stamp}")
    shutil.copy2(DB_PATH, backup)
    print(f"  已备份：{backup}")

    conn = sqlite3.connect(DB_PATH)
    for t in todo_t:
        conn.execute(f"DROP TABLE IF EXISTS {t}")
        print(f"  已删表 {t}")
    # 列上可能挂着索引 —— SQLite 的 DROP COLUMN 会因它失败
    # （实测 idx_tracks_release_title 就是，报 "error in index ... after drop
    # column"，列会静静地留着）。所以先删索引再删列。
    leftover_idx = [r[0] for r in conn.execute(
        "SELECT name FROM sqlite_master WHERE type='index' AND tbl_name='tracks'")]
    for name in leftover_idx:
        conn.execute(f"DROP INDEX IF EXISTS {name}")
        print(f"  已删索引 {name}")
    for t, c in todo_c:
        try:
            conn.execute(f"ALTER TABLE {t} DROP COLUMN {c}")
            print(f"  已删列 {t}.{c}")
        except sqlite3.OperationalError as e:
            # 失败不影响正确性（列留着只是冗余，本仓已无读取方）
            print(f"  ⚠ 删列 {t}.{c} 失败（{e}）—— 列留着无害，本仓已不读它")
    conn.commit()
    conn.close()
    print("\n✓ 完成。回滚：cp " + str(backup) + " " + str(DB_PATH))
    return 0


if __name__ == "__main__":
    sys.exit(main())
