#!/usr/bin/env python3
"""
从网易云同步账号、专辑、作品到本地台账。

    .venv/bin/python scripts/sync_netease.py

## 为什么这个脚本不需要浏览器

一开始我把它写成 browser-harness 脚本，结果作品目录也跟着受浏览器跨域限制的
连累 —— fetch 必须在同源页面下发，标签页一飘就 Failed to fetch。
后来发现**公开 API 用 curl 直接就能拿**，压根没有理由绕浏览器。

两条数据通道，抗风险程度差很多：

| 数据 | 通道 | 要登录 | 稳定性 |
|---|---|---|---|
| 艺人、专辑、作品目录 | 公开 API `/api/artist/{id}` | 否 | 纯 HTTP，稳 |
| 播放量、粉丝、收益、指数 | 音乐人后台页面 | **是** | 随改版失效 |

拆开之后日常同步一条命令跑完，只有想更新播放量时才开浏览器
（`scripts/ncm_stats.py`）。

## 为什么不解析艺人页

网易云对艺人页做了**反爬字符插入** —— 歌名里夹随机汉字，「雪夜无名」在 DOM
里是「雪·要治提·夜无名」。而同一份数据在 API 里是干净 JSON。
**能拿数据源就别解析渲染结果。**

## 匹配策略

按标题精确匹配，**不做模糊匹配**：匹配上补平台状态，没匹配上新登记。
宁可多登记一条让人自己合并，也不能把两首不同的歌并成一首 ——
那种错误等发现时数据已经混了。

补平台状态时**不动本地 stage**：平台上架是平台的事实，本地流程阶段是
我们自己的进度记录，两者不是一回事。

幂等，可以随时重跑。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import pipeline as P                      # noqa: E402
from core.paths import DATA_DIR                     # noqa: E402

ARTIST_ID = os.environ.get("VF_NCM_ARTIST", "32462959")
# 个人主页和艺人主页是**两个不同的 id**：
#   artist?id=    艺人主页 → 发布表单填它，平台据此核实音乐人身份
#   user/home?id= 个人主页 → 听歌记录/动态，证明不了音乐人身份
USER_ID = os.environ.get("VF_NCM_USER", "116974627")

COVER_DIR = DATA_DIR / "library" / "covers" / "netease"
NOW = time.strftime("%Y-%m-%dT%H:%M:%S")


def fetch(url: str) -> dict:
    """网易云公开接口。必须带 Referer —— 不带会被当盗链拒掉。"""
    req = urllib.request.Request(url, headers={
        "User-Agent": "Mozilla/5.0",
        "Referer": "https://music.163.com/",
    })
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def ymd(ms) -> str:
    return time.strftime("%Y-%m-%d", time.localtime(ms / 1000)) if ms else ""


# ── 1. 艺人 + 作品 + 专辑 ─────────────────────────────────
print(f"艺人 {ARTIST_ID} —— 拉作品目录")
a_resp = fetch(f"https://music.163.com/api/artist/{ARTIST_ID}")
al_resp = fetch(f"https://music.163.com/api/artist/albums/{ARTIST_ID}?limit=100")

art = a_resp.get("artist")
if not art:
    print("✗ 拿不到艺人数据")
    raise SystemExit(1)

songs = a_resp.get("hotSongs") or []
albums = al_resp.get("hotAlbums") or []
print(f"✓ {art['name']}（{'/'.join(art.get('alias') or [])}）  "
      f"{art['musicSize']} 首 · {art['albumSize']} 张专辑")

# ── 2. 封面下到本地 ───────────────────────────────────────
# 平台图床 URL 会变会失效，而封面是发别的平台要复用的物料。
# 只存 URL 等于把资产押在别人的 CDN 上。
COVER_DIR.mkdir(parents=True, exist_ok=True)
got = 0
for al in albums:
    if not al.get("picUrl"):
        continue
    dst = COVER_DIR / f"{al['id']}.jpg"
    if dst.exists():
        continue
    for attempt in range(3):        # 网易云图床偶发 SSL 断连，重试就好
        try:
            req = urllib.request.Request(al["picUrl"], headers={"User-Agent": "VoxFlow/0.3.0"})
            with urllib.request.urlopen(req, timeout=30) as r, open(dst, "wb") as f:
                f.write(r.read())
            got += 1
            break
        except Exception as e:
            if attempt == 2:
                print(f"  ✗ 封面 {al['name']}：{str(e)[:40]}")
            time.sleep(1)
print(f"✓ 封面：新下 {got} 张，本地共 {len(list(COVER_DIR.glob('*.jpg')))} 张")

# ── 3. 专辑入库 ───────────────────────────────────────────
for al in albums:
    cover = COVER_DIR / f"{al['id']}.jpg"
    P.upsert_album(
        f"netease-{al['id']}",
        platform="netease", album_id=str(al["id"]), title=al["name"],
        track_count=al.get("size", 0), publish_date=ymd(al.get("publishTime")),
        company=al.get("company") or "",
        description=(al.get("description") or "")[:500],
        tags=al.get("tags") or "", cover_url=al.get("picUrl") or "",
        cover_local=str(cover.relative_to(DATA_DIR)) if cover.exists() else "",
        url=f"https://music.163.com/#/album?id={al['id']}", synced_at=NOW,
    )
print(f"\n✓ 专辑 {len(albums)} 张入库：")
for al in albums:
    cv = "✓" if (COVER_DIR / f"{al['id']}.jpg").exists() else "✗"
    print(f"    {al['name']:20} {al.get('size', 0):>2} 首  {ymd(al.get('publishTime'))}  封面={cv}")

# ── 4. 账号入库 ───────────────────────────────────────────
# 不传 stats —— 播放量那些只有后台有，由 scripts/ncm_stats.py 单独更新。
# 这里传空会把已抓到的指标冲掉，所以干脆不传这个字段。
P.upsert_platform_account(
    "netease",
    label="网易云音乐", artist_id=str(art["id"]), artist_name=art["name"],
    alias=art.get("alias") or [], avatar_url=art.get("picUrl") or "",
    brief=art.get("briefDesc") or "",
    artist_url=f"https://music.163.com/#/artist?id={art['id']}",
    user_id=USER_ID, user_url=f"https://music.163.com/#/user/home?id={USER_ID}",
    song_count=art["musicSize"], album_count=art["albumSize"], synced_at=NOW,
)
print("✓ 账号入库")

# ── 5. 作品回填 ───────────────────────────────────────────
existing = {t["title"].strip(): t["id"] for t in P.list_tracks()}
matched, added = [], []
for s in songs:
    title = s["name"].strip()
    tid = existing.get(title)
    if not tid:
        tid = re.sub(r"[^\w一-鿿]+", "-", title).strip("-").lower() or f"ncm-{s['id']}"
        P.upsert(tid, title=title, stage="published", note="从网易云回填")
        added.append(title)
    else:
        matched.append(title)

    album = s.get("album") or {}
    cover = COVER_DIR / f"{album.get('id')}.jpg"
    has_cover = cover.exists()
    P.set_platform_status(
        tid, "netease", "online",
        song_id=str(s["id"]),
        song_url=f"https://music.163.com/#/song?id={s['id']}",
        album_id=str(album.get("id") or ""), album=album.get("name") or "",
        track_no=s.get("no"), duration=round((s.get("duration") or 0) / 1000),
        publish_date=ymd(album.get("publishTime")),
        cover_url=album.get("picUrl") or "",
        cover_local=str(cover.relative_to(DATA_DIR)) if has_cover else "",
        note="网易云回填",
    )
    # 本地没封面的用平台封面兜底 —— 总比看板上一片空白强
    t = P.get_track(tid)
    if t and not t.get("cover_file") and has_cover:
        P.upsert(tid, cover_file=str(cover.relative_to(DATA_DIR)))

print(f"✓ 作品回填：匹配 {len(matched)} 首、新增 {len(added)} 首")
