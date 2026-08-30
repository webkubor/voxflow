#!/usr/bin/env python3
"""
从 QQ 音乐同步账号、专辑、作品到本地台账。

    .venv/bin/python scripts/sync_qq.py

## 渠道：musicu.fcg（为什么不用别的）

QQ 音乐没有网易云那种干净的单端点公开 API。旧的 c.y.qq.com v8 fcg 端点
已 404 废弃（实测）。现在网页端走 `u.y.qq.com/cgi-bin/musicu.fcg`，
POST/GET 一个 JSON 信封，module/method 指定业务模块 —— 跨域友好、无需登录：

- 歌手搜索：`music.search.SearchCgiService/DoSearchForQQMusicDesktop`
- 歌手歌曲：`musichall.song_list_server/GetSingerSongList`
- 歌手专辑：`music.musichallAlbum.AlbumListServer/GetAlbumList`

歌手 mid 从艺人主页 URL 拿（`y.qq.com/n/ryqq_v2/singer/{mid}`），
默认 002Rcy0a0YpQ7L，可用 `VF_QQ_MID` 覆盖。

## 平台键

QQ 音乐属于腾讯音乐系，台账的 platform 键用 **tencent**（腾讯系），
与全网发行面板的「腾讯系」入口一致 —— 平台键列表见 core/pipeline.py 的
PLATFORMS。

## 匹配策略（照 sync_netease.py）

按标题精确匹配：匹配上补平台状态，没匹配上新登记。不动本地 stage。
幂等，可随时重跑。
"""

from __future__ import annotations

import json
import os
import re
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import pipeline as P                      # noqa: E402
from core.paths import DATA_DIR                     # noqa: E402

SINGER_MID = os.environ.get("VF_QQ_MID", "002Rcy0a0YpQ7L")
COVER_DIR = DATA_DIR / "library" / "covers" / "qq"
NOW = time.strftime("%Y-%m-%dT%H:%M:%S")
UA = "Mozilla/5.0"


def musicu(modules: dict) -> dict:
    """调用 musicu.fcg。modules 是 {信封键: {module, method, param}}。"""
    payload = {"comm": {"ct": 24}, **modules}
    data = urllib.parse.quote(json.dumps(payload, ensure_ascii=False), safe="")
    url = f"https://u.y.qq.com/cgi-bin/musicu.fcg?format=json&data={data}"
    req = urllib.request.Request(url, headers={"User-Agent": UA, "Referer": "https://y.qq.com/"})
    with urllib.request.urlopen(req, timeout=30) as r:
        return json.loads(r.read().decode())


def get_singer_songs(mid: str, begin: int = 0, num: int = 50) -> list[dict]:
    resp = musicu({"singer": {
        "module": "musichall.song_list_server", "method": "GetSingerSongList",
        "param": {"singerMid": mid, "begin": begin, "num": num}}})
    return (resp.get("singer", {}).get("data", {}).get("songList") or [])


def get_albums(mid: str, begin: int = 0, num: int = 50) -> list[dict]:
    resp = musicu({"alb": {
        "module": "music.musichallAlbum.AlbumListServer", "method": "GetAlbumList",
        "param": {"singerMid": mid, "begin": begin, "num": num}}})
    data = resp.get("alb", {}).get("data", {})
    return data.get("albumList") or data.get("list") or []


def get_singer_info(mid: str) -> dict:
    """歌手信息：名字从歌曲列表反推，头像 URL 按 mid 构造。

    不依赖搜索接口 —— 实测 `SearchCgiService/DoSearchForQQMusicDesktop`
    对同一 query 时好时坏（同样的参数有时返回歌手、有时整包空），
    get_singer_detail_info 对这个小歌手也是空的。而歌曲列表一定带歌手名，
    头像 URL 规律固定：https://y.qq.com/music/photo_new/T001R150x150M000{mid}_2.jpg
    """
    resp = musicu({"singer": {
        "module": "musichall.song_list_server", "method": "GetSingerSongList",
        "param": {"singerMid": mid, "begin": 0, "num": 5}}})
    data = resp.get("singer", {}).get("data", {})
    songs = data.get("songList") or []
    name = ""
    for s in songs:
        singers = (s.get("songInfo", {}) or {}).get("singer") or []
        if singers:
            name = singers[0].get("name", "")
            break
    return {
        "singerName": name or mid,
        "singerMID": mid,
        "songNum": data.get("totalNum", 0),
        "singerPic": f"https://y.qq.com/music/photo_new/T001R150x150M000{mid}_2.jpg",
    }


def ymd(s: str) -> str:
    return s[:10] if s else ""


def main() -> None:
    # 先拿专辑（数量从这来），再拿歌手信息（名字/歌曲数/头像）
    albums = get_albums(SINGER_MID)
    info = get_singer_info(SINGER_MID)
    name = info.get("singerName", "?")
    print(f"✓ 歌手：{name}（{info.get('songNum', 0)} 首 · {len(albums)} 张专辑）")

    # ── 1. 歌手头像 + 专辑封面下到本地（平台图床会变会失效）──
    COVER_DIR.mkdir(parents=True, exist_ok=True)
    singer_pic = info.get("singerPic", "").replace("http://", "https://")
    avatar_dst = COVER_DIR / f"singer_{SINGER_MID}.jpg"
    if singer_pic and not avatar_dst.exists():
        try:
            req = urllib.request.Request(singer_pic, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r, open(avatar_dst, "wb") as f:
                f.write(r.read())
        except Exception as e:                       # noqa: BLE001
            print(f"  ⚠ 头像下载失败: {str(e)[:40]}")

    # ── 2. 专辑入库 ──
    got_cover = 0
    for al in albums:
        amid = al.get("albumMid") or ""
        if not amid:
            continue
        cover = COVER_DIR / f"{amid}.jpg"
        if not cover.exists():
            url = f"https://y.qq.com/music/photo_new/T002R300x300M000{amid}.jpg"
            try:
                req = urllib.request.Request(url, headers={"User-Agent": UA})
                with urllib.request.urlopen(req, timeout=30) as r, open(cover, "wb") as f:
                    f.write(r.read())
                got_cover += 1
            except Exception:                        # noqa: BLE001
                pass
        P.upsert_album(
            f"qq-{amid}", platform="tencent", album_id=amid,
            title=al.get("albumName") or al.get("name") or "",
            track_count=al.get("songNum") or 0,
            publish_date=ymd(al.get("publicTime") or al.get("time_public") or ""),
            cover_url=f"https://y.qq.com/music/photo_new/T002R300x300M000{amid}.jpg",
            cover_local=str(cover.relative_to(DATA_DIR)) if cover.exists() else "",
            url=f"https://y.qq.com/n/ryqq/albumDetail/{amid}",
            synced_at=NOW,
        )
    print(f"✓ 专辑 {len(albums)} 张入库（封面新下 {got_cover}）")

    # ── 3. 账号入库（platform=tencent，腾讯系）──
    P.upsert_platform_account(
        "tencent",
        label="腾讯音乐（QQ 音乐）", artist_id=SINGER_MID,
        artist_name=name, alias=[], avatar_url=singer_pic,
        brief="", artist_url=f"https://y.qq.com/n/ryqq_v2/singer/{SINGER_MID}",
        song_count=info.get("songNum", 0), album_count=len(albums),
        synced_at=NOW,
    )
    print("✓ 账号入库（tencent / 腾讯系）")

    # ── 4. 作品回填 ──
    songs = get_singer_songs(SINGER_MID)
    existing = {t["title"].strip(): t["id"] for t in P.list_tracks()}
    matched, added = [], []
    for s in songs:
        si = s.get("songInfo", {})
        title = (si.get("name") or "").strip()
        if not title:
            continue
        tid = existing.get(title)
        if not tid:
            tid = re.sub(r"[^\w一-鿿]+", "-", title).strip("-").lower() or f"qq-{si.get('id')}"
            P.upsert(tid, title=title, stage="published", note="从 QQ 音乐回填")
            added.append(title)
        else:
            matched.append(title)

        album = si.get("album") or {}
        amid = album.get("mid") or ""
        cover = COVER_DIR / f"{amid}.jpg"
        P.set_platform_status(
            tid, "tencent", "online",
            song_id=str(si.get("id") or ""),
            song_url=f"https://y.qq.com/n/ryqq/songDetail/{si.get('mid')}",
            album_id=str(album.get("id") or ""), album=album.get("name") or "",
            track_no=si.get("num"), duration=round((si.get("interval") or 0)),
            publish_date=ymd(album.get("time_public") or ""),
            cover_url=f"https://y.qq.com/music/photo_new/T002R300x300M000{amid}.jpg" if amid else "",
            cover_local=str(cover.relative_to(DATA_DIR)) if cover.exists() else "",
            note="QQ 音乐回填",
        )
        t = P.get_track(tid)
        if t and not t.get("cover_file") and cover.exists():
            P.upsert(tid, cover_file=str(cover.relative_to(DATA_DIR)))

    print(f"✓ 作品回填：匹配 {len(matched)} 首、新增 {len(added)} 首")
    for title in added:
        print(f"    新增：{title}")


if __name__ == "__main__":
    main()
