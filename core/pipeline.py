"""
作品流水线状态 —— 「每首歌走到哪一步了」的唯一真源。

## 为什么需要它

VoxFlow 的价值是一条链：克隆声音 → 出歌 → 选定 → 发版 → 上架。但在此之前，
每一段的产物散在不同地方（Suno 云端、out/music/、publish/YYYYMMDD/），
状态只能靠「文件存不存在」倒推 —— 而倒推有两个问题：

1. **推不出用户的意图**。文件在 publish/ 下只说明打包过，不代表用户确认要发；
   而「确认发版」正是整条链上最重要的那个决定（发版之前不该做任何平台相关的事，
   因为不知道发哪个平台，封面尺寸和文案风格都定不了）。
2. **推不出失败**。审核被拒、上传中断，文件系统里看不出来。

所以状态要显式记录。这个文件管的就是那份台账。

## 状态机

    draft ──→ generated ──→ selected ──→ publishing ──→ published
    草稿      已出歌        已选定       发版中         已上架
                              │
                              └──→ archived（弃用）

- **generated → selected 是人的决定**：Suno 一次出两首，得听过才知道要哪首
- **selected → publishing 也是人的决定**：确认发版之后才按目标平台生成物料
- 每个平台单独记状态：同一首歌可能�givenB 平台已上架、A 平台还在审核

## 为什么不用数据库

台账规模是「几十到几百首」，一个 JSON 足够，而且可读、可手改、可进 git diff。
上数据库会引入迁移、连接、备份三件事，收益为零。
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from core import db
from core.paths import DATA_DIR, LEDGER_FILE, PUBLISH_ACCOUNTS_FILE

BASE_DIR = DATA_DIR          # 台账里的相对路径都是相对数据根
LEDGER = LEDGER_FILE
PUBLISH_ACCOUNTS = PUBLISH_ACCOUNTS_FILE

# 状态机的合法状态。顺序即流程顺序 —— 前端画进度条直接按这个数组来，
# 不要在前端再抄一份，那样两边迟早对不上。
STAGES = ["draft", "generated", "selected", "publishing", "published"]
STAGE_LABELS = {
    "draft": "草稿",
    "generated": "已出歌",
    "selected": "已选定",
    "publishing": "发版中",
    "published": "已上架",
    "archived": "已弃用",
}

# 目标平台。SOP 差异（封面尺寸、AI 声明方式、上传方式）见 docs/ROADMAP.md，
# 这里只登记「支持发到哪」。
PLATFORMS = {
    "qishui": {"label": "汽水音乐", "cover": "1440x1440", "ai_field": "创作方式=AI"},
    "netease": {"label": "网易云", "cover": "1400x1400", "ai_field": "AI 音乐人身份"},
    "tencent": {"label": "腾讯系", "cover": "待确认", "ai_field": "待确认"},
}

DEFAULT_PUBLISH_ACCOUNTS = [
    {"id": "qishui-main", "platform": "qishui", "label": "汽水音乐账号"},
    {"id": "netease-main", "platform": "netease", "label": "网易云音乐人账号"},
    {"id": "tencent-main", "platform": "tencent", "label": "腾讯音乐人账号"},
]

LOGIN_STATUS_LABELS = {
    "connected": "已登录",
    "expired": "登录失效",
    "unconfigured": "未接入",
    "unknown": "状态未知",
}

BACKUP_STATUS_LABELS = {
    "backed_up": "已云备份",
    "syncing": "同步中",
    "failed": "备份失败",
    "unrecorded": "未登记",
}


def _publish_accounts() -> list[dict[str, Any]]:
    """读取非敏感账号元数据；缺失时返回三个待接入账号。"""
    try:
        data = json.loads(PUBLISH_ACCOUNTS.read_text(encoding="utf-8"))
        accounts = data.get("accounts", [])
    except (OSError, json.JSONDecodeError):
        accounts = []

    normalized = []
    for account in accounts or DEFAULT_PUBLISH_ACCOUNTS:
        platform = account.get("platform")
        if platform not in PLATFORMS:
            continue
        login = account.get("login") or {}
        status = login.get("status", "unconfigured")
        normalized.append({
            "id": account.get("id", platform),
            "platform": platform,
            "label": account.get("label", PLATFORMS[platform]["label"]),
            "login": {
                "status": status,
                "label": LOGIN_STATUS_LABELS.get(status, status),
                "detail": login.get("detail", "尚未接入登录态检测"),
                "updated_at": login.get("updated_at", ""),
            },
        })
    return normalized



def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


# 只能存、不能显示的字段。
#
# 界面是可以给人看的地方 —— 演示、截图、录屏都可能发生。真实姓名、证件号、
# 手机号这类东西的用途是**填平台表单**，不是展示；它们留在库里供脚本读取，
# 但不该经 API 出去。
#
# 在**后端**过滤而不是前端不渲染：前端漏一处就泄露了，而且 API 本身也可能
# 被别的地方调用。数据不出后端，才叫真的不显示。
SENSITIVE_KEY_HINTS = ("真实姓名", "身份证", "手机", "电话", "银行", "证件", "id_card", "phone")


def _redact(config: dict[str, Any]) -> dict[str, Any]:
    """抹掉配置里的敏感字段，只留一个标记说明「填过了」。"""
    if not isinstance(config, dict):
        return config
    return {
        k: ("···（已填，不在界面展示）" if any(h in str(k) for h in SENSITIVE_KEY_HINTS) else v)
        for k, v in config.items()
    }


def _row_to_track(row, platforms: dict[str, Any]) -> dict[str, Any]:
    """一行 tracks + 它的平台状态 → 前端吃的那个结构。"""
    stage = row["stage"]
    backup = db._j(row["cloud_backup"], {}) or {}
    b_status = backup.get("status", "unrecorded")
    tid = row["id"]
    return {
        "id": tid,
        "title": row["title"] or "未命名",
        "stage": stage,
        "stage_label": STAGE_LABELS.get(stage, stage),
        "stage_index": STAGES.index(stage) if stage in STAGES else -1,
        "voice": row["voice"] or None,
        "clip_id": row["clip_id"] or None,
        "clip_ids": db._j(row["clip_ids"], []) or [],
        "platforms": platforms,
        "cloud_backup": {
            "status": b_status,
            "label": BACKUP_STATUS_LABELS.get(b_status, b_status),
            "location": backup.get("location", ""),
            "updated_at": backup.get("updated_at", ""),
        },
        "updated_at": row["updated_at"] or "",
        "note": row["note"] or "",
        # 创作元数据：歌本身的内容。平台发布要用（歌词是必填项、风格影响推荐），
        # 出问题复现也得靠它。不能只留在 Suno 云端和文件名里 —— 那边不归我们。
        "lyrics": row["lyrics"] or "",
        "tags": row["tags"] or "",
        "prompt": row["prompt"] or "",
        "album_desc": row["album_desc"] or "",
        "audio_file": row["audio_file"] or "",
        "cover_file": row["cover_file"] or "",
        # 现成可用的 URL —— 前端不该自己拼路径，拼错了是静默 404
        "cover_url": f"/api/cover/{tid}" if row["cover_file"] else "",
        "audio_url": (
            "/api/audio/" + "/".join(row["audio_file"].split("/")[-2:])
            if (row["audio_file"] or "").startswith("out/") else ""
        ),
    }


def _platform_row(r) -> dict[str, Any]:
    out = {
        "status": r["status"],
        "song_id": r["song_id"] or None,
        "song_url": r["song_url"] or "",
        "album_id": r["album_id"] or None,
        "album": r["album_name"] or "",
        "album_url": (f"https://music.163.com/#/album?id={r['album_id']}"
                      if r["platform"] == "netease" and r["album_id"] else ""),
        "track_no": r["track_no"],
        "duration": r["duration"],
        "publish_date": r["publish_date"] or "",
        "cover_url": r["cover_url"] or "",
        "cover_local": r["cover_local"] or "",
        "note": r["note"] or "",
        "submitted_at": r["submitted_at"] or "",
        "updated_at": r["updated_at"] or "",
    }
    cfg = db._j(r["config"], {}) or {}
    if cfg:
        out["config"] = _redact(cfg)      # 敏感字段不出后端
    return out


def list_tracks() -> list[dict[str, Any]]:
    """所有作品，按最近更新排序。前端看板直接吃这个。"""
    db.init()
    with db.connect() as c:
        rows = c.execute("SELECT * FROM tracks ORDER BY updated_at DESC").fetchall()
        plat_rows = c.execute("SELECT * FROM track_platforms").fetchall()

    by_track: dict[str, dict[str, Any]] = {}
    for r in plat_rows:
        by_track.setdefault(r["track_id"], {})[r["platform"]] = _platform_row(r)

    return [_row_to_track(r, by_track.get(r["id"], {})) for r in rows]


def get_track(track_id: str) -> dict[str, Any] | None:
    """单首作品。看板点进详情用，不用把全表拉回来再过滤。"""
    db.init()
    with db.connect() as c:
        row = c.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        if not row:
            return None
        plats = {r["platform"]: _platform_row(r) for r in
                 c.execute("SELECT * FROM track_platforms WHERE track_id = ?", (track_id,)).fetchall()}
    return _row_to_track(row, plats)


def upsert(track_id: str, **fields: Any) -> dict[str, Any]:
    """新建或更新一首作品。只写传进来的字段，不覆盖其余。"""
    db.init()
    now = _now()
    # clip_ids / cloud_backup 是 JSON 列，进库前要序列化
    for k in ("clip_ids", "cloud_backup"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k], ensure_ascii=False)

    cols = ("title", "stage", "lyrics", "tags", "prompt", "album_desc", "voice",
            "clip_id", "clip_ids", "audio_file", "cover_file", "note", "cloud_backup")
    given = {k: v for k, v in fields.items() if k in cols and v is not None}

    with db.connect() as c:
        exists = c.execute("SELECT 1 FROM tracks WHERE id = ?", (track_id,)).fetchone()
        if not exists:
            c.execute("INSERT INTO tracks (id, title, stage, created_at, updated_at) VALUES (?,?,?,?,?)",
                      (track_id, given.pop("title", "未命名"), given.pop("stage", "draft"), now, now))
        if given:
            sets = ", ".join(f"{k} = ?" for k in given)
            c.execute(f"UPDATE tracks SET {sets}, updated_at = ? WHERE id = ?",
                      (*given.values(), now, track_id))
        else:
            c.execute("UPDATE tracks SET updated_at = ? WHERE id = ?", (now, track_id))

    return get_track(track_id) or {}


def set_stage(track_id: str, stage: str) -> dict[str, Any]:
    """
    推进状态。**不做自动跃迁** —— 每一步都是显式的。

    尤其是 selected → publishing：那是「我确认要发这首」的决定，
    不能因为「文件齐了」就自动往前走。
    """
    if stage not in STAGES and stage != "archived":
        raise ValueError(f"未知状态: {stage}")
    return upsert(track_id, stage=stage)


def set_platform_status(track_id: str, platform: str, status: str, **extra: Any) -> dict[str, Any]:
    """
    记录某个平台的发布状态。

    每个平台单独记：同一首歌可能在汽水已上架、网易云还在审核 —— 只有一个
    全局状态的话，这种情况根本表达不出来。

    **整个操作在一个事务里**：以前是「改 JSON 再整份写回」，中途崩了会留下
    半吊子状态（比如「发版中但不知道发去哪」），那种状态没人看得懂。
    """
    if platform not in PLATFORMS:
        raise ValueError(f"未知平台: {platform}")
    db.init()
    now = _now()
    cfg = extra.pop("config", None)
    album = extra.pop("album", None)

    with db.connect() as c:
        c.execute("INSERT OR IGNORE INTO tracks (id, title, stage, created_at, updated_at) "
                  "VALUES (?,?,?,?,?)", (track_id, track_id, "draft", now, now))
        c.execute("""
            INSERT INTO track_platforms (track_id, platform, status, updated_at)
            VALUES (?,?,?,?)
            ON CONFLICT(track_id, platform) DO UPDATE SET status=excluded.status, updated_at=excluded.updated_at
        """, (track_id, platform, status, now))

        sets, vals = [], []
        mapping = {"song_id": "song_id", "song_url": "song_url", "album_id": "album_id",
                   "track_no": "track_no", "duration": "duration", "publish_date": "publish_date",
                   "cover_url": "cover_url", "cover_local": "cover_local", "note": "note",
                   "submitted_at": "submitted_at"}
        for k, col in mapping.items():
            if k in extra and extra[k] is not None:
                sets.append(f"{col} = ?"); vals.append(extra[k])
        if album is not None:
            sets.append("album_name = ?"); vals.append(album)
        if cfg is not None:
            sets.append("config = ?")
            vals.append(cfg if isinstance(cfg, str) else json.dumps(cfg, ensure_ascii=False))
        if sets:
            c.execute(f"UPDATE track_platforms SET {', '.join(sets)} WHERE track_id = ? AND platform = ?",
                      (*vals, track_id, platform))
        c.execute("UPDATE tracks SET updated_at = ? WHERE id = ?", (now, track_id))

    return get_track(track_id) or {}


def summary() -> dict[str, int]:
    """各状态各有几首 —— 看板顶部的计数。一句 GROUP BY，不用把全表拉回来数。"""
    db.init()
    counts = {s: 0 for s in STAGES}
    counts["archived"] = 0
    with db.connect() as c:
        for r in c.execute("SELECT stage, COUNT(*) n FROM tracks GROUP BY stage"):
            counts[r["stage"]] = r["n"]
    return counts


def list_albums(platform: str | None = None) -> list[dict[str, Any]]:
    """
    专辑 + 每张专辑的曲目。

    这个 join 以前是在 web/app.py 里手写的双重循环 —— 换成 SQL 之后
    才叫「查询」，而不是「把两份 JSON 读进内存自己配对」。
    """
    db.init()
    with db.connect() as c:
        q = "SELECT * FROM albums"
        args: tuple = ()
        if platform:
            q += " WHERE platform = ?"
            args = (platform,)
        q += " ORDER BY publish_date DESC"
        albums = [dict(r) for r in c.execute(q, args).fetchall()]

        for a in albums:
            a["tracks"] = [
                {"id": r["track_id"], "title": r["title"], "no": r["track_no"],
                 "duration": r["duration"], "url": r["song_url"]}
                for r in c.execute("""
                    SELECT tp.track_id, t.title, tp.track_no, tp.duration, tp.song_url
                    FROM track_platforms tp JOIN tracks t ON t.id = tp.track_id
                    WHERE tp.platform = ? AND tp.album_id = ?
                    ORDER BY COALESCE(tp.track_no, 999)
                """, (a["platform"], a["album_id"])).fetchall()
            ]
            a["cover_api"] = f"/api/album-cover/{a['key']}" if a["cover_local"] else ""
    return albums


def upsert_album(key: str, **fields: Any) -> None:
    """同步脚本用：写一张专辑。"""
    db.init()
    fields.setdefault("synced_at", _now())
    cols = ("platform", "album_id", "title", "track_count", "publish_date", "company",
            "description", "tags", "cover_url", "cover_local", "url", "synced_at")
    given = {k: v for k, v in fields.items() if k in cols}
    with db.connect() as c:
        c.execute(f"""
            INSERT INTO albums (key, {', '.join(given)}) VALUES (?{', ?' * len(given)})
            ON CONFLICT(key) DO UPDATE SET {', '.join(f'{k}=excluded.{k}' for k in given)}
        """, (key, *given.values()))


def list_platform_accounts() -> dict[str, Any]:
    """
    各平台账号资产，并交叉核对「平台自报的歌曲数」和「台账里实际在线数」。

    对不上说明同步漏了或者平台那边有变动 —— 数字自己会说话，
    比在界面上写「同步成功」有用得多。
    """
    db.init()
    with db.connect() as c:
        rows = c.execute("SELECT * FROM platform_accounts").fetchall()
        online = {r["platform"]: r["n"] for r in c.execute(
            "SELECT platform, COUNT(*) n FROM track_platforms "
            "WHERE status IN ('online','published') GROUP BY platform")}
        albums_by = {}
        # albums 的主键是 key（<platform>-<album_id>），不是 id —— 写错列名
        # 会让整个端点 500，而前端只看到「加载失败」
        for r in c.execute("SELECT platform, album_id, title, track_count FROM albums "
                           "ORDER BY publish_date DESC"):
            albums_by.setdefault(r["platform"], []).append(
                {"id": r["album_id"], "name": r["title"], "size": r["track_count"]})

    out = {}
    for r in rows:
        d = dict(r)
        d["alias"] = db._j(r["alias"], []) or []
        d["stats"] = db._j(r["stats"], {}) or {}
        d["albums"] = albums_by.get(r["platform"], [])
        d["local_online_count"] = online.get(r["platform"], 0)
        out[r["platform"]] = d
    return {"accounts": out}


def upsert_platform_account(platform: str, **fields: Any) -> None:
    """同步脚本用：写一个平台账号。"""
    db.init()
    fields.setdefault("synced_at", _now())
    for k in ("alias", "stats"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k], ensure_ascii=False)
    cols = ("label", "artist_id", "artist_name", "alias", "avatar_url", "brief",
            "artist_url", "user_id", "user_url", "song_count", "album_count", "stats", "synced_at")
    given = {k: v for k, v in fields.items() if k in cols}
    with db.connect() as c:
        c.execute(f"""
            INSERT INTO platform_accounts (platform, {', '.join(given)})
            VALUES (?{', ?' * len(given)})
            ON CONFLICT(platform) DO UPDATE SET {', '.join(f'{k}=excluded.{k}' for k in given)}
        """, (platform, *given.values()))


def publication_board() -> dict[str, Any]:
    """按发布账号聚合曲目，同时返回所有歌曲的云备份真值。"""
    tracks = list_tracks()
    accounts = _publish_accounts()
    for account in accounts:
        account["releases"] = [
            {"id": t["id"], "title": t["title"],
             "status": t["platforms"][account["platform"]].get("status", "unknown"),
             "updated_at": t["platforms"][account["platform"]].get("updated_at", ""),
             "cloud_backup": t["cloud_backup"]}
            for t in tracks if account["platform"] in t["platforms"]
        ]
    return {"accounts": accounts, "tracks": tracks}
