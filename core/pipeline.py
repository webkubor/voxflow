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
# 这里只登记「支持发到哪」。
def _load_platforms() -> dict[str, dict[str, Any]]:
    """平台清单 —— **唯一真源是 `configs/platforms.json`**。

    这里曾经是一份写死的 dict，和那份 JSON 重复。重复的代价不是「不好看」，
    是**没人能回答「到底支持几个平台」** —— 2026-09-06 就因此在第四处
    又编出了酷狗/酷我/B站三个根本不存在的平台，还写进了飞书表的选项里。

    JSON 那份才配当真源：它有表单字段、封面尺寸、AI 声明方式、控制台地址，
    是实际探过页面得到的。代码这边只需要 label 和封面尺寸，从它派生即可。

    加平台 = 改那份 JSON，不动代码。
    """
    from core.paths import CONFIG_DIR, PLATFORMS_FILE
    out: dict[str, dict[str, Any]] = {}
    for f in (CONFIG_DIR / "platforms.json", PLATFORMS_FILE):
        if not f.exists():
            continue
        try:
            raw = json.loads(f.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        for key, spec in raw.items():
            if key.startswith("_") or not isinstance(spec, dict):
                continue        # `_说明` 这类注释键不是平台
            out[key] = {
                "label": spec.get("label", key),
                "cover": (spec.get("cover") or {}).get("min_size", "待确认"),
                "ai_field": (spec.get("ai_declaration") or {}).get("field", "待确认")
                            if isinstance(spec.get("ai_declaration"), dict)
                            else (spec.get("ai_declaration") or "待确认"),
                "console": (spec.get("entries", {}).get("single", {}) or {}).get("url")
                           or spec.get("console", ""),
            }
        if out:
            break               # 用户目录那份优先，找到就不再看项目内置的
    return out


PLATFORMS = _load_platforms()

# 账号占位由平台清单派生 —— 不再手抄一遍平台名
DEFAULT_PUBLISH_ACCOUNTS = [
    {"id": f"{k}-main", "platform": k, "label": f"{v['label']}账号"}
    for k, v in PLATFORMS.items()
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
        "duration": (row["duration"] if "duration" in row.keys() else None),
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
        # 三个来源各有各的用处，所以三个都给，前端不用自己拼：
        #   suno_url  —— 云端原件，能看生成参数、能在 Suno 里再加工
        #   r2_url    —— 公网直链，发给别人下载（本地路径对别人没意义）
        #   audio_url —— 本机文件，最快、离线也能听
        # 拼 URL 这件事放前端做，拼错了是静默 404 —— 点了没反应、不报错。
        "suno_url": f"https://suno.com/song/{row['clip_id']}" if row["clip_id"] else "",
        "r2_url": backup.get("location", "") if str(
            backup.get("location", "")).startswith("http") else "",
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
        # 谁负责发这首 —— 看板要靠它做「只看我负责的」筛选。
        # 曲库有两百多首（Suno 云端全量同步进来的），不筛的话人得在里面
        # 找自己那两首，找错了就是替别人发了歌。
        "publisher": (r["publisher"] if "publisher" in keys else "") or "",
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
            "release_title", "release_platform", "duration")
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
                "SELECT id, track_id, status FROM track_platforms "
                "WHERE track_id=? AND platform=? AND IFNULL(song_id,'')=?",
                (track_id, platform, song_id)).fetchone()
        if listing is None and song_id:
            # 提交时还没有平台 id，后来核对后台才拿到 —— 补到原记录上，
            # 不要再插一条，否则同一首歌在同一平台出现两条。
            listing = c.execute(
                "SELECT id, track_id, status FROM track_platforms "
                "WHERE track_id=? AND platform=? AND IFNULL(song_id,'')='' "
                "ORDER BY id LIMIT 1",
                (track_id, platform)).fetchone()

        # 记下变更前的状态 —— 事件流要「从哪到哪」，只有「到哪」没意义
        _before = listing["status"] if listing else ""
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

    # 状态真变了才记事件、才推通知 —— 每次写都推的话，
    # 一次同步几十首就是几十条通知，群里会被刷爆，之后没人再看。
    if _before != status:
        log_event(track_id, platform, status, from_status=_before)
        _notify_status_change(track_id, platform, _before, status)

    # 写完平台状态就把阶段带上 —— 两套存储各写各的，正是它们此前
    # 互相矛盾的原因（已上架的歌还在流水线里排队，反过来也有）。
    # 收在这个唯一写入点，同步脚本和 UI 都自动受益。
    _sync_stage_from_platforms(track_id)
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


def _seconds(value: Any) -> int | None:
    """时长统一成整秒。0 / 空 / 坏值都当成「没有」，不能拿去匹配。"""
    if value is None or value == "":
        return None
    try:
        n = int(round(float(value)))
    except (TypeError, ValueError):
        return None
    return n if n > 0 else None


def _match_by_duration(c, seconds: int) -> str | None:
    """
    歌名对不上（改过名）时，用时长认原曲。

    人改歌名，几乎不改音频 —— 生成多长，发出去就是多长。
    只在「带 Suno clip / 本地音频、且这个时长只对应一首」时才自动挂；
    两首一样长就不敢猜。
    """
    rows = list(c.execute(
        "SELECT id FROM tracks "
        "WHERE duration IS NOT NULL "
        "AND ABS(duration - ?) <= 1 "
        "AND (IFNULL(clip_id,'') != '' OR IFNULL(audio_file,'') != '')",
        (seconds,)))
    if len(rows) == 1:
        return rows[0]["id"]
    return None


def resolve_track_for_listing(platform: str, song_id: str, title: str,
                              duration: Any = None) -> str | None:
    """
    给一条平台上架记录找本地作品。顺序：

    1. 这个 (platform, song_id) 已经挂过 → 沿用，避免重跑同步把人手关联冲掉
    2. 发行歌名对得上
    3. 生成歌名对得上，且只有一首原曲（同名超过一首就不敢自动挂）
    4. 歌名对不上或同名多首 → 用时长（±1 秒）在原曲里唯一命中
    5. 找不到 → None，调用方再建孤儿
    """
    db.init()
    title = (title or "").strip()
    seconds = _seconds(duration)
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
                "SELECT id, clip_id, audio_file, duration FROM tracks WHERE title=?",
                (title,)))
        else:
            rows = []
        sourced = [r for r in rows if r["clip_id"] or r["audio_file"]]
        if len(sourced) == 1:
            return sourced[0]["id"]
        if len(sourced) > 1:
            if seconds is not None:
                by_dur = [r for r in sourced
                          if _seconds(r["duration"]) is not None
                          and abs(int(_seconds(r["duration"])) - seconds) <= 1]
                if len(by_dur) == 1:
                    return by_dur[0]["id"]
            return None
        if rows:
            return rows[0]["id"]
        if seconds is not None:
            return _match_by_duration(c, seconds)
    return None


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


# ─────────────────────── 备料检查 ───────────────────────
#
# 「备料中」原本是个**空状态** —— 点了确认发版就写上它，然后什么也不发生，
# 也没有任何东西告诉你备料算不算完、下一步该点哪里。链路就断在这儿。
#
# 这里把它变成一份**可核对的清单**：这首歌发这个平台还缺什么，
# 每一项缺了怎么补。全绿了才谈得上「去发布」。
#
# 清单项来自 `configs/platforms.json` 里实测的表单字段，不在这里硬编码平台规则 ——
# 平台改版时改那份配置，这段逻辑不用动。


def _artist_profile() -> dict[str, Any]:
    from core.paths import ARTIST_FILE
    try:
        return json.loads(ARTIST_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}


def readiness(track_id: str, platform: str) -> dict[str, Any]:
    """这首歌发这个平台，备料齐了没有。

    返回 {ok, items: [{名称, 就绪, 说明}], 缺口数}
    """
    track = get_track(track_id)
    if not track:
        return {"ok": False, "items": [], "错误": "曲目不存在"}
    spec = (_platform_specs() or {}).get(platform) or {}
    artist = _artist_profile()
    cover_min = spec.get("cover", {}).get("min_size", "1440x1440")

    def item(name: str, ok: bool, hint: str) -> dict[str, Any]:
        return {"名称": name, "就绪": bool(ok), "说明": "" if ok else hint}

    # 封面必须真的够大 —— Suno 自带的是 360×360，放大是糊的，
    # 「有封面」和「封面能用」是两回事，只判存在会在上传时被平台打回。
    cover_ok = bool(track.get("cover_url")) and _cover_big_enough(track_id, cover_min)
    items = [
        item("完整版音频", bool(track.get("audio_url")),
             "曲库里没有音频文件 —— 先在 AI 音乐那屏生成或补录"),
        item(f"专辑封面 ≥{cover_min}", cover_ok,
             f"缺封面或尺寸不足 {cover_min}（Suno 自带的 360×360 不能用）· 点「出封面」"),
        item("歌词", bool(track.get("lyrics")), "歌词为空 —— 在详情里补，平台必填"),
        item("歌曲标题", bool((track.get("title") or "").strip()), "标题为空"),
        item("专辑名称", bool(_album_name_of(track, platform)),
             "没有专辑名 —— 单曲也要填，可以和歌名一致"),
        item("艺名（表演者/词曲作者）", bool(artist.get("stage_name")),
             "artist.json 里没有 stage_name"),
        item("法律姓名（版权登记用）", bool(artist.get("real_name")),
             "artist.json 里没有 real_name —— 结算要它，艺名不能替"),
    ]
    missing = [i for i in items if not i["就绪"]]
    return {
        "ok": not missing,
        "items": items,
        "缺口数": len(missing),
        "平台": spec.get("label", platform),
        "控制台": (spec.get("entries", {}).get("single", {}) or {}).get("url")
                  or spec.get("console", ""),
        # 备料齐了给出那条真正能把表填完的命令。自动化的价值在填表这 10 分钟，
        # 最后点提交那一秒留给人 —— 提交进审核队列是不可逆的。
        "发布命令": f"VF_BASE=$PWD VF_TRACK={track_id} browser-harness < scripts/publish_{platform}.py"
                    if (Path(__file__).resolve().parent.parent
                        / f"scripts/publish_{platform}.py").exists() else "",
    }


def _platform_specs() -> dict[str, Any]:
    from core.paths import CONFIG_DIR, PROJECT_DIR
    for p in (CONFIG_DIR / "platforms.json", PROJECT_DIR / "configs/platforms.json"):
        if p.exists():
            try:
                return json.loads(p.read_text(encoding="utf-8"))
            except (OSError, json.JSONDecodeError):
                return {}
    return {}


def _album_name_of(track: dict[str, Any], platform: str) -> str:
    info = (track.get("platforms") or {}).get(platform) or {}
    return (info.get("album_name") or track.get("album_desc") or "").strip()


def _cover_big_enough(track_id: str, min_size: str) -> bool:
    """封面短边够不够。读不出尺寸时**放行** —— 宁可让平台去判，
    也不要因为本地缺个图像库就把人卡在这一步。"""
    try:
        need = int(str(min_size).lower().split("x")[0])
    except (ValueError, IndexError):
        return True
    db.init()
    with db.connect() as c:
        row = c.execute("SELECT cover_file FROM tracks WHERE id=?", (track_id,)).fetchone()
    if not row or not row["cover_file"]:
        return False
    try:
        from pathlib import Path as _P
        from core.paths import DATA_DIR
        from PIL import Image
        p = _P(row["cover_file"])
        if not p.is_absolute():
            p = DATA_DIR / p
        with Image.open(p) as im:
            return min(im.size) >= need
    except Exception:      # noqa: BLE001 —— 读不出就不拦
        return True


# ─────────────────── 阶段与平台状态的一致性 ───────────────────
#
# 流水线阶段（tracks.stage）和平台状态（track_platforms.status）是**两套
# 独立的存储**，此前没有任何东西保证它们一致。结果两个方向都错过：
#
#   已上架却还在流水线里排队   4 首（网易云 online，阶段还停在 generated）
#   阶段写着已上架、平台却没发  2 首（一首在备料、一首在审核）
#
# 看板因此回答不了「这歌到底发出去没有」—— 它给的两个答案互相矛盾。
#
# **平台实况是真源**：歌在不在平台上，只有平台说了算。阶段是它的展示，
# 应该跟着走，不该反过来。所以：有平台记录的曲目，阶段由平台状态推导。
#
# 没有任何平台记录的曲目不动 —— draft / generated / selected 是「还没
# 进入发行」的阶段，只有人能判断，推不出来。

# 平台状态 → 流水线阶段。取所有平台里**最靠后**的那个：
# 一首歌在 A 平台已上架、在 B 平台还在审，它整体就是「已发布」。
_STATUS_TO_STAGE = {
    "online": "published",
    "reviewing": "publishing",
    "uploaded": "publishing",
    "preparing": "publishing",   # 备料是发版流程的一部分，不是「还没开始发」
    "rejected": "publishing",    # 被驳回还在发行流程里，只是要返工
}


def release_status_for_title(title: str) -> dict[str, Any] | None:
    """这首歌现在发到哪了。给通知用：任务失败 ≠ 歌没了。

    生成任务的 CLI 常在「下载音频」那步挂（Suno 403），群里就会喊失败。
    可歌早就在库里，甚至已经交到汽水审核。通知必须先问台账。
    """
    title = (title or "").strip()
    if not title:
        return None
    db.init()
    with db.connect() as c:
        rows = c.execute(
            "SELECT t.id, t.title, t.stage, t.release_title, t.release_platform, "
            "p.platform, p.status, p.song_id "
            "FROM tracks t LEFT JOIN track_platforms p ON p.track_id = t.id "
            "WHERE t.title = ? OR IFNULL(t.release_title,'') = ?",
            (title, title),
        ).fetchall()
    if not rows:
        return None
    rank = {"online": 4, "published": 4, "reviewing": 3,
            "uploaded": 2, "preparing": 1, "rejected": 1}
    best = max(rows, key=lambda r: rank.get(r["status"] or "", 0))
    plat = (best["platform"] or best["release_platform"] or "")
    st = best["status"] or ""
    stage = best["stage"] or ""
    label = _plat_label(plat) if plat else ""
    if st in ("online", "published") or stage == "published":
        return {"kind": "online", "label": f"已上架" + (f"（{label}）" if label else ""),
                "platform": plat, "status": st or "online"}
    if st == "reviewing":
        return {"kind": "reviewing",
                "label": f"{label}审核中" if label else "平台审核中",
                "platform": plat, "status": st}
    if st in ("preparing", "uploaded") or stage == "publishing":
        return {"kind": "publishing",
                "label": f"{label}发版中" if label else "发版中（签署/备料）",
                "platform": plat, "status": st or "preparing"}
    return None


def derived_stage(platform_infos: dict[str, Any]) -> str:
    """按平台实况推导阶段。没有平台记录返回空串（表示「推不出来，别动」）。"""
    if not platform_infos:
        return ""
    stages = {_STATUS_TO_STAGE.get((i or {}).get("status", ""), "")
              for i in platform_infos.values()}
    if "published" in stages:
        return "published"
    if "publishing" in stages:
        return "publishing"
    return ""


def reconcile_stages(dry_run: bool = False) -> dict[str, Any]:
    """把阶段和平台实况对齐。返回改动明细。

    幂等：对齐之后再跑一次是 0 改动。
    """
    db.init()
    fixed = []
    with db.connect() as c:
        rows = c.execute("SELECT id, title, stage FROM tracks").fetchall()
        plats = c.execute("SELECT track_id, platform, status FROM track_platforms").fetchall()
    by_track: dict[str, dict[str, Any]] = {}
    for r in plats:
        by_track.setdefault(r["track_id"], {})[r["platform"]] = {"status": r["status"]}

    for r in rows:
        want = derived_stage(by_track.get(r["id"], {}))
        if want and want != r["stage"]:
            fixed.append({"曲名": r["title"], "原阶段": r["stage"], "改为": want})
            if not dry_run:
                set_stage(r["id"], want)
    return {"对齐": len(fixed), "明细": fixed}


def _sync_stage_from_platforms(track_id: str) -> None:
    """某首歌的平台状态变了 → 阶段跟着走。推不出来就不动。"""
    db.init()
    with db.connect() as c:
        rows = c.execute("SELECT platform, status FROM track_platforms WHERE track_id=?",
                         (track_id,)).fetchall()
        cur = c.execute("SELECT stage FROM tracks WHERE id=?", (track_id,)).fetchone()
    want = derived_stage({r["platform"]: {"status": r["status"]} for r in rows})
    if want and cur and want != cur["stage"]:
        set_stage(track_id, want)


def set_publisher(track_id: str, platform: str, name: str,
                  open_id: str = "") -> None:
    """记下这首歌在这个平台**由谁负责发布**。

    为什么本地也要存一份（飞书台账里已经有了）：台账是**对外视图** ——
    别人不给他开数据库，所以要有个地方让大家认领和跟进。但它可能被误删、
    可能哪天不用飞书了，而「谁发的」是要长期追溯的事实：分成归属看它、
    上架出问题找谁也看它。所以真源留在本地。

    收益不往这张表里抄 —— 平台后台的数字是实时的，抄进来就是过期快照。
    """
    db.init()
    now = _now()
    with db.connect() as c:
        # ⚠️ 不能用 `INSERT OR IGNORE`。
        #
        # 这张表的主键早就从 (track_id, platform) 改成了自增 id（见
        # `_migrate_listing_pk`）—— OR IGNORE 靠唯一约束才会「忽略」，
        # 主键一换它就**永远不会触发**，于是每调一次 set_publisher 就多一行。
        # 结果是同一首歌在同一平台出现好几条，看板上一首歌显示两遍、
        # 状态还各不相同（一条备料中一条审核中），人根本不知道信哪个。
        exists = c.execute("SELECT 1 FROM track_platforms WHERE track_id=? AND platform=? LIMIT 1",
                           (track_id, platform)).fetchone()
        if not exists:
            c.execute("INSERT INTO track_platforms (track_id, platform, status, updated_at) "
                      "VALUES (?,?,?,?)", (track_id, platform, "preparing", now))
        c.execute("UPDATE track_platforms SET publisher=?, publisher_id=?, "
                  "assigned_at=COALESCE(NULLIF(assigned_at,''), ?), updated_at=? "
                  "WHERE track_id=? AND platform=?",
                  (name, open_id, now, now, track_id, platform))


def publish_log(limit: int = 50) -> list[dict[str, Any]]:
    """发布记录：哪首歌、发行名、多长、什么平台、谁负责、到哪一步了。

    这是「发歌记录」那一屏和 `voice publish-log` 共用的数据源。
    """
    db.init()
    with db.connect() as c:
        rows = c.execute("""
            SELECT t.id, t.title, t.release_title, t.duration,
                   p.platform, p.status, p.publisher, p.assigned_at,
                   p.album_name, p.publish_date, p.song_url
            FROM track_platforms p JOIN tracks t ON t.id = p.track_id
            ORDER BY COALESCE(NULLIF(p.publish_date,''), p.assigned_at, p.updated_at) DESC
            LIMIT ?""", (limit,)).fetchall()
    out = []
    for r in rows:
        d = int(r["duration"] or 0)
        out.append({
            "曲名": r["title"],
            "发行歌名": r["release_title"] or r["title"],
            "时长": f"{d // 60}:{d % 60:02d}" if d else "",
            "平台": (PLATFORMS.get(r["platform"]) or {}).get("label", r["platform"]),
            "状态": PLATFORM_STATUS_LABELS.get(r["status"], r["status"]),
            "负责人": r["publisher"] or "",
            "专辑": r["album_name"] or "",
            "上架日": r["publish_date"] or "",
            "平台链接": r["song_url"] or "",
        })
    return out


PLATFORM_STATUS_LABELS = {
    "preparing": "备料中", "uploaded": "已上传", "reviewing": "审核中",
    "online": "已上架", "rejected": "被驳回",
}


def album_name_for(track: dict[str, Any], platform: str, batch_size: int = 1) -> str:
    """这次发行该用什么专辑名。

    ## 平台规则，不是我们的偏好

    汽水明写：**「如果专辑内仅有一首歌，专辑名称应与歌曲名称一致」**。
    所以单曲发行时专辑名 = 歌名，没有选择余地 —— 填别的直接卡在第一步，
    而且提示是普通文字挂在字段下面（不是红字），很难注意到。

    想共用一张专辑只有一条路：**同一次提交里放进所有歌**
    （页面上写着「如需代理发行，请创建新专辑并一次性添加所有歌曲，
    发行后不可增删」）。那种情况下 batch_size > 1，才用得上自定义专辑名。

    2026-09-06 在这上面栽过：我按「同一批次共用专辑」把四首都改成
    「破晓时分 · 纯音乐 BGM」，结果单曲提交全被拦。规则只在脑子里，
    没写进代码，就会被下一次的「合理推断」覆盖掉。
    """
    name = (track.get("release_title") or track.get("title") or "").strip()
    if batch_size <= 1:
        return name
    info = (track.get("platforms") or {}).get(platform) or {}
    return (info.get("album") or track.get("album_desc") or name).strip()


def prepare(track_id: str, platform: str, *, album: str = "",
            publisher: str = "", publisher_id: str = "",
            instrumental: bool = False) -> dict[str, Any]:
    """把一首歌推进「备料中」，能自动补的字段一次补齐。

    ## 为什么要有这一步

    导入/生成完之后，人还得手动点「确认发版」、挑平台、填专辑名、
    标歌词 —— 这些**机器全都知道**：平台是配置里定的，专辑名可以承继，
    纯音乐的歌词就是 `[Instrumental]`。让人点五下再开始干活，
    等于把自动化省下的时间又还回去。

    ## 什么不自动做

    **出封面不在这里** —— 它花钱（museav 1 积分/张 ≈ ¥0.83）。
    自动化可以省事，但不能替人做花钱的决定：一次导入 20 首就是 20 块，
    而人可能只想先试一首。所以这里只把「缺封面」报出来，
    出不出由调用方显式决定。
    """
    track = get_track(track_id)
    if not track:
        return {"ok": False, "错误": "曲目不存在"}
    if platform not in PLATFORMS:
        return {"ok": False, "错误": f"未知平台 {platform}"}

    fields: dict[str, Any] = {}
    if album and not (track.get("album_desc") or "").strip():
        fields["album_desc"] = album
    # 纯音乐的歌词不是「没填」，是「就是没有」—— 平台必填这一栏，
    # 空着会被打回，标准写法是 [Instrumental]。
    if instrumental and not (track.get("lyrics") or "").strip():
        fields["lyrics"] = "[Instrumental]"
    if fields:
        upsert(track_id, **fields)

    # 专辑名走统一规则，不再由调用方随手传 —— 见 album_name_for 的注释
    set_platform_status(track_id, platform, "preparing",
                        album=album_name_for(track, platform))
    if publisher:
        set_publisher(track_id, platform, publisher, publisher_id)

    r = readiness(track_id, platform)
    # 把「还缺什么」直接回给调用方 —— 备料的意义就在于**知道还差哪几步**，
    # 只说一句「已进入备料」等于什么都没说。
    return {"ok": True, "备料齐了": r["ok"], "缺口数": r["缺口数"],
            "缺": [i["名称"] for i in r["items"] if not i["就绪"]],
            "需要出封面": any("封面" in i["名称"] for i in r["items"] if not i["就绪"]),
            "发布命令": r.get("发布命令", ""), "控制台": r.get("控制台", "")}



# ─────────────────── 发布事件流 ───────────────────

def log_event(track_id: str, platform: str, to_status: str, *,
              from_status: str = "", actor: str = "", note: str = "") -> None:
    """记一条状态变更。**不抛异常** —— 记不上不该拦住业务。

    为什么要有事件流：`status` 字段只说「现在在哪」，不说「怎么来的」。
    「这首歌卡了几天」「上次谁推进的」「驳回过几次」——
    这几个运营最常问的问题，单看 status 一个都答不了。
    """
    try:
        db.init()
        with db.connect() as c:
            c.execute("INSERT INTO publish_events "
                      "(track_id, platform, from_status, to_status, actor, note, ts) "
                      "VALUES (?,?,?,?,?,?,?)",
                      (track_id, platform, from_status, to_status, actor, note, _now()))
    except Exception as e:  # noqa: BLE001
        obs.log("publish_event_failed", level="warn", error=str(e)[:120])


def events(track_id: str = "", limit: int = 50) -> list[dict[str, Any]]:
    """事件流。不传 track_id 就是全局最近的。"""
    db.init()
    sql = ("SELECT e.*, t.title, t.release_title FROM publish_events e "
           "LEFT JOIN tracks t ON t.id = e.track_id ")
    args: list[Any] = []
    if track_id:
        sql += "WHERE e.track_id = ? "
        args.append(track_id)
    sql += "ORDER BY e.id DESC LIMIT ?"
    args.append(limit)
    with db.connect() as c:
        rows = c.execute(sql, args).fetchall()
    return [{
        "曲目": r["release_title"] or r["title"] or r["track_id"][:8],
        "平台": (PLATFORMS.get(r["platform"]) or {}).get("label", r["platform"]),
        "从": PLATFORM_STATUS_LABELS.get(r["from_status"], r["from_status"] or "—"),
        "到": PLATFORM_STATUS_LABELS.get(r["to_status"], r["to_status"]),
        "谁": r["actor"] or "",
        "备注": r["note"] or "",
        "时间": r["ts"],
    } for r in rows]


def _notify_status_change(track_id: str, platform: str, before: str, after: str) -> None:
    """状态变了推一条群通知。**吞掉所有异常** —— 通知挂了不能拦住业务。

    只推**人需要行动或需要知道**的那几个状态：
    进入审核（要开始等）、上架（可以看数据了）、驳回（要返工）。
    「备料中」这种自己刚点出来的不推 —— 人刚点完就收到通知，纯噪音。
    """
    INTERESTING = {"reviewing": ("⏳ 已提交审核", "warn"),
                   "online": ("🎉 已上架", "done"),
                   "rejected": ("❌ 被驳回", "error")}
    if after not in INTERESTING:
        return
    try:
        from core import notify

        t = get_track(track_id) or {}
        info = (t.get("platforms") or {}).get(platform) or {}
        d = int(t.get("duration") or info.get("duration") or 0)
        title, level = INTERESTING[after]
        notify.notify(
            f"{title}：{t.get('release_title') or t.get('title') or track_id[:8]}",
            {"平台": (PLATFORMS.get(platform) or {}).get("label", platform),
             "负责人": info.get("publisher", ""),
             "时长": f"{d // 60}:{d % 60:02d}" if d else "",
             "专辑": info.get("album", ""),
             "变更": f"{PLATFORM_STATUS_LABELS.get(before, before or '新建')} → "
                     f"{PLATFORM_STATUS_LABELS.get(after, after)}"},
            level=level, event=f"status_{after}",
            dedupe_key=f"vf-st-{track_id}-{platform}-{after}",
        )
    except Exception as e:  # noqa: BLE001
        obs.log("status_notify_failed", level="warn", error=str(e)[:120])


def record_login(platform: str, ok: bool, *, detail: str = "", account: str = "") -> None:
    """记下某个平台的登录核验结果。

    ## 为什么要存

    登录态本身在浏览器里，存不下来 —— 存的是**「最后一次核验的结果和时间」**。
    有了它，界面上才能说「3 分钟前验过，已登录」，而不是每次进页面都重跑一次
    （跑一次要开浏览器、几秒钟，还可能弹 Chrome 的调试授权框）。

    `account` 是账号名。平台后台的 DOM 里不一定抓得到（藏在下拉菜单里，
    而且平台改版就失效），所以**抓不到就让人填一次**，之后复用 ——
    比每次靠选择器去猜可靠得多。
    """
    db.init()
    now = _now()
    with db.connect() as c:
        c.execute("INSERT OR IGNORE INTO platform_accounts (platform, label, synced_at) "
                  "VALUES (?,?,?)",
                  (platform, (PLATFORMS.get(platform) or {}).get("label", platform), ""))
        sets = ["login_status = ?", "login_detail = ?", "login_checked_at = ?"]
        vals = ["connected" if ok else "expired", detail[:200], now]
        if account:
            sets.append("artist_name = ?"); vals.append(account)
        c.execute(f"UPDATE platform_accounts SET {', '.join(sets)} WHERE platform = ?",
                  (*vals, platform))


def login_state(platform: str) -> dict[str, Any]:
    """上次核验的登录结果。没验过就返回 unknown —— 不猜。"""
    db.init()
    with db.connect() as c:
        r = c.execute("SELECT login_status, login_detail, login_checked_at, artist_name "
                      "FROM platform_accounts WHERE platform=?", (platform,)).fetchone()
    if not r or not (r["login_checked_at"] if "login_checked_at" in r.keys() else ""):
        return {"status": "unknown", "label": "没验过", "checked_at": "", "account": ""}
    st = r["login_status"] or "unknown"
    return {"status": st, "label": LOGIN_STATUS_LABELS.get(st, st),
            "detail": r["login_detail"] or "", "checked_at": r["login_checked_at"],
            "account": r["artist_name"] or ""}
