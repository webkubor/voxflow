"""
作品状态 —— 「每首歌生成到哪一步了」的唯一真源。

## 边界（2026-10-10 拆分后）

**本模块只管生成侧**：一首歌从草稿到出歌、选定。发行（发到哪个平台、审核状态、
上架台账、专辑、平台账号）整体迁到了独立仓
[suno-publisher](https://github.com/webkubor/suno-publisher) —— 那边有自己的
sqlite 和 releases / listings / albums / platform_accounts / publish_events 五张表。

所以这里**不再有** platform 概念：没有 `PLATFORMS`、没有 `track_platforms`
查询、没有 `release_title`。VoxFlow 通过 `/api/catalog/*` 向发行侧提供
「生成了什么」，发行侧自己算「什么该发」。

## 为什么需要它

在此之前，每首歌的状态只能靠「文件存不存在」倒推 —— 而倒推有两个问题：

1. **推不出用户的意图**。文件在 out/ 下只说明生成过，不代表用户选定了要留。
2. **推不出失败**。生成中断、下载失败，文件系统里看不出来。

所以状态要显式记录。这个文件管的就是那份台账。

## 状态机

    draft ──→ generated ──→ selected
    草稿      已出歌        已选定
                              │
                              └──→ archived（弃用）

- **generated → selected 是人的决定**：Suno 一次出两首，得听过才知道要哪首

（`publishing` / `published` 两个状态是拆分前的遗留值，老库里存在，所以
`STAGES` 仍然认得它们；但本模块不再产生这两个状态 —— 发行进度看 suno-publisher。）

## 为什么不用数据库

台账规模是「几十到几百首」，一个 JSON 足够，而且可读、可手改、可进 git diff。
上数据库会引入迁移、连接、备份三件事，收益为零。
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from core import db
from core.paths import DATA_DIR, LEDGER_FILE

BASE_DIR = DATA_DIR          # 台账里的相对路径都是相对数据根
LEDGER = LEDGER_FILE

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

# 这里只登记「支持发到哪」。


# artist.json 的 platform_profiles 用中文名；库和 API 用 qishui/netease/tencent。
# 两边都认，避免档案里写「QQ音乐」就对不上账号。

# 艺人档案里的角色键 → 界面上的短标签。顺序即展示顺序。


BACKUP_STATUS_LABELS = {
    "backed_up": "已云备份",
    "syncing": "同步中",
    "failed": "备份失败",
    "unrecorded": "未登记",
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


def _row_to_track(row) -> dict[str, Any]:
    """一行 tracks → 前端吃的那个结构。

    2026-10-10 发行拆分后不再带 `platforms` / `listings` / `is_source` /
    `release_title` / `release_platform` —— 那些是发行侧的事实，已经归
    suno-publisher（它有自己的 listings / releases 表）。这里只描述「生成了什么」。
    """
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


def list_tracks() -> list[dict[str, Any]]:
    """所有作品，按最近更新排序。前端看板直接吃这个。"""
    db.init()
    with db.connect() as c:
        rows = c.execute("SELECT * FROM tracks ORDER BY updated_at DESC").fetchall()
    return [_row_to_track(r) for r in rows]


def get_track(track_id: str) -> dict[str, Any] | None:
    """单首作品。看板点进详情用，不用把全表拉回来再过滤。"""
    db.init()
    with db.connect() as c:
        row = c.execute("SELECT * FROM tracks WHERE id = ?", (track_id,)).fetchone()
    if not row:
        return None
    return _row_to_track(row)


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


# ══════════════════════════════════════════════════════════════════════
# 发行能力已迁往 suno-publisher（2026-10-10）
#
# 这些函数原本在 voxflow 里管「把曲库的歌发到音乐平台」：发行身份锁定、
# 上架状态流转、专辑与平台账号台账、备料检查、事件流。全部搬到了
# github.com/webkubor/suno-publisher，连同四张表（track_platforms /
# albums / platform_accounts / publish_events）和那份平台发行知识。
#
# 为什么搬：voxflow 的定位收敛为「纯 AI 音频生成工具」（语音克隆 / 音色设计 /
# 播客 / BGM / Suno 音乐生成），发行是另一件事，混在一起两边都难维护。
#
# ## 现在为什么还留着这些函数
#
# 还没删，因为**有读取方**：/api/release/pending 依赖 publish_fields()，
# 浏览器发行扩展（extension/）也靠那个端点拿元数据和音频。删函数之前必须
# 先让扩展切到 suno-publisher 自己的取数路径，否则插件会当场失联。
#
# 迁移动作与对账记录见 suno-publisher 的 scripts/migrate_from_voxflow.py：
#   60 条上架 = 22 已上市 + 20 无 song_id + 18 其他；47 事件 → 46 + 1 条
#   2026-01 历史数据（三个关联键全空，真孤儿）。
# ══════════════════════════════════════════════════════════════════════


# 改名的门槛线：到了这些状态，歌已经在平台后台了，名字不能再动
# （平台那边的曲目信息已经提交，本地改了只会两边对不上）。


def set_stage(track_id: str, stage: str) -> dict[str, Any]:
    """
    推进状态。**不做自动跃迁** —— 每一步都是显式的。

    尤其是 selected → publishing：那是「我确认要发这首」的决定，
    不能因为「文件齐了」就自动往前走。
    """
    if stage not in STAGES and stage != "archived":
        raise ValueError(f"未知状态: {stage}")
    return upsert(track_id, stage=stage)


def summary() -> dict[str, int]:
    """各状态各有几首 —— 看板顶部的计数。一句 GROUP BY，不用把全表拉回来数。"""
    db.init()
    counts = {s: 0 for s in STAGES}
    counts["archived"] = 0
    with db.connect() as c:
        for r in c.execute("SELECT stage, COUNT(*) n FROM tracks GROUP BY stage"):
            counts[r["stage"]] = r["n"]
    return counts


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


# ─────────────────── 发布事件流 ───────────────────
