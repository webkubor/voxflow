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

表就四张，查询都是直白的 select/upsert。ORM 带来的是另一套要学的抽象、
另一层出问题时要穿透的东西，在这个规模上换不来任何收益。

## 迁移与回滚

`migrate_from_json()` 幂等，可以反复跑。原 JSON **不删**（改名为 .migrated），
出问题随时能退回去看。
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
    -- 发行身份。生成歌名（title）可以重复（Suno 一次出两首同名）；
    -- 发出去的歌名必须唯一。独家授权：一首只能投一个平台。
    release_title    TEXT DEFAULT '',
    release_platform TEXT DEFAULT '',
    -- 音频时长（秒）。歌名会改，时长几乎不变，对不上名字时靠它认原曲。
    duration    INTEGER,
    created_at  TEXT,
    updated_at  TEXT
);

-- 一首本地作品 × 多条平台上架记录。
--
-- 以前主键是 (track_id, platform)：一首歌每个平台只能挂一条。
-- 对不上现实 —— 发到平台后可能改名，也可能把同一首拆成完整版/片段/伴奏
-- 好几条。上架记录的身份是 (platform, song_id)，跟本地歌名无关。
CREATE TABLE IF NOT EXISTS track_platforms (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    track_id     TEXT NOT NULL,
    platform     TEXT NOT NULL,
    platform_title TEXT DEFAULT '',    -- 平台上的歌名，可以跟本地 title 不同
    status       TEXT NOT NULL,
    song_id      TEXT DEFAULT '',
    song_url     TEXT DEFAULT '',
    album_id     TEXT DEFAULT '',
    album_name   TEXT DEFAULT '',
    track_no     INTEGER,
    duration     INTEGER,
    publish_date TEXT DEFAULT '',
    cover_url    TEXT DEFAULT '',
    cover_local  TEXT DEFAULT '',
    config       TEXT DEFAULT '{}',
    note         TEXT DEFAULT '',
    submitted_at TEXT DEFAULT '',
    plays        INTEGER DEFAULT 0,
    earned_cny   REAL DEFAULT 0,
    stats_at     TEXT DEFAULT '',
    updated_at   TEXT,
    FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
);
CREATE INDEX IF NOT EXISTS idx_tp_platform ON track_platforms(platform, status);
CREATE INDEX IF NOT EXISTS idx_tp_track ON track_platforms(track_id, platform);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tp_song ON track_platforms(platform, song_id)
    WHERE song_id != '';

CREATE TABLE IF NOT EXISTS albums (
    key          TEXT PRIMARY KEY,      -- <platform>-<album_id>
    platform     TEXT NOT NULL,
    album_id     TEXT NOT NULL,
    title        TEXT NOT NULL,
    track_count  INTEGER DEFAULT 0,
    publish_date TEXT DEFAULT '',
    company      TEXT DEFAULT '',
    description  TEXT DEFAULT '',
    tags         TEXT DEFAULT '',
    cover_url    TEXT DEFAULT '',
    cover_local  TEXT DEFAULT '',
    url          TEXT DEFAULT '',
    synced_at    TEXT
);
CREATE INDEX IF NOT EXISTS idx_albums_platform ON albums(platform, publish_date DESC);

CREATE TABLE IF NOT EXISTS platform_accounts (
    platform     TEXT PRIMARY KEY,
    label        TEXT DEFAULT '',
    artist_id    TEXT DEFAULT '',
    artist_name  TEXT DEFAULT '',
    alias        TEXT DEFAULT '[]',     -- JSON 数组
    avatar_url   TEXT DEFAULT '',
    brief        TEXT DEFAULT '',
    artist_url   TEXT DEFAULT '',
    user_id      TEXT DEFAULT '',
    user_url     TEXT DEFAULT '',
    song_count   INTEGER DEFAULT 0,
    album_count  INTEGER DEFAULT 0,
    stats        TEXT DEFAULT '{}',     -- JSON：播放量/粉丝/收益，只有后台有
    synced_at    TEXT
);

-- 计量事件：每次调用上游（Suno / 中台出图 / LLM / 本地 TTS）记一条。
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
    ("track_platforms", "plays", "INTEGER DEFAULT 0"),
    ("track_platforms", "earned_cny", "REAL DEFAULT 0"),
    ("track_platforms", "stats_at", "TEXT DEFAULT ''"),
    ("track_platforms", "platform_title", "TEXT DEFAULT ''"),
    ("tracks", "release_title", "TEXT DEFAULT ''"),
    ("tracks", "release_platform", "TEXT DEFAULT ''"),
    ("tracks", "duration", "INTEGER"),
]


def _migrate_listing_pk(c: sqlite3.Connection) -> None:
    """
    旧主键是 (track_id, platform)，一首歌每个平台只能一条。
    改成自增 id 之后，同一首可以挂多条（改名、拆分）。
    """
    have = {r["name"] for r in c.execute("PRAGMA table_info(track_platforms)")}
    if "id" in have:
        return
    cols = [r["name"] for r in c.execute("PRAGMA table_info(track_platforms)")]
    col_sql = ", ".join(cols)
    c.execute("PRAGMA foreign_keys = OFF")
    c.execute("""
        CREATE TABLE track_platforms_new (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT NOT NULL,
            platform TEXT NOT NULL,
            platform_title TEXT DEFAULT '',
            status TEXT NOT NULL,
            song_id TEXT DEFAULT '',
            song_url TEXT DEFAULT '',
            album_id TEXT DEFAULT '',
            album_name TEXT DEFAULT '',
            track_no INTEGER,
            duration INTEGER,
            publish_date TEXT DEFAULT '',
            cover_url TEXT DEFAULT '',
            cover_local TEXT DEFAULT '',
            config TEXT DEFAULT '{}',
            note TEXT DEFAULT '',
            submitted_at TEXT DEFAULT '',
            plays INTEGER DEFAULT 0,
            earned_cny REAL DEFAULT 0,
            stats_at TEXT DEFAULT '',
            updated_at TEXT,
            FOREIGN KEY (track_id) REFERENCES tracks(id) ON DELETE CASCADE
        )
    """)
    # 旧表没有 platform_title / id，按列名拷。缺的列用默认值。
    shared = [c_ for c_ in cols if c_ != "id"]
    c.execute(
        f"INSERT INTO track_platforms_new ({', '.join(shared)}) "
        f"SELECT {', '.join(shared)} FROM track_platforms"
    )
    c.execute("DROP TABLE track_platforms")
    c.execute("ALTER TABLE track_platforms_new RENAME TO track_platforms")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tp_platform ON track_platforms(platform, status)")
    c.execute("CREATE INDEX IF NOT EXISTS idx_tp_track ON track_platforms(track_id, platform)")
    c.execute(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_tp_song "
        "ON track_platforms(platform, song_id) WHERE song_id != ''"
    )
    # 旧数据：平台歌名就等于当时的本地 title
    c.execute("""
        UPDATE track_platforms SET platform_title = (
            SELECT title FROM tracks WHERE tracks.id = track_platforms.track_id
        ) WHERE IFNULL(platform_title,'') = ''
    """)
    c.execute("PRAGMA foreign_keys = ON")


def init() -> None:
    """建表 + 补列。幂等，每次启动跑一次。"""
    with connect() as c:
        c.executescript(SCHEMA)
        _migrate_listing_pk(c)
        for table, col, ddl in _ADD_COLUMNS:
            have = {r["name"] for r in c.execute(f"PRAGMA table_info({table})")}
            if col not in have:
                c.execute(f"ALTER TABLE {table} ADD COLUMN {col} {ddl}")
        c.execute(
            "CREATE UNIQUE INDEX IF NOT EXISTS idx_tracks_release_title "
            "ON tracks(release_title) WHERE release_title != ''"
        )
        # 存量回填只跑一次。每次 init 都回填会把后挂上的孤儿歌名写进
        # release_title，撞上已占用的唯一索引。
        done = c.execute("SELECT 1 FROM meta WHERE key='release_backfill'").fetchone()
        if not done:
            c.execute("""
                UPDATE tracks SET release_title = (
                    SELECT platform_title FROM track_platforms
                    WHERE track_id = tracks.id AND IFNULL(platform_title,'') != ''
                    LIMIT 1
                ) WHERE IFNULL(release_title,'') = ''
            """)
            c.execute("""
                UPDATE tracks SET release_platform = (
                    SELECT platform FROM track_platforms
                    WHERE track_id = tracks.id LIMIT 1
                ) WHERE IFNULL(release_platform,'') = ''
                  AND EXISTS (SELECT 1 FROM track_platforms WHERE track_id = tracks.id)
            """)
            c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('release_backfill', '1')")


def _j(v: Any, default: Any = None) -> Any:
    """解 JSON 字段，坏了就给默认值 —— 一个字段坏了不该让整行读不出来。"""
    if not v:
        return default
    try:
        return json.loads(v)
    except Exception:
        return default


# ── 迁移 ──────────────────────────────────────────────────

def migrate_from_json(verbose: bool = True) -> dict[str, int]:
    """
    把已有的 JSON 台账导进数据库。**幂等**，可以反复跑。

    原 JSON 不删，改名为 `.migrated` —— 出问题随时能退回去看。
    """
    init()
    stats = {"tracks": 0, "platforms": 0, "albums": 0, "accounts": 0}

    ledger_f = CONFIG_DIR / "pipeline.json"
    albums_f = CONFIG_DIR / "albums.json"
    accounts_f = CONFIG_DIR / "platform_accounts.json"

    with connect() as c:
        if ledger_f.exists():
            data = json.loads(ledger_f.read_text(encoding="utf-8"))
            for tid, t in (data.get("tracks") or {}).items():
                c.execute("""
                    INSERT INTO tracks (id, title, stage, lyrics, tags, prompt, album_desc,
                                        voice, clip_id, clip_ids, audio_file, cover_file,
                                        note, cloud_backup, created_at, updated_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(id) DO UPDATE SET
                        title=excluded.title, stage=excluded.stage,
                        lyrics=CASE WHEN excluded.lyrics != '' THEN excluded.lyrics ELSE tracks.lyrics END,
                        tags=CASE WHEN excluded.tags != '' THEN excluded.tags ELSE tracks.tags END,
                        album_desc=CASE WHEN excluded.album_desc != '' THEN excluded.album_desc ELSE tracks.album_desc END,
                        audio_file=CASE WHEN excluded.audio_file != '' THEN excluded.audio_file ELSE tracks.audio_file END,
                        cover_file=CASE WHEN excluded.cover_file != '' THEN excluded.cover_file ELSE tracks.cover_file END,
                        updated_at=excluded.updated_at
                """, (
                    tid, t.get("title") or "未命名", t.get("stage", "draft"),
                    t.get("lyrics", ""), t.get("tags", ""), t.get("prompt", ""),
                    t.get("album_desc", ""), t.get("voice") or "", t.get("clip_id") or "",
                    json.dumps(t.get("clip_ids") or [], ensure_ascii=False),
                    t.get("audio_file", ""), t.get("cover_file", ""), t.get("note", ""),
                    json.dumps(t.get("cloud_backup") or {}, ensure_ascii=False),
                    t.get("created_at") or t.get("updated_at") or _now(),
                    t.get("updated_at") or _now(),
                ))
                stats["tracks"] += 1

                for pk, info in (t.get("platforms") or {}).items():
                    if not isinstance(info, dict):
                        continue
                    c.execute("""
                        INSERT INTO track_platforms
                            (track_id, platform, status, song_id, song_url, album_id, album_name,
                             track_no, duration, publish_date, cover_url, cover_local,
                             config, note, submitted_at, updated_at)
                        VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                        ON CONFLICT(track_id, platform) DO UPDATE SET
                            status=excluded.status, song_id=excluded.song_id,
                            song_url=excluded.song_url, album_id=excluded.album_id,
                            album_name=excluded.album_name, track_no=excluded.track_no,
                            duration=excluded.duration, publish_date=excluded.publish_date,
                            cover_url=excluded.cover_url, cover_local=excluded.cover_local,
                            config=excluded.config, note=excluded.note,
                            submitted_at=excluded.submitted_at, updated_at=excluded.updated_at
                    """, (
                        tid, pk, info.get("status", "unknown"),
                        str(info.get("song_id") or ""), info.get("song_url", ""),
                        str(info.get("album_id") or ""), info.get("album", ""),
                        info.get("track_no"), info.get("duration"),
                        info.get("publish_date", ""), info.get("cover_url", ""),
                        info.get("cover_local", ""),
                        json.dumps(info.get("config") or {}, ensure_ascii=False),
                        info.get("note", ""), info.get("submitted_at", ""),
                        info.get("updated_at") or _now(),
                    ))
                    stats["platforms"] += 1

        if albums_f.exists():
            for key, a in (json.loads(albums_f.read_text(encoding="utf-8")).get("albums") or {}).items():
                c.execute("""
                    INSERT INTO albums (key, platform, album_id, title, track_count, publish_date,
                                        company, description, tags, cover_url, cover_local, url, synced_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(key) DO UPDATE SET
                        title=excluded.title, track_count=excluded.track_count,
                        publish_date=excluded.publish_date, description=excluded.description,
                        cover_url=excluded.cover_url, cover_local=excluded.cover_local,
                        synced_at=excluded.synced_at
                """, (
                    key, a.get("platform", ""), str(a.get("album_id") or ""), a.get("title", ""),
                    a.get("track_count", 0), a.get("publish_date", ""), a.get("company", ""),
                    a.get("description", ""), a.get("tags", ""), a.get("cover_url", ""),
                    a.get("cover_local", ""), a.get("url", ""), a.get("synced_at") or _now(),
                ))
                stats["albums"] += 1

        if accounts_f.exists():
            for pk, acc in (json.loads(accounts_f.read_text(encoding="utf-8")).get("accounts") or {}).items():
                c.execute("""
                    INSERT INTO platform_accounts
                        (platform, label, artist_id, artist_name, alias, avatar_url, brief,
                         artist_url, user_id, user_url, song_count, album_count, stats, synced_at)
                    VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)
                    ON CONFLICT(platform) DO UPDATE SET
                        artist_name=excluded.artist_name, alias=excluded.alias,
                        avatar_url=excluded.avatar_url, song_count=excluded.song_count,
                        album_count=excluded.album_count, stats=excluded.stats,
                        synced_at=excluded.synced_at
                """, (
                    pk, acc.get("platform", ""), str(acc.get("artist_id") or ""),
                    acc.get("artist_name", ""),
                    json.dumps(acc.get("alias") or [], ensure_ascii=False),
                    acc.get("avatar_url", ""), acc.get("brief", ""), acc.get("artist_url", ""),
                    str(acc.get("user_id") or ""), acc.get("user_url", ""),
                    acc.get("song_count", 0), acc.get("album_count", 0),
                    json.dumps(acc.get("stats") or {}, ensure_ascii=False),
                    acc.get("synced_at") or _now(),
                ))
                stats["accounts"] += 1

        c.execute("INSERT OR REPLACE INTO meta (key, value) VALUES ('migrated_at', ?)", (_now(),))

    # 原文件留着，改个名 —— 迁移出问题时还能回去看
    if verbose:
        for f in (ledger_f, albums_f, accounts_f):
            if f.exists():
                f.rename(f.with_suffix(f.suffix + ".migrated"))
        print(f"✓ 迁移完成：作品 {stats['tracks']} · 平台状态 {stats['platforms']} · "
              f"专辑 {stats['albums']} · 账号 {stats['accounts']}")
        print(f"  原 JSON 已改名为 *.migrated（没删，随时能回去看）")
    return stats
