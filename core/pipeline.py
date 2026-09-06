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
from core.paths import ARTIST_FILE, DATA_DIR, LEDGER_FILE, PUBLISH_ACCOUNTS_FILE

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
# 这里只登记「支持发到哪」。label 是给人看的名字（QQ 音乐不要写成「腾讯系」）。
PLATFORMS = {
    "qishui": {
        "label": "汽水音乐", "cover": "1440x1440", "ai_field": "创作方式=AI",
        "console": "https://music.douyin.com/console", "color": "#2EE6D6",
    },
    "netease": {
        "label": "网易云音乐", "cover": "1400x1400", "ai_field": "AI 音乐人身份",
        "console": "https://music.163.com/musician", "color": "#EC4141",
    },
    "tencent": {
        "label": "QQ音乐", "cover": "待确认", "ai_field": "待确认",
        "console": "https://y.qq.com/musician", "color": "#31C27C",
    },
}

DEFAULT_PUBLISH_ACCOUNTS = [
    {"id": "qishui-main", "platform": "qishui", "label": "汽水音乐账号"},
    {"id": "netease-main", "platform": "netease", "label": "网易云音乐人账号"},
    {"id": "tencent-main", "platform": "tencent", "label": "QQ音乐账号"},
]

# artist.json 的 platform_profiles 用中文名；库和 API 用 qishui/netease/tencent。
# 两边都认，避免档案里写「QQ音乐」就对不上账号。
_PROFILE_KEY = {
    "qishui": "qishui", "汽水音乐": "qishui", "汽水": "qishui",
    "netease": "netease", "网易云音乐": "netease", "网易云": "netease",
    "tencent": "tencent", "QQ音乐": "tencent", "腾讯音乐人": "tencent",
    "腾讯系": "tencent", "腾讯音乐": "tencent", "腾讯音乐（QQ 音乐）": "tencent",
}

# 艺人档案里的角色键 → 界面上的短标签。顺序即展示顺序。
_ROLE_LABELS = (
    ("performer", "唱"),
    ("lyricist", "词"),
    ("composer", "曲"),
    ("producer", "制作"),
    ("album_artist", "专辑歌手"),
)

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


def _artist_identity() -> dict[str, Any]:
    """艺名与各平台主页。真源 artist.json；读不到就空，不编数据。"""
    empty: dict[str, Any] = {"stage_name": "", "roles": [], "profiles": {}}
    try:
        data = json.loads(ARTIST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return empty
    if not isinstance(data, dict):
        return empty
    profiles: dict[str, dict[str, Any]] = {}
    for p in data.get("platform_profiles") or []:
        if not isinstance(p, dict):
            continue
        key = p.get("key") or _PROFILE_KEY.get(str(p.get("platform") or ""))
        if key in PLATFORMS:
            profiles[key] = p
    roles = data.get("roles") if isinstance(data.get("roles"), dict) else {}
    role_tags = [label for field, label in _ROLE_LABELS if roles.get(field)]
    return {
        "stage_name": str(data.get("stage_name") or ""),
        "roles": role_tags,
        "profiles": profiles,
    }


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


def _row_to_track(row, platforms: dict[str, Any],
                  listings: list[dict[str, Any]] | None = None) -> dict[str, Any]:
    """一行 tracks + 它的平台状态 → 前端吃的那个结构。"""
    listings = listings or [
        {"platform": pk, **info} for pk, info in (platforms or {}).items()
    ]
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
        # 这个作品是不是「原曲」（Suno/本地音频），还是平台回填出来的孤儿。
        # 发行页拿它决定要不要显示「关联原曲」。
        "is_source": bool(row["clip_id"] or row["audio_file"]),
        "listings": listings,
        # 发出去的身份。title 是生成名，可以重复；release_title 必须唯一。
        "release_title": (row["release_title"] if "release_title" in row.keys() else "") or "",
        "release_platform": (row["release_platform"] if "release_platform" in row.keys() else "") or "",
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
    keys = r.keys() if hasattr(r, "keys") else []
    out = {
        "id": r["id"] if "id" in keys else None,
        "platform": r["platform"] if "platform" in keys else "",
        "platform_title": (r["platform_title"] if "platform_title" in keys else "") or "",
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


def _group_listings(plat_rows) -> tuple[dict[str, dict[str, Any]], dict[str, list]]:
    """平台记录按作品归堆。platforms 仍是「每平台一条」给旧 UI；listings 是全部。"""
    by_track: dict[str, dict[str, Any]] = {}
    listings_by: dict[str, list] = {}
    for r in plat_rows:
        row = _platform_row(r)
        listings_by.setdefault(r["track_id"], []).append(row)
        slot = by_track.setdefault(r["track_id"], {})
        if r["platform"] not in slot:
            slot[r["platform"]] = row
    return by_track, listings_by


def list_tracks() -> list[dict[str, Any]]:
    """所有作品，按最近更新排序。前端看板直接吃这个。"""
    db.init()
    with db.connect() as c:
        rows = c.execute("SELECT * FROM tracks ORDER BY updated_at DESC").fetchall()
        plat_rows = c.execute("SELECT * FROM track_platforms").fetchall()

    by_track, listings_by = _group_listings(plat_rows)
    return [_row_to_track(r, by_track.get(r["id"], {}), listings_by.get(r["id"], [])) for r in rows]


def get_track(track_id: str) -> dict[str, Any] | None:
    """单首作品。看板点进详情用，不用把全表拉回来再过滤。"""
    db.init()
    with db.connect() as c:
        row = c.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
        if not row:
            return None
        plat_rows = c.execute(
            "SELECT * FROM track_platforms WHERE track_id = ?", (track_id,)).fetchall()
    by_track, listings_by = _group_listings(plat_rows)
    return _row_to_track(row, by_track.get(track_id, {}), listings_by.get(track_id, []))


def upsert(track_id: str, **fields: Any) -> dict[str, Any]:
    """新建或更新一首作品。只写传进来的字段，不覆盖其余。"""
    db.init()
    now = _now()
    # clip_ids / cloud_backup 是 JSON 列，进库前要序列化
    for k in ("clip_ids", "cloud_backup"):
        if k in fields and not isinstance(fields[k], str):
            fields[k] = json.dumps(fields[k], ensure_ascii=False)

    cols = ("title", "stage", "lyrics", "tags", "prompt", "album_desc", "voice",
            "clip_id", "clip_ids", "audio_file", "cover_file", "note", "cloud_backup",
            "release_title", "release_platform")
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


ACTIVE_RELEASE = ("preparing", "uploaded", "reviewing", "online", "published")


def _plat_label(platform: str) -> str:
    return (PLATFORMS.get(platform) or {}).get("label", platform)


def find_title_owner(title: str, except_id: str = "") -> dict[str, str] | None:
    """谁占用了这个发行歌名。空串不算占用。"""
    title = (title or "").strip()
    if not title:
        return None
    db.init()
    with db.connect() as c:
        r = c.execute(
            "SELECT id, title FROM tracks WHERE release_title=? AND id!=?",
            (title, except_id)).fetchone()
        if r:
            return {"id": r["id"], "title": r["title"] or title}
        r = c.execute(
            """
            SELECT t.id, t.title FROM track_platforms p
            JOIN tracks t ON t.id = p.track_id
            WHERE p.platform_title=? AND p.status IN ({})
              AND t.id!=?
            LIMIT 1
            """.format(",".join("?" * len(ACTIVE_RELEASE))),
            (title, *ACTIVE_RELEASE, except_id),
        ).fetchone()
        if r:
            return {"id": r["id"], "title": r["title"] or title}
    return None


def submit_release(track_id: str, platform: str, release_title: str) -> dict[str, Any]:
    """
    人点「确认发版」。独家授权 + 发行歌名唯一。

    - 一首只能投一个平台（再投是违约）
    - 发出去的歌名全局唯一（Suno 生成名可以重复）
    - 发行歌名一旦定下就必须统一
    """
    if platform not in PLATFORMS:
        raise ValueError(f"未知平台: {platform}")
    title = (release_title or "").strip()
    if not title:
        raise ValueError("发行歌名不能空。Suno 生成名可以重复，发出去的必须唯一。")

    track = get_track(track_id)
    if not track:
        raise ValueError(f"没有这首作品: {track_id}")

    already_plat = track.get("release_platform") or ""
    already_title = track.get("release_title") or ""
    if already_plat and already_plat != platform:
        raise ValueError(
            f"独家授权：已发往{_plat_label(already_plat)}，不能再发到{_plat_label(platform)}")
    if already_title and already_title != title:
        raise ValueError(f"发行歌名已定为「{already_title}」，必须统一，不能改成「{title}」")

    owner = find_title_owner(title, except_id=track_id)
    if owner:
        raise ValueError(f"发行歌名「{title}」已被「{owner['title']}」占用，发出去的歌名必须唯一")

    upsert(track_id, release_title=title, release_platform=platform)
    return set_platform_status(track_id, platform, "preparing", platform_title=title)


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
    记录某条平台上架记录。

    身份是 (platform, song_id)，不是歌名。同一首本地作品可以挂多条
    （改名、拆成完整版/片段），对不上的先作为孤儿挂着，再人手关联。
    """
    if platform not in PLATFORMS:
        raise ValueError(f"未知平台: {platform}")
    db.init()
    now = _now()
    cfg = extra.pop("config", None)
    album = extra.pop("album", None)
    platform_title = extra.pop("platform_title", None)
    song_id = str(extra.get("song_id") or "")

    with db.connect() as c:
        c.execute("INSERT OR IGNORE INTO tracks (id, title, stage, created_at, updated_at) "
                  "VALUES (?,?,?,?,?)", (track_id, track_id, "draft", now, now))

        listing = None
        if song_id:
            listing = c.execute(
                "SELECT id, track_id FROM track_platforms WHERE platform=? AND song_id=?",
                (platform, song_id)).fetchone()
        if listing is None:
            listing = c.execute(
                "SELECT id, track_id FROM track_platforms "
                "WHERE track_id=? AND platform=? AND IFNULL(song_id,'')=?",
                (track_id, platform, song_id)).fetchone()

        if listing:
            lid = listing["id"]
            c.execute("UPDATE track_platforms SET status=?, updated_at=? WHERE id=?",
                      (status, now, lid))
            if listing["track_id"] != track_id:
                c.execute("UPDATE track_platforms SET track_id=? WHERE id=?", (track_id, lid))
        else:
            c.execute(
                "INSERT INTO track_platforms (track_id, platform, status, updated_at) "
                "VALUES (?,?,?,?)", (track_id, platform, status, now))
            lid = c.execute("SELECT last_insert_rowid()").fetchone()[0]

        sets, vals = [], []
        mapping = {"song_id": "song_id", "song_url": "song_url", "album_id": "album_id",
                   "track_no": "track_no", "duration": "duration", "publish_date": "publish_date",
                   "cover_url": "cover_url", "cover_local": "cover_local", "note": "note",
                   "submitted_at": "submitted_at",
                   "plays": "plays", "earned_cny": "earned_cny", "stats_at": "stats_at"}
        for k, col in mapping.items():
            if k in extra and extra[k] is not None:
                sets.append(f"{col} = ?"); vals.append(extra[k])
        if album is not None:
            sets.append("album_name = ?"); vals.append(album)
        if platform_title is not None:
            sets.append("platform_title = ?"); vals.append(platform_title)
        if cfg is not None:
            sets.append("config = ?")
            vals.append(cfg if isinstance(cfg, str) else json.dumps(cfg, ensure_ascii=False))
        if sets:
            c.execute(f"UPDATE track_platforms SET {', '.join(sets)} WHERE id = ?",
                      (*vals, lid))
        c.execute("UPDATE tracks SET updated_at = ? WHERE id = ?", (now, track_id))

    return get_track(track_id) or {}


def link_listing(listing_id: int, track_id: str) -> dict[str, Any]:
    """
    把一条平台上架记录挂到某首本地/Suno 作品上。

    发行歌名必须跟原曲统一；同一平台不能挂第二条（独家不能重复发）。
    汽水分发到别的平台、歌名相同，可以挂。
    """
    db.init()
    now = _now()
    dest = get_track(track_id)
    if not dest:
        raise ValueError(f"没有这首作品: {track_id}")
    with db.connect() as c:
        listing = c.execute("SELECT * FROM track_platforms WHERE id=?", (listing_id,)).fetchone()
        if not listing:
            raise ValueError(f"没有这条上架记录: {listing_id}")

        listing_title = (listing["platform_title"] or "").strip()
        dest_rt = (dest.get("release_title") or "").strip()
        dest_rp = dest.get("release_platform") or ""

        same_plat = [l for l in (dest.get("listings") or [])
                     if l.get("platform") == listing["platform"] and l.get("id") != listing_id]
        if same_plat:
            raise ValueError(
                f"独家授权：这首在{_plat_label(listing['platform'])}已经有一条发行记录，不能再挂")

        if dest_rt and listing_title and dest_rt != listing_title:
            raise ValueError(
                f"发行歌名必须统一：原曲是「{dest_rt}」，这条是「{listing_title}」")

        check_title = dest_rt or listing_title
        if check_title:
            owner = find_title_owner(check_title, except_id=track_id)
            if owner and owner["id"] != listing["track_id"]:
                raise ValueError(
                    f"发行歌名「{check_title}」已被「{owner['title']}」占用")

        old_tid = listing["track_id"]
        c.execute("UPDATE track_platforms SET track_id=?, updated_at=? WHERE id=?",
                  (track_id, now, listing_id))
        if not dest_rt and listing_title:
            c.execute("UPDATE tracks SET release_title=? WHERE id=?", (listing_title, track_id))
        if not dest_rp:
            c.execute("UPDATE tracks SET release_platform=? WHERE id=?",
                      (listing["platform"], track_id))
        c.execute("UPDATE tracks SET updated_at=? WHERE id=?", (now, track_id))
        if old_tid != track_id:
            leftover = c.execute(
                "SELECT COUNT(*) n FROM track_platforms WHERE track_id=?", (old_tid,)).fetchone()["n"]
            old = c.execute(
                "SELECT clip_id, audio_file, note FROM tracks WHERE id=?", (old_tid,)).fetchone()
            empty_shell = (
                leftover == 0
                and old
                and not old["clip_id"]
                and not old["audio_file"]
                and "回填" in (old["note"] or "")
            )
            if empty_shell:
                c.execute("DELETE FROM tracks WHERE id=?", (old_tid,))
    return get_track(track_id) or {}


def resolve_track_for_listing(platform: str, song_id: str, title: str) -> str | None:
    """
    给一条平台上架记录找本地作品。顺序：

    1. 这个 (platform, song_id) 已经挂过 → 沿用，避免重跑同步把人手关联冲掉
    2. 本地有同名作品，优先带 Suno clip / 本地音频的那首（拆成多首同名时挂到原曲）
    3. 找不到 → None，调用方再建孤儿
    """
    db.init()
    title = (title or "").strip()
    with db.connect() as c:
        if song_id:
            hit = c.execute(
                "SELECT track_id FROM track_platforms WHERE platform=? AND song_id=?",
                (platform, str(song_id))).fetchone()
            if hit:
                return hit["track_id"]
        if title:
            hit = c.execute(
                "SELECT id FROM tracks WHERE release_title=?", (title,)).fetchone()
            if hit:
                return hit["id"]
            rows = list(c.execute(
                "SELECT id, clip_id, audio_file FROM tracks WHERE title=?", (title,)))
        else:
            rows = []
    if not rows:
        return None
    sourced = [r for r in rows if r["clip_id"] or r["audio_file"]]
    # 生成名可以重复：同名原曲超过一首就不敢自动挂，留给人手点。
    if len(sourced) > 1:
        return None
    return (sourced[0] if sourced else rows[0])["id"]


def source_candidates() -> list[dict[str, Any]]:
    """能当「原曲」被关联的作品：有 Suno clip 或本地音频。"""
    db.init()
    with db.connect() as c:
        rows = c.execute(
            "SELECT id, title, clip_id, audio_file, stage, "
            "release_title, release_platform FROM tracks "
            "WHERE IFNULL(clip_id,'') != '' OR IFNULL(audio_file,'') != '' "
            "ORDER BY updated_at DESC"
        ).fetchall()
    return [{"id": r["id"], "title": r["title"], "clip_id": r["clip_id"] or "",
             "stage": r["stage"], "suno": bool(r["clip_id"]),
             "release_title": r["release_title"] or "",
             "release_platform": r["release_platform"] or ""} for r in rows]


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

    **三个平台始终都返回**，哪怕还没跑过同步脚本。身份来自 artist.json
    （艺名、主页），统计来自 platform_accounts 表。汽水没同步过后台时，
    界面仍能看到「月栖洲 / 汽水音乐」，而不是整页「未接入」。
    """
    db.init()
    identity = _artist_identity()
    with db.connect() as c:
        rows = {r["platform"]: dict(r) for r in c.execute("SELECT * FROM platform_accounts")}
        online = {r["platform"]: r["n"] for r in c.execute(
            "SELECT platform, COUNT(*) n FROM track_platforms "
            "WHERE status IN ('online','published') GROUP BY platform")}
        listed = {r["platform"]: r["n"] for r in c.execute(
            "SELECT platform, COUNT(*) n FROM track_platforms GROUP BY platform")}
        albums_by: dict[str, list] = {}
        # albums 的主键是 key（<platform>-<album_id>），不是 id —— 写错列名
        # 会让整个端点 500，而前端只看到「加载失败」
        for r in c.execute("SELECT platform, album_id, title, track_count FROM albums "
                           "ORDER BY publish_date DESC"):
            albums_by.setdefault(r["platform"], []).append(
                {"id": r["album_id"], "name": r["title"], "size": r["track_count"]})

    out: dict[str, Any] = {}
    for key, meta in PLATFORMS.items():
        row = rows.get(key) or {}
        profile = identity["profiles"].get(key) or {}
        artist_name = (row.get("artist_name") or identity["stage_name"] or "").strip()
        artist_url = (row.get("artist_url") or profile.get("artist_url") or "").strip()
        user_url = (row.get("user_url") or profile.get("user_url") or "").strip()
        synced_at = row.get("synced_at") or ""
        out[key] = {
            "platform": key,
            "label": meta["label"],
            "artist_id": row.get("artist_id") or profile.get("artist_id") or "",
            "artist_name": artist_name,
            "alias": db._j(row.get("alias"), []) or [],
            "avatar_url": row.get("avatar_url") or "",
            "brief": row.get("brief") or "",
            "artist_url": artist_url,
            "user_id": row.get("user_id") or profile.get("user_id") or "",
            "user_url": user_url,
            "song_count": int(row["song_count"] or 0) if row.get("song_count") is not None else 0,
            "album_count": int(row["album_count"] or 0) if row.get("album_count") is not None else 0,
            "stats": db._j(row.get("stats"), {}) or {},
            "albums": albums_by.get(key, []),
            "local_online_count": online.get(key, 0),
            "local_listed_count": listed.get(key, 0),
            "synced_at": synced_at,
            "synced": bool(synced_at),
            "console_url": meta.get("console") or "",
            "color": meta.get("color") or "",
        }
    return {
        "accounts": out,
        "stage_name": identity["stage_name"],
        "roles": identity["roles"],
    }


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
