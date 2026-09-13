#!/usr/bin/env python3
"""
从汽水音乐（字节系）后台同步作品状态到本地台账。

    .venv/bin/python scripts/sync_qishui.py [--dry-run]

## 为什么需要它

网易云和 QQ 都有公开 API，一条命令就能对账；**只有汽水没有**，
状态一直靠人手记。2026-09-12 的事故就是这么来的：本地把「致命脉冲」
记成 draft、「长安月」记成 preparing，实际两首 09-07 就已经发行了，
错了整整 5 天没人发现 —— 而汽水是单价最高（1.0 元/千播）、
触达最广（字节系 + 全球 150+ 流媒体）的那个通道。

## 为什么走浏览器

汽水后台没有开放 API，登录态在 Cookie 里。ego-browser 直接复用
用户日常浏览器的登录态，不用存密码、不用扫码。

## 只补不改

跟 sync_suno.py 同一个原则：只用云端状态覆盖**平台侧字段**
（状态、发行时间、平台曲名），本地的歌词、封面、收益记录一个字不动。

⚠️ 多账号：汽水按登录的账号显示作品。如果一条本地记录在后台查不到，
**不会**把它改成"未发布" —— 它可能只是在另一个账号下。
查不到的只做提示，绝不动数据。
"""
from __future__ import annotations

import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db, pipeline as P  # noqa: E402

DRY = "--dry-run" in sys.argv

# 后台那几个中文状态 → 本地台账的 status
# 后台那几个中文状态 → 本地台账的 status。
#
# ⚠️「代理发行中」算 **online** 不算 reviewing。它的意思是「已经在汽水可听，
# 同时正由代理商分发到全球 150+ 平台」，不是还在排队等审核 ——
# 2026-09-13 owner 确认。之前映射成 reviewing，导致 7 首已上线的歌
# 在台账和运营台里一直显示「审核中」，收益口径也跟着少算。
#
# 真正没过审的是「审核未通过」，它会连带在列表里显示驳回原因。
STATUS_MAP = {
    "字节系平台已发行": "online",
    "全球已发行": "online",
    "已发行": "online",
    "代理发行中": "online",
    "审核中": "reviewing",
    "发行审核中": "reviewing",
    "审核未通过": "draft",
    "草稿": "draft",
}

_EGO = r"""
// 复用**已经登录汽水**的那个空间 —— ego 的每个任务空间是独立浏览器 profile，
// 登录态不共享。另起一个空间就是未登录状态，只会读到 0 条，
// 而报错长得像「账号不对」，完全看不出是空间选错了。
const spaces = await listTaskSpaces();
let task = null;
for (const s of spaces) {
  try {
    // ownership 有三种值：agent / user / **agentDelegatedToUser**（handOff 之后就是它）。
    // 只判断 === "user" 会漏掉第三种，于是对一个已交还的空间调 taskSpace()，
    // 拿不到页面、静默跳过，最后报「一条作品都没读到」，看着像账号不对。
    const t = s.ownership === "agent"
      ? await taskSpace(s.spaceId ?? s.id)
      : await takeOverTaskSpace(s.spaceId ?? s.id);
    const pg = t.page("p1");
    if ((await pg.url()).includes("music.douyin.com")) { task = t; break; }
  } catch (e) { /* 空间不可用，换下一个 */ }
}
if (!task) task = await taskSpace("qishui publish");
const page = task.page("p1");
await page.goto("https://music.douyin.com/console/songs");
await page.waitForLoadState();
await page.waitForTimeout(6000);

// 这个列表**不是标准 <tr>/<td>**（实测 querySelectorAll("tr") 取不到行），
// 是 div 拼的网格。所以从「状态文案」这个锚点往上找容器，容器的文本就是一整行。
// 好处是不依赖 DOM 标签，平台换布局也不容易断。
const rows = await page.evaluate(() => {
  const STATUS = ["字节系平台已发行", "全球已发行", "已发行", "代理发行中",
                  "发行审核中", "审核中", "审核未通过", "草稿"];
  const out = [];
  const seen = new Set();
  for (const el of document.querySelectorAll("*")) {
    if (el.children.length) continue;
    const txt = (el.textContent || "").trim();
    if (!STATUS.includes(txt)) continue;
    // 往上找到既含状态、又含日期的那一层 —— 那就是一行
    let row = el;
    for (let i = 0; i < 8 && row; i++) {
      const t = row.textContent || "";
      if (t.includes(txt) && /\d{4}-\d{2}-\d{2}/.test(t) && t.length < 400) break;
      row = row.parentElement;
    }
    if (!row) continue;
    const flat = (row.textContent || "").replace(/\s+/g, " ").trim();
    if (seen.has(flat)) continue;
    seen.add(flat);
    const link = row.querySelector('a[href*="/console/songs/detail/"], a[href*="/console/albums/detail/"]');
    // 单元格：把可见的叶子节点按顺序取出来，比切文本可靠
    const cells = [...row.querySelectorAll("*")]
      .filter(e => !e.children.length && (e.textContent || "").trim())
      .map(e => (e.textContent || "").trim());
    out.push({ cells, detail: link ? link.getAttribute("href") : "" });
  }
  return out;
});
console.log("QISHUI:" + JSON.stringify(rows));
"""


def fetch_rows() -> list[dict]:
    env = {**os.environ, "PATH": f"{Path.home()}/.local/bin:" + os.environ.get("PATH", "")}
    p = subprocess.run(["ego-browser", "nodejs"], input=_EGO, capture_output=True,
                       text=True, timeout=300, env=env)
    lines = (p.stdout + "\n" + p.stderr).splitlines()
    line = next((l for l in lines if l.startswith("QISHUI:")), "")
    if not line:
        raise SystemExit(f"读不到后台（ego-browser 没回话）：{(p.stderr or p.stdout)[-400:]}")
    return json.loads(line[len("QISHUI:"):])


def parse(row: dict) -> dict | None:
    """把一行单元格解析成 {title, status, date, url}。列序可能变，按内容认。"""
    cells = row.get("cells") or []
    status = next((STATUS_MAP[c] for c in cells if c in STATUS_MAP), "")
    if not status:
        return None
    date = next((c for c in cells if re.match(r"^\d{4}-\d{2}-\d{2}", c)), "")
    # 曲名：跳过纯数字的序号列、状态列、日期列、地区列
    skip = {"全球", "中国大陆", "查看详情", "修改"}
    names = [c for c in cells
             if c and not c.isdigit() and c not in STATUS_MAP and c not in skip
             and not re.match(r"^\d{4}-\d{2}-\d{2}", c)]
    if not names:
        return None
    detail = row.get("detail") or ""
    # song_id 就在详情链接里（/console/songs/detail/<song_id>）。
    # **必须带上它**：set_platform_status 按 (platform, song_id) 认记录，
    # 不传就匹配不到已有那条，于是新建一条 —— 同一首歌在台账里出现两行、
    # 状态各说各话（实测「逆着风跑起来」被拆成 reviewing + online 两条）。
    m = re.search(r"/detail/(\d+)", detail)
    return {
        "title": names[0],
        "status": status,
        "date": date[:10],
        "song_id": m.group(1) if m else "",
        "url": f"https://music.douyin.com{detail}" if detail.startswith("/") else detail,
    }


def main() -> int:
    db.init()
    rows = [r for r in (parse(r) for r in fetch_rows()) if r]
    if not rows:
        print("后台一条作品都没读到 —— 确认浏览器登录的是要对账的那个汽水账号")
        return 1
    print(f"后台读到 {len(rows)} 首\n")

    with db.connect() as c:
        rows_ = c.execute(
            "SELECT p.track_id, t.title, t.release_title, p.status FROM track_platforms p "
            "JOIN tracks t ON t.id=p.track_id WHERE p.platform='qishui'").fetchall()
        # 三个名字都做索引：本地曲名、发行名、平台曲名。
        # 后台列表显示的是**发行名**，只按 title 匹配会把「哦豁 · 翻车瞬间」判成
        # 「后台没有」，而它其实就在那儿、叫「翻车瞬间」。
        local = {}
        for r in rows_:
            for key in (r["title"], r["release_title"]):
                if key:
                    local.setdefault(key, r)
        by_plat_title = {r["platform_title"]: r for r in c.execute(
            "SELECT track_id, platform_title, status FROM track_platforms "
            "WHERE platform='qishui' AND platform_title!=''").fetchall()}

    changed = missing = 0
    for r in rows:
        hit = local.get(r["title"]) or by_plat_title.get(r["title"])
        if not hit:
            print(f"  ? 后台有、本地没有：{r['title']}（{r['status']}）")
            missing += 1
            continue
        if hit["status"] == r["status"]:
            continue
        print(f"  ~ {r['title']}：{hit['status']} → {r['status']}"
              + (f"  发行 {r['date']}" if r["date"] else ""))
        changed += 1
        if not DRY:
            extra = {"note": "汽水后台同步"}
            if r["date"]:
                extra["publish_date"] = r["date"]
            if r["url"]:
                extra["song_url"] = r["url"]
            if r.get("song_id"):
                extra["song_id"] = r["song_id"]
            P.set_platform_status(hit["track_id"], "qishui", r["status"], **extra)
            if r["status"] == "online":
                P.set_stage(hit["track_id"], "published")

    back = {r["title"] for r in rows}
    reported = set()
    for title, hit in local.items():
        if hit["track_id"] in reported:
            continue
        names = {hit["title"], hit["release_title"]} - {None, ""}
        if (names & back) or hit["status"] not in ("online", "published"):
            continue
        reported.add(hit["track_id"])
        if True:
            print(f"  ! 本地记着已上线、这个账号后台没有：{title}（可能在别的汽水账号下，未改动）")

    tail = "（预演）" if DRY else ""
    print(f"\n{tail}状态更新 {changed} 首，后台有本地无 {missing} 首")
    return 0


if __name__ == "__main__":
    sys.exit(main())
