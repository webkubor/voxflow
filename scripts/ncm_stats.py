"""
抓网易云音乐人后台指标（播放量/粉丝/收益/指数）。

    VF_BASE=$PWD browser-harness < scripts/ncm_stats.py

## 为什么单独一个脚本

作品目录走公开 API，纯 HTTP 就够（见 sync_netease.py）；只有这些指标
**必须登录**、而且后台是 SPA 没有稳定接口，只能从渲染后的文本里抠。
把它们混在一起会让不需要浏览器的部分也受跨域和登录态的连累。

⚠️ 后台入口是 `/musician/artist/home`。`/musician` 是老路径会跳登录页，
看起来像「没登录」其实登录着 —— 我在这上面误判过一次。

这段会随平台改版失效。失效表现为抓不到（不写库），不会写坏已有数据。
"""
import os, sys, time
from pathlib import Path
sys.path.insert(0, str(Path(os.environ.get("VF_BASE") or Path.cwd())))
from core import pipeline as P

new_tab("https://music.163.com/musician/artist/home")
time.sleep(9)

stats = js(r"""(() => {
  const t = document.body.innerText
  const g = (re) => { const m = t.match(re); return m ? m[1] : null }
  return {
    play_count: g(/播放量[^\d]*([\d.]+[wW万]?)/),
    fans: g(/粉丝\s*\n\s*([\d.]+[wW万]?)/),
    works: g(/作品\(首\)\s*\n\s*(\d+)/),
    withdrawable_cny: g(/可提现税前收益\(元\)[^\d]*([\d.]+)/),
    musician_index: g(/音乐人指数\s*\n\s*(\d+)/),
    play_7d: g(/近7日播放量\s*([\d.]+)\s*次/),
    play_yesterday_delta: g(/昨日新增\s*[↑↓]?\s*(\d+)/),
    roles: g(/网易音乐人\s*\n\s*([^\n]{0,20})/),
  }
})()""")

if not stats or not stats.get("works"):
    print("✗ 抓不到 —— 没登录，或者平台改版了")
    print("  确认一下 https://music.163.com/musician/artist/home 能正常打开")
    raise SystemExit(1)

P.upsert_platform_account("netease",
                          stats={**stats, "synced_at": time.strftime("%Y-%m-%dT%H:%M:%S")})
print(f"✓ 播放 {stats['play_count']}（昨日+{stats['play_yesterday_delta']}）· "
      f"粉丝 {stats['fans']} · 作品 {stats['works']} 首 · "
      f"可提现 ¥{stats['withdrawable_cny']} · 指数 {stats['musician_index']}")
