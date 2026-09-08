"""
汽水音乐单曲发布 —— 端到端自动填表，直达 Step 3 签署协议。

用法：
    VF_BASE=$PWD VF_TRACK=6d9c9bd9-6c42-4852-83ae-68b097c5d661 browser-harness < scripts/publish_qishui_e2e.py
"""

try:
    from browser_harness import _ipc as _bh_ipc
    _bh_orig_connect = _bh_ipc.connect
    _bh_ipc.connect = lambda name, timeout=1.0: _bh_orig_connect(name, timeout=180.0)
except Exception:
    pass

import json
import os
import sys
import time
from pathlib import Path

BASE = Path(os.environ.get("VF_BASE") or Path.cwd()).resolve()
TRACK_ID = os.environ.get("VF_TRACK", "6d9c9bd9-6c42-4852-83ae-68b097c5d661")
REAL_NAME = os.environ.get("VF_REAL_NAME", "王恩博")
sys.path.insert(0, str(BASE))

from core.paths import DATA_DIR
from core import pipeline as P

track = P.get_track(TRACK_ID) if TRACK_ID else None
if not track:
    print(f"✗ 台账里没有 {TRACK_ID}")
    sys.exit(1)

title = track.get("release_title") or track.get("title") or ""
lyrics_raw = track.get("lyrics", "")
lyrics = "\n".join(l for l in lyrics_raw.splitlines() if not l.strip().startswith("[")).strip()

def _resolve(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = DATA_DIR / path
    return path

audio = _resolve(track.get("audio_file") or "")
cover = _resolve(track.get("cover_file") or "")

if audio.suffix.lower() == ".wav" and audio.is_file():
    mp3_candidate = audio.with_suffix(".mp3")
    if not mp3_candidate.is_file() or mp3_candidate.stat().st_mtime < audio.stat().st_mtime:
        import subprocess
        subprocess.run(["ffmpeg", "-y", "-i", str(audio), "-b:a", "320k", str(mp3_candidate)],
                       check=True, capture_output=True)
    audio = mp3_candidate

print(f"==================================================")
print(f"正在发布歌曲: 《{title}》 ({TRACK_ID})")
print(f"  音频: {audio.name} ({'✓' if audio.is_file() else '✗'})")
print(f"  封面: {cover.name} ({'✓' if cover.is_file() else '✗'})")
print(f"  作者真实姓名: {REAL_NAME}")
print(f"==================================================")

if not (audio.is_file() and cover.is_file()):
    print("✗ 物料缺失，退出")
    sys.exit(1)

# ── 1. 确保在完整发布页 ───────────────────────────
info = page_info()
curr_url = info.get("url", "")
if "complete-publish" not in curr_url:
    print("打开发布页...")
    new_tab("https://music.douyin.com/console/publish")
    time.sleep(5)
    pos = js("""(() => {
      const el = [...document.querySelectorAll('button,div,span')]
        .find(e => e.children.length === 0 && e.textContent.trim() === '发布全曲')
      if (!el) return null
      const r = el.getBoundingClientRect()
      return [Math.round(r.left + r.width/2), Math.round(r.top + r.height/2)]
    })()""")
    if pos:
        click_at_xy(pos[0], pos[1])
        time.sleep(6)

# ── 2. 辅助函数 ──────────────────────────────────
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

def fill_input_by_selector(selector, value):
    ok = js(f"""(() => {{
      const el = document.querySelector({json.dumps(selector)});
      if (!el) return false;
      el.focus();
      el.select?.();
      return true;
    }})()""")
    if not ok:
        return False
    time.sleep(0.2)
    cdp("Input.insertText", text=value)
    time.sleep(0.2)
    return True

def fill_by_label(label, value):
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
    js("""(() => { const el=document.querySelector("[data-vf-fill='1']"); el.focus(); el.select?.() })()""")
    time.sleep(0.2)
    cdp("Input.insertText", text=value)
    time.sleep(0.3)
    js("""document.querySelector("[data-vf-fill='1']")?.removeAttribute('data-vf-fill')""")
    return True

def get_red_errors():
    return js("""(() => {
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

# ── 3. Step 1: 上传作品 ───────────────────────────
print("\n[Step 1] 上传音频与封面...")
print("  音频上传:", "✓" if set_file("完整版", audio) else "✗")
# 等待音频转码与平台解析
_mb = (os.path.getsize(audio) / 1048576) if audio and os.path.exists(audio) else 4
time.sleep(min(30, max(8, _mb * 2.0)))

print("  封面上传:", "✓" if (set_file("1440", cover) or set_file("上传封面", cover)) else "✗")
time.sleep(2)
# 处理裁剪弹窗
js("""(() => {
  const btns = [...document.querySelectorAll('button, .semi-button')].filter(b => b.innerText.trim() === '确定');
  if (btns.length > 0) btns[btns.length - 1].click();
})()""")
time.sleep(1.5)

print("\n[Step 1] 填写基础信息...")
print("  歌曲标题:", "✓" if fill_by_label("歌曲标题", title) else "✗")
time.sleep(0.5)

_album = (track.get("platforms", {}).get("qishui", {}) or {}).get("album") or track.get("album_name") or title
print("  专辑名称:", "✓" if fill_by_label("专辑名称", _album) else "✗", f"({_album})")
time.sleep(0.5)

# 纯音乐开关
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
print("  是否是纯音乐:", r_inst)
time.sleep(0.5)

# 原创单选
js("""(() => {
  const radios = [...document.querySelectorAll('input[type=radio]')];
  const yuanchuang = radios.find(el => {
    let n = el;
    for (let i=0;i<5 && n;i++) { if ((n.textContent||'').startsWith('原创本人原创')) return true; n = n.parentElement }
    return false;
  });
  if (yuanchuang) yuanchuang.click();
})()""")

# AI 声明单选「是」
js("""(() => {
  const aiRow = [...document.querySelectorAll('*')]
    .find(e => (e.textContent||'').includes('以下歌曲均使用AI创作') && e.querySelectorAll('input[type=radio]').length >= 2);
  if (aiRow) {
    const yes = [...aiRow.querySelectorAll('input[type=radio]')].find(el => {
      let n = el;
      for (let i=0;i<4 && n;i++) { if ((n.textContent||'').trim() === '是') return true; n = n.parentElement }
      return false;
    });
    if (yes) yes.click();
  }
})()""")
time.sleep(0.5)

# 使用的 AI 工具: Suno
r_open = js("""(() => {
  const lab=[...document.querySelectorAll('*')].find(e=>e.children.length===0 && e.innerText?.trim()==='使用的AI工具');
  if(!lab) return 'no-label';
  let row=lab.parentElement;
  for(let i=0;i<5 && row;i++){ if(row.innerText.includes('请选择')||row.querySelector('input,[class*=select]')) break; row=row.parentElement; }
  const sel=row.querySelector('[class*=select],[class*=Select],input');
  if(!sel) return 'no-control';
  sel.click(); return 'opened';
})()""")
time.sleep(1.2)
r_pick = js("""(() => {
  const opt=[...document.querySelectorAll('[class*=option],[class*=Option],[role=option],li')]
    .find(e=>e.offsetParent && e.innerText?.trim()==='Suno');
  if(!opt) return 'not-found';
  opt.click(); return 'Suno';
})()""") if r_open == 'opened' else r_open
print("  AI工具选择:", r_pick)
time.sleep(1)

# 是否已发行: 否
js("""(() => {
  const relRow = [...document.querySelectorAll('*')]
    .find(e => (e.textContent||'').includes('是否已发行') && e.querySelectorAll('input[type=radio],button').length >= 2
               && (e.textContent||'').length < 60);
  if (relRow) {
    const no = [...relRow.querySelectorAll('input[type=radio],button')]
      .find(el => (el.textContent||el.value||'').trim() === '否');
    if (no) no.click();
  }
})()""")

time.sleep(1.5)
reds1 = get_red_errors()
print("  Step 1 检查红字:", reds1 or "无")

# 点击下一步进入 Step 2
print("\n进入 Step 2 授权作品...")
js("""(() => {
  const btns = [...document.querySelectorAll('button')].filter(b => b.innerText.trim() === '下一步');
  if (btns.length > 0) btns[btns.length - 1].click();
})()""")

time.sleep(3)

# ── 4. Step 2: 授权作品 ───────────────────────────
print("\n[Step 2] 补充授权与真实姓名...")

# 词作者与曲作者真实姓名
js(f"""(() => {{
  const inputs = [...document.querySelectorAll('input[placeholder="请输入真实姓名"]')];
  inputs.forEach(i => {{
    i.focus();
    i.value = {json.dumps(REAL_NAME)};
    i.dispatchEvent(new Event('input', {{ bubbles: true }}));
    i.dispatchEvent(new Event('change', {{ bubbles: true }}));
  }});
}})()""")
print(f"  真实姓名: {REAL_NAME}")

# 处理艺人多余链接（SOP 规范：无用字段不浪费时间，空行全部切为「无主页链接」避免阻碍表单）
js("""(() => {
  const inputs = [...document.querySelectorAll('input[placeholder="请输入平台个人链接"]')];
  inputs.forEach((input, idx) => {
    if (!input.value.trim()) {
      // 寻找该行对应的下拉
      let p = input.closest('tr') || input.parentElement;
      for (let k=0; k<6 && p; k++) {
        const toggle = [...p.querySelectorAll('span, div, button')].find(e => e.innerText && e.innerText.trim() === '有主页链接');
        if (toggle) {
          toggle.click();
          setTimeout(() => {
            const optNo = [...document.querySelectorAll('li, [role=option], [class*=option]')].find(o => o.innerText && o.innerText.trim() === '无主页链接');
            if (optNo) optNo.click();
          }, 300);
          break;
        }
        p = p.parentElement;
      }
    }
  });
})()""")
time.sleep(2)

reds2 = get_red_errors()
print("  Step 2 检查红字:", reds2 or "无")

# 点击下一步进入 Step 3
print("\n进入 Step 3 签署协议...")
js("""(() => {
  const btns = [...document.querySelectorAll('button')].filter(b => b.innerText.trim() === '下一步');
  if (btns.length > 0) btns[btns.length - 1].click();
})()""")

time.sleep(5)

# ── 5. Step 3: 电子牵协议签署，无需翻阅直接点击【签署】 ─────
print("自动点击右下角蓝色【签署】按钮...")
sign_res = js("""(() => {
  const btns = [...document.querySelectorAll('button')].filter(b => 
    b.innerText.trim() === '签署' && 
    b.offsetParent !== null && 
    !b.disabled
  );
  if (btns.length > 0) {
    const btn = btns[btns.length - 1];
    btn.scrollIntoView({block: 'center'});
    const r = btn.getBoundingClientRect();
    return {found: true, pos: [Math.round(r.left + r.width/2), Math.round(r.top + r.height/2)]};
  }
  return {found: false};
})()""")

if sign_res.get("found"):
    click_at_xy(sign_res["pos"][0], sign_res["pos"][1])
    print("  已点击【签署】按钮:", sign_res["pos"])
    time.sleep(5)

shot_path = capture_screenshot()
print("\n" + "="*50)
print(f"✅ 《{title}》端到端自动发布推进完成！")
print(f"当前页面截图: {shot_path}")
print("="*50)
