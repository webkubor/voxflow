"""
抓网易云音乐人后台的**单曲**播放量，回填台账。

    VF_BASE=$PWD browser-harness < scripts/ncm_track_stats.py

## 和 ncm_stats.py 的分工

`ncm_stats.py` 抓的是**账号级**汇总（总播放、粉丝、可提现收益）。
这个抓的是**单曲级**播放量 —— 两者回答的问题完全不同：

- 账号级：这门生意整体赚不赚钱
- 单曲级：**哪首歌在赚钱** → 下一首该做什么风格

后者才是选题依据，而它一直是空白：公开 API 给不了（`song/detail` 的
`playedNum` 恒为 0，2026-09-05 两个端点都验证过），只能从后台抓。

## 口径：近 30 日，不是累计

后台的数据中心只给「近 7 日」和「近 30 日」两档，**没有累计**。

这不算损失，反而更合适：累计播放量里绝大部分是老作品多年的沉淀，
而「最近 30 天哪首在涨」才是能指导下一首做什么的信号。

## 收益是折算的，不是平台给的

后台的单曲表里**没有收益列** —— 收益只有账号级的「可提现税前收益」。
所以单曲收益 = 该曲播放量 × 实测千播单价（账号总收益 ÷ 账号总播放）。

这个折算站得住：网易云按播放计费，同一账号下各曲单价基本相同。但它
**是折算不是实测**，写库时单独记 `earned_est=1` 意义上的口径说明，
界面上也必须标出来 —— 把折算值当平台实付会让人高估某几首的价值。

## 会随平台改版失效

抓的是渲染后的表格（后台是 Ant Design SPA，没有稳定公开接口）。
失效表现为抓不到（不写库），不会写坏已有数据。
"""
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(os.environ.get("VF_BASE") or Path.cwd())))
from core import db, obs  # noqa: E402
from core import pipeline as P  # noqa: E402

RANGE = "近30日"          # 后台只有「近7日」「近30日」两档
MAX_PAGES = 20            # 每页 10 首，20 页够到 200 首；到底了自然提前结束

new_tab("https://music.163.com/musician/artist/dataCenter")  # noqa: F821
time.sleep(9)

if not js("!!document.querySelector('table tbody tr')"):  # noqa: F821
    print("✗ 抓不到表格 —— 没登录，或者后台改版了")
    print("  确认 https://music.163.com/musician/artist/dataCenter 能正常打开并列出作品")
    raise SystemExit(1)

# 切到近 30 日。默认是近 7 日，那个窗口太短，几首歌只有个位数播放，看不出趋势。
js(f"""(() => {{
  const t = [...document.querySelectorAll('.mc-tabs-item')]
    .find(e => e.innerText.trim() === '{RANGE}')
  if (t) t.click()
}})()""")  # noqa: F821
time.sleep(4)

rows = []
seen_first = None
for page in range(1, MAX_PAGES + 1):
    if page > 1:
        js(f"""(() => {{
          const pag = document.querySelector('.ant-pagination, [class*=pagination]')
          const li = [...(pag?.querySelectorAll('li') || [])]
            .find(e => e.innerText.trim() === '{page}')
          if (li) (li.querySelector('a') || li).click()
        }})()""")  # noqa: F821
        time.sleep(3.5)

    page_rows = js("""[...document.querySelectorAll('table tbody tr')]
        .map(tr => [...tr.querySelectorAll('td')].map(td => td.innerText.trim()))""")  # noqa: F821
    if not page_rows:
        break
    # 翻页失败时页面内容不变，会把同一页重复收进来 —— 用首行判重，
    # 比信任「点了就翻了」可靠（Ant 的分页在末页点击是无响应的）。
    first = page_rows[0][1] if len(page_rows[0]) > 1 else None
    if first and first == seen_first:
        break
    seen_first = first
    rows.extend(page_rows)
    if len(page_rows) < 10:      # 不满一页 = 最后一页
        break


def _int(v: str) -> int:
    """表格里没有数据是 '--'，不是 0 —— 但对播放量来说两者都当 0 处理。"""
    try:
        return int(str(v).replace(",", ""))
    except (TypeError, ValueError):
        return 0


tracks = [{"song": r[1], "album": r[2], "plays": _int(r[3])}
          for r in rows if len(r) > 3 and r[1]]
if not tracks:
    print("✗ 表格解析出来是空的 —— 列的顺序可能变了")
    raise SystemExit(1)

# 折算单曲收益：实测千播单价（账号总收益 ÷ 账号总播放）× 该曲播放量。
rev = obs.platform_revenue().get("netease") or {}
rate = rev.get("cny_per_1k_plays", 0) if rev.get("rate_source") == "measured" else 0
if not rate:
    print("⚠ 还没有账号级收益数据（先跑 scripts/ncm_stats.py），本次只回填播放量")

# 标题 → track_id。台账里这些作品本来就是 sync_netease.py 按平台歌名建的，
# 所以精确匹配就够；匹配不上的单独列出来让人看一眼，不静默丢弃。
db.init()
with db.connect() as c:
    id_by_title = {r["title"]: r["id"] for r in c.execute("SELECT id, title FROM tracks")}

now = time.strftime("%Y-%m-%dT%H:%M:%S")
written, missed = 0, []
for t in tracks:
    tid = id_by_title.get(t["song"])
    if not tid:
        missed.append(t["song"])
        continue
    with db.connect() as c:
        c.execute(
            "UPDATE track_platforms SET plays=?, earned_cny=?, stats_at=?, updated_at=?"
            " WHERE track_id=? AND platform='netease'",
            (t["plays"], round(t["plays"] * rate / 1000, 4), now, now, tid))
        written += c.total_changes

total_plays = sum(t["plays"] for t in tracks)
active = [t for t in tracks if t["plays"] > 0]
print(f"✓ {RANGE}：{len(tracks)} 首，播放 {total_plays} 次，{len(active)} 首有播放")
print(f"  回填 {written} 首（按标题匹配台账）"
      + (f"，{len(missed)} 首台账里没有：{'、'.join(missed[:4])}" if missed else ""))
if rate:
    print(f"  收益按实测 ¥{rate:.4f}/千播折算 —— 是折算值不是平台实付，界面上会标出来")
for t in active[:5]:
    print(f"    {t['plays']:>5} 次  {t['song']}  ({t['album']})")

obs.log("ncm_track_stats", tracks=len(tracks), plays=total_plays,
        written=written, missed=len(missed), window=RANGE)
