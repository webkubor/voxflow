"""
台账的存储层 —— SQLite。

## 为什么从 JSON 换过来

之前的判据是「有并发写、要组合查询、单文件几 MB 才换」。**第二条成立了**：
数据散在 4 个 JSON 里（作品、专辑、平台账号、音色），`/api/albums` 已经在
手写 join 把曲目挂到专辑下，再接 QQ 音乐和汽水会更多。这是 SQL 一句话的事。

换过来还顺带解决两个问题：

- **原子性**。「记平台状态 + 推进阶段」现在是两次全量重写 JSON，
  中间崩了会留下「发版中但不知道发去哪」的半吊子状态。SQLite 一个事务搞定。
- **全量重写**。JSON 每次改一个字段都要把整份读进来、改、再整份写回去。
  几百首歌时还好，但这个模式本身就不对。

## 什么没换

**配置类仍然是 JSON**：`artist.json`（艺人档案）、`platforms.json`（平台 SOP）。
它们是人手改的、要能 `cat` 看、要能 git diff、几十行且不会增长。
把它们塞进数据库只会让改一个字段变成一件麻烦事。

分层的依据是**「谁在写」**：机器持续写入的进库，人手工维护的留 JSON。

## 为什么不用 ORM

表就三张，查询都是直白的 select/upsert。ORM 带来的是另一套要学的抽象、
另一层出问题时要穿透的东西，在这个规模上换不来任何收益。

## 发行数据不在这里

2026-10-10 拆分：发行（上架台账、专辑、平台账号、状态流转）整体迁到独立仓
[suno-publisher](https://github.com/webkubor/suno-publisher)，它有自己
的库（`~/.suno-publisher/suno-publisher.db`）和五张表。本仓只管生成。

为什么不共用一个库：`connect()` 每次开新连接、不用全局单例，设计前提是
「本地单用户工具」。两个独立发版的仓同时打开同一个文件，等于把这个假设叠加
两次 —— `timeout=10` 的锁等待在两边都频繁写时会炸 `database is locked`，
而任何一边改 schema 都会在不知情的情况下冲击另一边。
"""

from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator

from core.paths import CONFIG_DIR, DATA_DIR

DB_PATH = DATA_DIR / "voxflow.db"

SCHEMA = """
CREATE TABLE IF NOT EXISTS tracks (
    id          TEXT PRIMARY KEY,
    title       TEXT NOT NULL,
    stage       TEXT NOT NULL DEFAULT 'draft',
    lyrics      TEXT DEFAULT '',
    tags        TEXT DEFAULT '',
    prompt      TEXT DEFAULT '',
    album_desc  TEXT DEFAULT '',
    voice       TEXT DEFAULT '',
    clip_id     TEXT DEFAULT '',
    clip_ids    TEXT DEFAULT '[]',      -- JSON 数组：Suno 一次出两首，都留着
    audio_file  TEXT DEFAULT '',
    cover_file  TEXT DEFAULT '',
    note        TEXT DEFAULT '',
    cloud_backup TEXT DEFAULT '{}',     -- JSON：R2 同步位置，预留
    -- 发行身份两列（release_title / release_platform）2026-10-10 随发行拆分
    -- 移走了：不再声明、不再写入。**老库里它们还在**（当初是 ALTER 加的，
    -- 建表语句里从来就没有）—— 本仓已无任何读取方，要清掉见
    -- scripts/drop_release_tables.py。新建的库不会有这两列。
    -- 音频时长（秒）。歌名会改，时长几乎不变，对不上名字时靠它认原曲。
    duration    INTEGER,
    created_at  TEXT,
    updated_at  TEXT
);

--
-- 为什么要单独一张表而不是塞进日志文件：成本要能按作品、按 provider、按天
-- **聚合查询**——「这首歌到底花了多少」「这个月中台烧了多少积分」。
-- JSONL 能记录但不能查，SQL 一句话的事。
--
-- cost_cny 在写入时就换算好并落盘（而不是查询时按当前单价算）：单价会变
-- （Suno 换套餐、中台调价），历史成本应该定格在**当时**的单价上，
-- 不然改一次价，过去半年的账全变了。
CREATE TABLE IF NOT EXISTS usage_events (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    ts          TEXT NOT NULL,
    provider    TEXT NOT NULL,          -- suno | museav | llm | tts
    action      TEXT NOT NULL,          -- generate | cover | lyrics | clone | design
    qty         REAL DEFAULT 1,         -- 业务量：首/张/次/秒
    credits     REAL DEFAULT 0,         -- 消耗的上游积分
    cost_cny    REAL DEFAULT 0,         -- 换算成人民币（写入时定格）
    track_id    TEXT DEFAULT '',        -- 关联作品，用于算单曲成本
    duration_ms INTEGER DEFAULT 0,
    ok          INTEGER DEFAULT 1,      -- 失败也要记：失败的调用照样烧钱
    -- 这条是实测还是估算。回填历史作品时只能按「有 clip_id = 用过 Suno」推算，
    -- 那是**估计值**，必须和真实计量分得开 —— 混在一起之后，看到的数字就再也
    -- 说不清有多少是真的，而说不清的数字会被当成真的拿去做决策。
    estimated   INTEGER DEFAULT 0,
    meta        TEXT DEFAULT '{}'
);
CREATE INDEX IF NOT EXISTS idx_usage_ts ON usage_events(ts DESC);
CREATE INDEX IF NOT EXISTS idx_usage_track ON usage_events(track_id);
CREATE INDEX IF NOT EXISTS idx_usage_provider ON usage_events(provider, ts DESC);

CREATE TABLE IF NOT EXISTS meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""


def _now() -> str:
    return time.strftime("%Y-%m-%dT%H:%M:%S")


@contextmanager
def connect() -> Iterator[sqlite3.Connection]:
    """
    拿一条连接，出作用域自动提交/回滚。

    每次开新连接而不是全局单例：这是本地单用户工具，连接开销可忽略，
    而全局连接会在多线程（FastAPI 的 worker）下踩 sqlite 的线程限制。
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# 已有库的增量迁移：(表, 列, 列定义)。
#
# 为什么用清单而不是版本号迁移框架：这是本地单用户工具，表只有五张，
# 迁移全是「加个列」。一套 migration 框架要引入版本表、上下迁移、
# 执行顺序 —— 解决的是「多环境、多人、要能回滚」的问题，这里一个都没有。
#
# ADD COLUMN 在 SQLite 里不幂等（重复加会报错），所以先查 PRAGMA。
_ADD_COLUMNS = [
    ("usage_events", "estimated", "INTEGER DEFAULT 0"),
    ("tracks", "duration", "INTEGER"),
    # 发行侧的补列（track_platforms 的 plays/earned_cny/publisher、
    # platform_accounts 的 login_*）随 2026-10-10 拆分一并删掉了 ——
    # 那些表已经不在本仓。
]





def init() -> None:
    """建表 + 补列。幂等，每次启动跑一次。

    2026-10-10 拆分后只管生成侧的表：tracks / usage_events / meta。
    发行那四张表（track_platforms / albums / platform_accounts / publish_events）
    连同它们的补列、索引和存量回填一起删了 —— 那些数据在 suno-publisher 的库，
    本仓不再产生也不再读。

    **只删代码不 DROP 存量表**：老库里的那四张表还在（见 scripts/drop_release_tables.py
    可以显式清掉）。这样万一还有没找到的读取方，是「表还在但没人读」
    而不是「表没了、当场炸」。
    """
    with connect() as c:
        c.executescript(SCHEMA)
        for table, col, ddl in _ADD_COLUMNS:
            have = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
            if col not in have:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")


def _j(v: Any, default: Any = None) -> Any:
    """解 JSON 字段，坏了就给默认值 —— 一个字段坏了不该让整行读不出来。"""
    if not v:
        return default
    try:
        return json.loads(v)
    except Exception:
        return default


# ── 迁移 ──────────────────────────────────────────────────

