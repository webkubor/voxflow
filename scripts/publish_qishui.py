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

# ── harness 的 socket 超时太小，先抬高 ──────────────────────────
#
# `browser_harness/helpers.py` 里 `_send()` 写死 `ipc.connect(timeout=5.0)`。
# 5 秒够普通 CDP 调用，但**传文件不够** —— 这里要通过 CDP 把一个 28MB 的 wav
# 塞给 <input type=file>，实测直接 TimeoutError。
#
# 而那个报错长得像网络问题（socket recv timed out），完全看不出是文件太大，
# 排查时会往浏览器连不上的方向去猜。
#
# 不改 harness 本体（那是外部依赖，装更新就没了），只在本脚本里把连接超时
# 调大。其余行为一个字不动。
try:
    from browser_harness import _ipc as _bh_ipc

    _bh_orig_connect = _bh_ipc.connect
    _bh_ipc.connect = lambda name, timeout=1.0: _bh_orig_connect(name, timeout=180.0)
except Exception:  # noqa: BLE001 —— 抬不高就按原样跑，大不了还是超时
    pass


import json
import os
import sys
import time
from pathlib import Path

# harness 用 exec 跑这个脚本，__file__ 指向的是 harness 自己的包目录，不是这里 ——
# 所以项目根必须从外面传进来，不能靠 __file__ 推。
BASE = Path(os.environ.get("VF_BASE") or Path.cwd()).resolve()
TRACK_ID = os.environ.get("VF_TRACK", "")
sys.path.insert(0, str(BASE))

from core.paths import DATA_DIR                      # noqa: E402
from core import pipeline as P                       # noqa: E402

track = P.get_track(TRACK_ID) if TRACK_ID else None
if not track:
    print(f"✗ 台账里没有 {TRACK_ID}")
    sys.exit(1)

title = track.get("release_title") or track.get("title") or ""
lyrics_raw = track.get("lyrics", "")
# [Verse] 这类结构标记是给 Suno 的，不是给听众看的 —— 平台歌词要纯文本
lyrics = "\n".join(l for l in lyrics_raw.splitlines() if not l.strip().startswith("["))
lyrics = "\n".join(l for l in lyrics.splitlines()).strip()

def _resolve(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = DATA_DIR / path
    return path

audio = _resolve(track.get("audio_file") or "")
cover = _resolve(track.get("cover_file") or "")

# 汽水平台对大体积 WAV 解析耗时极长且容易报「音频无效」，
# 上传前转为 320k MP3，体积缩小 80%，平台解析秒过
if audio.suffix.lower() == ".wav" and audio.is_file():
    mp3_candidate = audio.with_suffix(".mp3")
    if not mp3_candidate.is_file() or mp3_candidate.stat().st_mtime < audio.stat().st_mtime:
        import subprocess
        subprocess.run(["ffmpeg", "-y", "-i", str(audio), "-b:a", "320k", str(mp3_candidate)],
                       check=True, capture_output=True)
    audio = mp3_candidate

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
# 那不是文件真有问题，是还没传完就被校验了。
#
# ⚠️ 2026-09-06 实测：29MB 的 wav 等 12 秒**远远不够**，平台同时报出
# 「音频无效」和「非纯音乐请填歌词」两条 —— 后一条尤其误导人，
# 看起来像 AI 声明或歌词填错了，实际是它解析到了半截的文件。
#
# 两个应对，都要：① 上传前把音频转成 320k mp3（29MB → 6MB）；
# ② 这里按文件大小等，别写死一个数。
_mb = (os.path.getsize(audio) / 1048576) if audio and os.path.exists(audio) else 6
time.sleep(min(60, max(15, _mb * 2.5)))
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
    # fill_input 逐字符键入中文经常只落下第一个字（实测歌曲名变成「竹」），
    # 专辑名和歌名对不上，页面红字报错。一律用 insertText 整段插入。
    js("""(() => { const el=document.querySelector("[data-vf-fill='1']"); el.focus(); el.select?.() })()""")
    time.sleep(0.2)
    cdp("Input.insertText", text=value)
    time.sleep(0.4)
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
# ⚠️ 专辑名**不是歌名**。
#
# 之前这里填的是 `title`，于是**每首歌都新建一个专辑** —— 一批四首就是
# 四个单曲专辑，平台上散成四条，既不像一个作品集，也拿不到专辑维度的曝光。
# 同一批次的歌应该共用一个专辑（表单上还有「选择已有专辑」可以复用）。
#
# 真源是台账的 album_name / album_desc，填不到就退回歌名（单曲发行是合理的，
# 但那应该是显式选择，不是因为读不到而默认）。
_album = (track.get("platforms", {}).get("qishui", {}) or {}).get("album") \
         or track.get("album_name") or title
print("  专辑名称:", "✓" if fill_by_label("专辑名称", _album) else "✗", f"（{_album}）")
time.sleep(1)
if album_desc:
    print("  专辑介绍:", "✓" if fill_by_label("关于专辑的介绍", album_desc, multiline=True) else "✗")
    time.sleep(1)

# ── 是否是纯音乐 ──────────────────────────────────────────
#
# ⚠️ 这个开关此前完全没设，是「上传卡住」的真凶之一。
#
# 它默认是「否」，于是平台要求填歌词；而我们在歌词栏填的是 `[Instrumental]`，
# 平台把它当成空 —— 报出「您上传的音频非纯音乐，请填写歌词」。
# 那句话读起来像是音频被检测出人声了，实际是**这个开关没打开**。
#
# 判断依据用歌词字段：`[Instrumental]` 或空 = 纯音乐。
# 不去猜音频里有没有人声 —— 那是平台该判的，我们只如实声明。
_is_inst = (lyrics or "").strip().lower() in ("", "[instrumental]", "instrumental")
r_inst = js("""(() => {
  const lab=[...document.querySelectorAll('*')].find(e=>e.children.length===0 && e.innerText?.trim()==='是否是纯音乐');
  if(!lab) return '没有这个开关';
  let row=lab.parentElement;
  for(let i=0;i<4 && row;i++){ if(row.innerText.length>8) break; row=row.parentElement; }
  const want=%s;
  const btn=[...row.querySelectorAll('button,label,span,div')]
    .find(e=>e.children.length===0 && e.innerText?.trim()===want);
  if(!btn) return '没找到「'+want+'」';
  btn.click(); return '已选「'+want+'」';
})()""" % ("'是'" if _is_inst else "'否'"))
print("\n是否是纯音乐:", r_inst)
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

# AI 工具下拉。不选的话页面过不了校验。
ai = js("""(() => {
  const lab = [...document.querySelectorAll('*')].find(e => (e.textContent||'').trim() === '使用的AI工具')
  let root = lab
  for (let i = 0; i < 8 && root; i++) {
    const box = [...root.querySelectorAll('*')].find(e => (e.textContent||'').trim() === '请选择')
    if (box) { box.click(); return 'opened' }
    root = root.parentElement
  }
  return 'no-box'
})()""")
time.sleep(0.6)
picked = js("""(() => {
  const el = [...document.querySelectorAll('*')].find(e => {
    const t = (e.textContent||'').trim()
    const r = e.getBoundingClientRect()
    return t === 'Suno' && r.height > 12 && r.height < 60 && r.width > 30
  })
  if (!el) return 'not-found'
  el.click(); return 'Suno'
})()""")
# ── 使用的 AI 工具 ────────────────────────────────────────
#
# AI 声明选「是」之后这一栏必填。它是个下拉，**选项要展开之后才渲染出来** ——
# 展开和选择必须分两次 js 调用，中间等一下；写在同一次里必然 not-found
# （之前就是这么失败的，报「opened not-found」看起来像没有这个选项）。
r_open = js("""(() => {
  const lab=[...document.querySelectorAll('*')].find(e=>e.children.length===0 && e.innerText?.trim()==='使用的AI工具');
  if(!lab) return 'no-label';
  let row=lab.parentElement;
  for(let i=0;i<5 && row;i++){ if(row.innerText.includes('请选择')||row.querySelector('input,[class*=select]')) break; row=row.parentElement; }
  const sel=row.querySelector('[class*=select],[class*=Select],input');
  if(!sel) return 'no-control';
  sel.click(); return 'opened';
})()""")
time.sleep(1.5)
r_pick = js("""(() => {
  const opt=[...document.querySelectorAll('[class*=option],[class*=Option],[role=option],li')]
    .find(e=>e.offsetParent && e.innerText?.trim()==='Suno');
  if(!opt) return 'not-found';
  opt.click(); return 'Suno';
})()""") if r_open == 'opened' else r_open
print("  AI工具:", r_open, r_pick)
time.sleep(1)
# 填完必须看红字。fill_input 吞字这种错，不截图会当成成功。
reds = js("""(() => {
  const reds = []
  for (const e of document.querySelectorAll('*')) {
    if (e.children.length > 3) continue
    const t = (e.textContent||'').trim()
    if (!t || t.length > 80) continue
    const c = getComputedStyle(e).color
    const m = c.match(/rgba?\\((\\d+),\\s*(\\d+),\\s*(\\d+)/)
    if (!m) continue
    if (+m[1] > 180 && +m[2] < 130 && +m[3] < 130) reds.push(t)
  }
  return [...new Set(reds)]
})()""")
print("  红字:", reds or "无")
try:
    shot = capture_screenshot()
    print("  截图:", shot)
except Exception as e:
    print("  截图失败:", e)

print("\n表已填好，停在提交前。请你看一眼再点「下一步 / 提交」。")
print("点完告诉我，我把台账改成 reviewing。")
