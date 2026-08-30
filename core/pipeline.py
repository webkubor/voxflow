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

BASE_DIR = Path(__file__).resolve().parent.parent
LEDGER = BASE_DIR / "configs" / "pipeline.json"
PUBLISH_ACCOUNTS = BASE_DIR / "configs" / "publish_accounts.json"

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


def _load() -> dict[str, Any]:
    if not LEDGER.exists():
        return {"tracks": {}}
    try:
        return json.loads(LEDGER.read_text(encoding="utf-8"))
    except Exception:
        # 台账坏了不能让整个应用起不来 —— 返回空的，用户至少还能用其它功能
        return {"tracks": {}}


def _save(data: dict[str, Any]) -> None:
    LEDGER.parent.mkdir(parents=True, exist_ok=True)
    LEDGER.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def _backup_record(track: dict[str, Any]) -> dict[str, str]:
    backup = track.get("cloud_backup") or {}
    status = backup.get("status", "unrecorded")
    return {
        "status": status,
        "label": BACKUP_STATUS_LABELS.get(status, status),
        "location": backup.get("location", ""),
        "updated_at": backup.get("updated_at", ""),
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


def list_tracks() -> list[dict[str, Any]]:
    """所有作品，按最近更新排序。前端看板直接吃这个。"""
    data = _load()
    tracks = []
    for tid, t in data.get("tracks", {}).items():
        stage = t.get("stage", "draft")
        tracks.append({
            "id": tid,
            "title": t.get("title") or "未命名",
            "stage": stage,
            "stage_label": STAGE_LABELS.get(stage, stage),
            "stage_index": STAGES.index(stage) if stage in STAGES else -1,
            "voice": t.get("voice"),          # 用了哪个音色
            "clip_id": t.get("clip_id"),      # Suno 的 clip
            "clip_ids": t.get("clip_ids", []),   # 一次出两首，两个都留着
            "platforms": t.get("platforms", {}),
            "cloud_backup": _backup_record(t),
            "updated_at": t.get("updated_at", ""),
            "note": t.get("note", ""),
            # ── 创作元数据 ──
            # 歌本身的内容，跟流程状态无关，但必须留底：平台发布时歌词是必填项、
            # 风格标签影响推荐，出了问题要复现也得靠这些。
            # 不能只留在 Suno 云端和文件名里 —— 那边不归我们，账号一停或者
            # 对方改版就没了；文件名更是只能塞下一个标题。
            "lyrics": t.get("lyrics", ""),
            "tags": t.get("tags", ""),       # 送给 Suno 的风格串
            "prompt": t.get("prompt", ""),   # 让 LLM 写歌词时给的描述
            "audio_file": t.get("audio_file", ""),
            "cover_file": t.get("cover_file", ""),
        })
    tracks.sort(key=lambda x: x["updated_at"], reverse=True)
    return tracks


def publication_board() -> dict[str, Any]:
    """按发布账号聚合曲目，同时返回所有歌曲的云备份真值。"""
    tracks = list_tracks()
    accounts = _publish_accounts()
    for account in accounts:
        releases = []
        for track in tracks:
            release = track["platforms"].get(account["platform"])
            if release is None:
                continue
            status = release.get("status", "unknown")
            releases.append({
                "id": track["id"],
                "title": track["title"],
                "status": status,
                "updated_at": release.get("updated_at", ""),
                "cloud_backup": track["cloud_backup"],
            })
        account["releases"] = releases
    return {"accounts": accounts, "tracks": tracks}


def upsert(track_id: str, **fields: Any) -> dict[str, Any]:
    """新建或更新一首作品。只写传进来的字段，不覆盖其余。"""
    data = _load()
    t = data.setdefault("tracks", {}).setdefault(track_id, {"stage": "draft"})
    for k, v in fields.items():
        if v is not None:
            t[k] = v
    t["updated_at"] = _now()
    _save(data)
    return t


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
    """
    if platform not in PLATFORMS:
        raise ValueError(f"未知平台: {platform}")
    data = _load()
    t = data.setdefault("tracks", {}).setdefault(track_id, {"stage": "draft"})
    p = t.setdefault("platforms", {}).setdefault(platform, {})
    p["status"] = status
    p["updated_at"] = _now()
    p.update({k: v for k, v in extra.items() if v is not None})
    t["updated_at"] = _now()
    _save(data)
    return t


def summary() -> dict[str, int]:
    """各状态各有几首 —— 看板顶部的计数。"""
    counts = {s: 0 for s in STAGES}
    counts["archived"] = 0
    for t in list_tracks():
        counts[t["stage"]] = counts.get(t["stage"], 0) + 1
    return counts
