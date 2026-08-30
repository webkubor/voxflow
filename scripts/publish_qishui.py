"""
汽水音乐单曲发布 —— 自动填表，停在提交前。

## 怎么跑

    VF_BASE=$PWD VF_TRACK=nifeng-paoqilai browser-harness < scripts/publish_qishui.py

前提：浏览器已登录汽水音乐（harness 附着的是你日常那个 Chrome，登录态直接可用）。

## 为什么停在提交前，不一路点到底

自动化的价值在**填表**那 10 分钟，不在最后点提交那 1 秒。而提交是不可逆的：
一旦提交进审核队列，改要走撤回流程。所以让人看一眼再点 —— 省下的时间一分不少，
风险却降到零。

平台改版时这个脚本会断。断在填表阶段是安全的（什么都没提交），
真断了就重新探一遍页面、更新 configs/platforms.json 里的字段。

## 字段来自哪

表单字段是 2026-08-30 实际探页面得到的，登记在 configs/platforms.json。
不要在这里硬编码平台规则 —— 加平台/改规则都该只动那份配置。
"""

import json
import os
import sys
import time
from pathlib import Path

# harness 用 exec 跑这个脚本，__file__ 指向的是 harness 自己的包目录，不是这里 ——
# 所以项目根必须从外面传进来，不能靠 __file__ 推。
BASE = Path(os.environ.get("VF_BASE") or Path.cwd()).resolve()
TRACK_ID = os.environ.get("VF_TRACK", "")

ledger = json.loads((BASE / "configs" / "pipeline.json").read_text(encoding="utf-8"))
track = ledger.get("tracks", {}).get(TRACK_ID)
if not track:
    print(f"✗ 台账里没有 {TRACK_ID}；有的是：{list(ledger.get('tracks', {}))}")
    sys.exit(1)

title = track.get("title", "")
lyrics_raw = track.get("lyrics", "")
# [Verse] 这类结构标记是给 Suno 的，不是给听众看的 —— 平台歌词要纯文本
lyrics = "\n".join(l for l in lyrics_raw.splitlines() if not l.strip().startswith("["))
lyrics = "\n".join(l for l in lyrics.splitlines()).strip()

audio = (BASE / track.get("audio_file", "")).resolve()
cover = (BASE / track.get("cover_file", "")).resolve()

print(f"作品：{title}")
print(f"  音频 {audio.name}  {'✓' if audio.is_file() else '✗ 缺失'}")
print(f"  封面 {cover.name}  {'✓' if cover.is_file() else '✗ 缺失'}")
print(f"  歌词 {len(lyrics)} 字")
if not (audio.is_file() and cover.is_file()):
    sys.exit(1)

# ── 进入发布页 ────────────────────────────────────────────
info = page_info()
if "complete-publish" not in info.get("url", ""):
    new_tab("https://music.douyin.com/console/publish")
    time.sleep(7)
    pos = js("""(() => {
      const el = [...document.querySelectorAll('button,div,span')]
        .find(e => e.children.length === 0 && e.textContent.trim() === '发布全曲')
      if (!el) return null
      const r = el.getBoundingClientRect()
      return [Math.round(r.left + r.width/2), Math.round(r.top + r.height/2)]
    })()""")
    if pos:
        click_at_xy(pos[0], pos[1])
        time.sleep(8)
print("页面:", page_info().get("url"))

# ── 上传文件 ──────────────────────────────────────────────
# 文件选择器不能用 JS 赋值（安全限制），必须走 CDP 的 DOM.setFileInputFiles
def set_file(label_keyword, path):
    node = js(f"""(() => {{
      const inputs = [...document.querySelectorAll('input[type=file]')]
      for (const el of inputs) {{
        let n = el
        for (let i = 0; i < 6 && n; i++) {{
          if ((n.textContent || '').includes({json.dumps(label_keyword)})) {{
            el.setAttribute('data-vf-target', '1')
            return true
          }}
          n = n.parentElement
        }}
      }}
      return false
    }})()""")
    if not node:
        print(f"  ✗ 没找到「{label_keyword}」的上传框")
        return False
    doc = cdp("DOM.getDocument")
    nid = cdp("DOM.querySelector", nodeId=doc["root"]["nodeId"],
              selector="input[data-vf-target='1']")["nodeId"]
    cdp("DOM.setFileInputFiles", nodeId=nid, files=[str(path)])
    js("""document.querySelector("input[data-vf-target='1']")?.removeAttribute('data-vf-target')""")
    return True

print("\n上传物料…")
print("  音频:", "✓" if set_file("完整版", audio) else "✗")
# 上传后平台要解析音频（采样率/位深/声道），太早往下走会看到「音频无效」——
# 那不是文件真有问题，是还没传完就被校验了
time.sleep(12)
# 「专辑封面」这个词离 input 太远（中间隔着说明文字），
# 用规格说明里的「1440」当锚点，它就贴在上传框旁边
print("  封面:", "✓" if (set_file("1440", cover) or set_file("上传封面", cover)) else "✗")
time.sleep(3)

# ── 填文本 ────────────────────────────────────────────────
# React 受控组件只认真实输入事件，直接赋 value 不会更新它的 state，
# 提交时读到的还是空 —— 所以走 fill_input（CDP 真实输入）
def fill_by_label(label, value, multiline=False):
    ok = js(f"""(() => {{
      const els = [...document.querySelectorAll('input[type=text], textarea')]
      for (const el of els) {{
        let n = el
        for (let i = 0; i < 6 && n; i++) {{
          if ((n.textContent || '').includes({json.dumps(label)})) {{
            el.setAttribute('data-vf-fill', '1'); return true
          }}
          n = n.parentElement
        }}
      }}
      return false
    }})()""")
    if not ok:
        print(f"  ✗ 没找到「{label}」")
        return False
    if multiline:
        # fill_input 是逐字符键入，换行会被当成「提交」或者直接吞掉，
        # 结果歌词挤成一整段 —— 而平台要求「行数大于 1」。
        # Input.insertText 是整段插入，保留换行。
        js("""(() => { const el=document.querySelector("[data-vf-fill='1']"); el.focus(); el.select?.() })()""")
        time.sleep(0.3)
        cdp("Input.insertText", text=value)
        time.sleep(0.5)
    else:
        fill_input("[data-vf-fill='1']", value)
    js("""document.querySelector("[data-vf-fill='1']")?.removeAttribute('data-vf-fill')""")
    return True

# 专辑介绍：台账里有就用，没有就跳过（不编）。
# 这是选填项，但**能填的都填** —— 平台拿它做展示和推荐，
# 留空等于白白少一块曝光，而生成它的成本几乎为零。
album_desc = track.get("album_desc", "")

print("\n填写信息…")
print("  歌曲标题:", "✓" if fill_by_label("歌曲标题", title) else "✗")
time.sleep(1)
print("  歌词:", "✓" if fill_by_label("歌词", lyrics, multiline=True) else "✗")
time.sleep(1)
print("  专辑名称:", "✓" if fill_by_label("专辑名称", title) else "✗")
time.sleep(1)
if album_desc:
    print("  专辑介绍:", "✓" if fill_by_label("关于专辑的介绍", album_desc, multiline=True) else "✗")
    time.sleep(1)

# ── 作品类型 + AI 声明 ────────────────────────────────────
# AI 声明必须如实填。平台有官方选项，瞒报被查到会影响账号 ——
# 这一项不做「智能判断」，永远打开。
print("\n作品类型与 AI 声明…")
r = js("""(() => {
  const out = {}
  const radios = [...document.querySelectorAll('input[type=radio]')]
  const yuanchuang = radios.find(el => {
    let n = el
    for (let i=0;i<5 && n;i++) { if ((n.textContent||'').startsWith('原创本人原创')) return true; n = n.parentElement }
    return false
  })
  if (yuanchuang) { yuanchuang.click(); out.原创 = true }

  // AI 声明是页面顶部「以下歌曲均使用AI创作」的是/否单选。
  // 之前误认成 input[type=range]，那其实是别的控件。
  // 这一项必须如实选「是」—— 平台有官方选项，瞒报被查到影响账号，
  // 所以不做任何判断，永远选是。
  const aiRow = [...document.querySelectorAll('*')]
    .find(e => (e.textContent||'').includes('以下歌曲均使用AI创作') && e.querySelectorAll('input[type=radio]').length >= 2)
  if (aiRow) {
    const yes = [...aiRow.querySelectorAll('input[type=radio]')].find(el => {
      let n = el
      for (let i=0;i<4 && n;i++) { if ((n.textContent||'').trim() === '是') return true; n = n.parentElement }
      return false
    })
    if (yes) { yes.click(); out.AI声明 = '已选「是」' }
    else out.AI声明 = '找到那一行但没定位到「是」'
  } else out.AI声明 = '没找到 AI 声明行'

  // 「是否已发行」：新歌一律「否」。选「是」意味着这首歌已经在别处上架，
  // 平台会走不同的版权核验流程 —— 填错会卡审核。
  const relRow = [...document.querySelectorAll('*')]
    .find(e => (e.textContent||'').includes('是否已发行') && e.querySelectorAll('input[type=radio],button').length >= 2
               && (e.textContent||'').length < 60)
  if (relRow) {
    const no = [...relRow.querySelectorAll('input[type=radio],button')]
      .find(el => (el.textContent||el.value||'').trim() === '否')
    if (no) { no.click(); out.是否已发行 = '已选「否」' }
    else out.是否已发行 = '找到那一行但没定位到「否」'
  } else out.是否已发行 = '没找到'
  return out
})()""")
print(" ", r)
