"""
从网易云拉回已发布作品，回填到本地台账。

    VF_BASE=$PWD browser-harness < scripts/sync_netease.py

## 为什么需要「回填」

台账记的是**我们这边的动作**（写了词、出了歌、确认发版），但歌一旦上了平台，
真实状态就归平台了 —— 审核过没过、什么时候上架、在哪张专辑里，本地不知道。
不回填的话台账会越来越假：《雪夜无名》《落雪》在网易云早就上架了，
本地却还停在「已出歌」。

## 为什么走 API 不解析页面

网易云的艺人页做了**反爬字符插入** —— 歌名里夹随机汉字，
「雪夜无名」在 DOM 里是「雪·要治提·夜无名」。解析页面等于跟这套投毒机制赛跑。
而 `/api/artist/{id}` 返回的是干净 JSON，同一份数据、没有毒。
能拿数据源就别解析渲染结果。

## 匹配策略

按标题匹配本地台账：
- **匹配上** → 补一条 netease 平台状态（online），不动本地的流程阶段
- **没匹配上** → 新登记一条，标记来源是网易云回填

不做模糊匹配。宁可多登记一条让人自己合并，也不能把两首不同的歌并成一首 ——
那种错误发现时数据已经混了。
"""

import json
import os
import re
import time
from pathlib import Path

BASE = Path(os.environ.get("VF_BASE") or Path.cwd()).resolve()
ARTIST_ID = os.environ.get("VF_NCM_ARTIST", "32462959")
# 个人主页和艺人主页是**两个不同的 id**，用途也不同：
#   艺人主页 artist?id=  → 平台核实音乐人身份用，发布表单填这个
#   个人主页 user/home?id= → 你的听歌/动态页，个人展示用
# 两个都记，用错一个平台核实时会说「证明不了音乐人身份」。
USER_ID = os.environ.get("VF_NCM_USER", "116974627")

DATA_DIR = Path(os.environ.get("VOXFLOW_HOME") or (Path.home() / ".voxflow"))
LEDGER = DATA_DIR / "configs" / "pipeline.json"
ACCOUNTS = DATA_DIR / "configs" / "platform_accounts.json"

print(f"艺人 ID: {ARTIST_ID}")

raw = js(f"""(async () => {{
  const get = async (u) => {{
    const res = await fetch(u, {{ credentials: 'include' }})
    return await res.json()
  }}
  const a = await get('https://music.163.com/api/artist/{ARTIST_ID}')
  const al = await get('https://music.163.com/api/artist/albums/{ARTIST_ID}?limit=100')
  return {{
    artist: a.artist ? {{
      id: a.artist.id, name: a.artist.name, alias: a.artist.alias,
      musicSize: a.artist.musicSize, albumSize: a.artist.albumSize,
    }} : null,
    songs: (a.hotSongs || []).map(s => ({{
      id: s.id, name: s.name, album: s.album?.name,
      duration: Math.round((s.duration || 0) / 1000),
      publishTime: s.album?.publishTime,
    }})),
    albums: (al.hotAlbums || []).map(x => ({{
      id: x.id, name: x.name, size: x.size, publishTime: x.publishTime,
    }})),
  }}
}})()""")

if not raw or not raw.get("artist"):
    print("✗ 没拿到艺人数据 —— 检查是不是被登录墙拦了")
    raise SystemExit(1)

art = raw["artist"]
songs = raw["songs"]
albums = raw["albums"]
print(f"✓ {art['name']}（{'/'.join(art.get('alias') or [])}）  {art['musicSize']} 首 · {art['albumSize']} 张专辑")

# ── 平台账号台账 ──────────────────────────────────────────
ACCOUNTS.parent.mkdir(parents=True, exist_ok=True)
acc = json.loads(ACCOUNTS.read_text(encoding="utf-8")) if ACCOUNTS.exists() else {"accounts": {}}
acc.setdefault("accounts", {})["netease"] = {
    "platform": "网易云音乐",
    "artist_id": art["id"],
    "artist_name": art["name"],
    "alias": art.get("alias") or [],
    "artist_url": f"https://music.163.com/#/artist?id={art['id']}",
    "user_id": USER_ID,
    "user_url": f"https://music.163.com/#/user/home?id={USER_ID}",
    "_两个链接的区别": "artist_url 是艺人主页（发布表单填它，平台据此核实音乐人身份）；"
                       "user_url 是个人主页（听歌记录、动态），证明不了音乐人身份。",
    "song_count": art["musicSize"],
    "album_count": art["albumSize"],
    "albums": [{"name": a["name"], "size": a["size"]} for a in albums],
    "synced_at": time.strftime("%Y-%m-%dT%H:%M:%S"),
    "_来源": "公开 API /api/artist/{id}，不需要登录；音乐人后台（收益、审核状态）才要登录",
}
# ── 音乐人后台指标（要登录）─────────────────────────────
# 公开 API 只有作品目录，播放量、粉丝、收益这些**只有后台有**。
# 后台是个 SPA，数据渲染在页面上没有稳定的公开接口 —— 只能从文本里抠。
# 这段会随平台改版失效，失效就是抓不到（返回 None），不会写坏已有数据。
print("\n抓音乐人后台指标…")
new_tab("https://music.163.com/musician/artist/home")
time.sleep(9)
stats = js("""(() => {
  const txt = document.body.innerText
  const g = (re) => { const m = txt.match(re); return m ? m[1] : null }
  return {
    play_count: g(/播放量[^\\d]*([\\d.]+[wW万]?)/),
    fans: g(/粉丝\\s*\\n\\s*([\\d.]+[wW万]?)/),
    works: g(/作品\\(首\\)\\s*\\n\\s*(\\d+)/),
    withdrawable_cny: g(/可提现税前收益\\(元\\)[^\\d]*([\\d.]+)/),
    musician_index: g(/音乐人指数\\s*\\n\\s*(\\d+)/),
    play_7d: g(/近7日播放量\\s*([\\d.]+)\\s*次/),
    play_yesterday_delta: g(/昨日新增\\s*[↑↓]?\\s*(\\d+)/),
    roles: g(/网易音乐人\\s*\\n\\s*([^\\n]{0,20})/),
  }
})()""")

if stats and stats.get("works"):
    acc["accounts"]["netease"]["stats"] = {**stats, "synced_at": time.strftime("%Y-%m-%dT%H:%M:%S")}
    print(f"  播放 {stats['play_count']}（昨日+{stats['play_yesterday_delta']}）· "
          f"粉丝 {stats['fans']} · 作品 {stats['works']} 首 · "
          f"可提现 {stats['withdrawable_cny']} 元 · 指数 {stats['musician_index']}")
else:
    print("  ✗ 抓不到后台指标（没登录？或者平台改版了）—— 不影响作品目录同步")

ACCOUNTS.write_text(json.dumps(acc, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"✓ 平台账号台账已更新：{ACCOUNTS}")

# ── 回填作品台账 ──────────────────────────────────────────
ledger = json.loads(LEDGER.read_text(encoding="utf-8")) if LEDGER.exists() else {"tracks": {}}
tracks = ledger.setdefault("tracks", {})
by_title = {(t.get("title") or "").strip(): tid for tid, t in tracks.items()}

matched, added = [], []
now = time.strftime("%Y-%m-%dT%H:%M:%S")

for s in songs:
    title = s["name"].strip()
    tid = by_title.get(title)
    if not tid:
        # 没匹配上就新建。id 用标题生成，跟本地新歌一个规则
        tid = re.sub(r"[^\w一-鿿]+", "-", title).strip("-").lower() or f"ncm-{s['id']}"
        tracks[tid] = {
            "title": title,
            "stage": "published",     # 平台上有 = 已上架，这是事实不是推测
            "note": "从网易云回填",
        }
        added.append(title)
    else:
        matched.append(title)

    t = tracks[tid]
    # 平台状态直接写「已上架」—— 它在平台上能播，这是最硬的事实。
    # 但**不动 stage**：本地流程阶段是我们自己的进度记录，
    # 平台上架不代表本地那套流程走完了（比如物料可能还没归档）。
    plats = t.setdefault("platforms", {})
    plats["netease"] = {
        "status": "online",
        "song_id": s["id"],
        "album": s.get("album"),
        "url": f"https://music.163.com/#/song?id={s['id']}",
        "duration": s.get("duration"),
        "updated_at": now,
        "note": "网易云回填",
    }
    t.setdefault("updated_at", now)

LEDGER.write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"✓ 作品台账已回填：匹配 {len(matched)} 首、新增 {len(added)} 首")
if matched:
    print(f"  匹配上的：{'、'.join(matched[:6])}{' …' if len(matched) > 6 else ''}")
if added:
    print(f"  新登记的：{'、'.join(added[:8])}{' …' if len(added) > 8 else ''}")
