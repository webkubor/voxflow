import json
import os
import sys
import time
from pathlib import Path

BASE = Path(os.environ.get("VF_BASE") or Path.cwd()).resolve()
TRACK_ID = os.environ.get("VF_TRACK", "6d9c9bd9-6c42-4852-83ae-68b097c5d661")
sys.path.insert(0, str(BASE))

from core.paths import DATA_DIR
from core import pipeline as P

track = P.get_track(TRACK_ID)
if not track:
    print(f"✗ 台账中不存在 {TRACK_ID}")
    sys.exit(1)

title = track.get("release_title") or track.get("title") or ""
print(f"=== 自动发布曲目：{title} ({TRACK_ID[:8]}) ===")

def _resolve(p: str) -> Path:
    path = Path(p)
    if not path.is_absolute():
        path = DATA_DIR / path
    return path

audio = _resolve(track.get("audio_file") or "")
cover = _resolve(track.get("cover_file") or "")

if audio.suffix.lower() == ".wav" and audio.is_file():
    mp3_candidate = audio.with_suffix(".mp3")
    if mp3_candidate.is_file():
        audio = mp3_candidate

print(f"  音频: {audio.name} ({audio.stat().st_size / 1024 / 1024:.2f} MB)")
print(f"  封面: {cover.name}")

# 1. 确保在 complete-publish 页面
info = page_info()
if "complete-publish" not in info.get("url", ""):
    print("  导航至发布全曲...")
    new_tab("https://music.douyin.com/console/publish")
    time.sleep(6)
    pos = js("""(() => {
      const el = [...document.querySelectorAll('button,div,span')]
        .find(e => e.children.length === 0 && e.textContent.trim() === '发布全曲');
      if (!el) return null;
      const r = el.getBoundingClientRect();
      return [Math.round(r.left + r.width/2), Math.round(r.top + r.height/2)];
    })()""")
    if pos:
        click_at_xy(pos[0], pos[1])
        time.sleep(6)

print("  当前页面:", page_info().get("url"))

# 2. 上传音频与封面
def set_file(label_keyword, path):
    node = js(f"""(() => {{
      const inputs = [...document.querySelectorAll('input[type=file]')];
      for (const el of inputs) {{
        let n = el;
        for (let i = 0; i < 6 && n; i++) {{
          if ((n.textContent || '').includes({json.dumps(label_keyword)})) {{
            el.setAttribute('data-vf-target', '1');
            return true;
          }}
          n = n.parentElement;
        }}
      }}
      return false;
    }})()""")
    if not node:
        return False
    doc = cdp("DOM.getDocument")
    nid = cdp("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector="input[data-vf-target='1']")["nodeId"]
    cdp("DOM.setFileInputFiles", nodeId=nid, files=[str(path)])
    js("""document.querySelector("input[data-vf-target='1']")?.removeAttribute('data-vf-target')""")
    return True

print("  上传音频...")
set_file("完整版", audio)
# 等待音频解析
time.sleep(12)

print("  上传封面...")
set_file("1440", cover) or set_file("上传封面", cover)
time.sleep(3)

# 3. 填入歌曲与专辑文本
def fill_by_label(label, value):
    ok = js(f"""(() => {{
      const els = [...document.querySelectorAll('input[type=text], textarea')];
      for (const el of els) {{
        let n = el;
        for (let i = 0; i < 6 && n; i++) {{
          if ((n.textContent || '').includes({json.dumps(label)})) {{
            el.setAttribute('data-vf-fill', '1'); return true;
          }}
          n = n.parentElement;
        }}
      }}
      return false;
    }})()""")
    if not ok: return False
    js("""(() => { const el=document.querySelector("[data-vf-fill='1']"); el.focus(); el.select?.(); })()""")
    time.sleep(0.2)
    cdp("Input.insertText", text=value)
    time.sleep(0.3)
    js("""document.querySelector("[data-vf-fill='1']")?.removeAttribute('data-vf-fill')""")
    return True

fill_by_label("歌曲标题", title)
fill_by_label("专辑名称", title)

# 4. 点击全部「添加自己」（表演者、曲作者、专辑歌手）
js("""(() => {
  const btns = [...document.querySelectorAll('button')].filter(b => b.textContent.trim() === '添加自己');
  btns.forEach(b => b.click());
})()""")
time.sleep(1)

# 5. 是否纯音乐 -> 是
js("""(() => {
  const lab = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && e.innerText?.trim() === '是否是纯音乐');
  if (lab) {
    let row = lab.parentElement;
    for (let i=0; i<4 && row; i++) { if (row.innerText.length > 8) break; row = row.parentElement; }
    const btn = [...row.querySelectorAll('button,label,span,div')].find(e => e.children.length === 0 && e.innerText?.trim() === '是');
    if (btn) btn.click();
  }
})()""")
time.sleep(1)

# 6. 原创 + AI声明 Suno
js("""(() => {
  // 原创
  const radios = [...document.querySelectorAll('input[type=radio]')];
  const yuanchuang = radios.find(el => {
    let n = el;
    for (let i=0; i<5 && n; i++) { if ((n.textContent||'').startsWith('原创本人原创')) return true; n = n.parentElement; }
    return false;
  });
  if (yuanchuang) yuanchuang.click();

  // AI 创作：是
  const aiRow = [...document.querySelectorAll('*')].find(e => (e.textContent||'').includes('以下歌曲均使用AI创作') && e.querySelectorAll('input[type=radio]').length >= 2);
  if (aiRow) {
    const yes = [...aiRow.querySelectorAll('input[type=radio]')].find(el => {
      let n = el;
      for (let i=0; i<4 && n; i++) { if ((n.textContent||'').trim() === '是') return true; n = n.parentElement; }
      return false;
    });
    if (yes) yes.click();
  }

  // 是否已发行：否
  const relRow = [...document.querySelectorAll('*')].find(e => (e.textContent||'').includes('是否已发行') && e.querySelectorAll('input[type=radio],button').length >= 2 && (e.textContent||'').length < 60);
  if (relRow) {
    const no = [...relRow.querySelectorAll('input[type=radio],button')].find(el => (el.textContent||el.value||'').trim() === '否');
    if (no) no.click();
  }
})()""")
time.sleep(1)

# AI 工具选择 Suno
js("""(() => {
  const lab = [...document.querySelectorAll('*')].find(e => e.children.length === 0 && e.innerText?.trim() === '使用的AI工具');
  if (lab) {
    let row = lab.parentElement;
    for (let i=0; i<5 && row; i++) { if (row.innerText.includes('请选择') || row.querySelector('input,[class*=select]')) break; row = row.parentElement; }
    const sel = row.querySelector('[class*=select],[class*=Select],input');
    if (sel) sel.click();
  }
})()""")
time.sleep(1)
js("""(() => {
  const opt = [...document.querySelectorAll('[class*=option],[class*=Option],[role=option],li')].find(e => e.offsetParent && e.innerText?.trim() === 'Suno');
  if (opt) opt.click();
})()""")
time.sleep(1)

# 7. 智能剪辑版生成（如果有按钮）
js("""(() => {
  const clipBtn = [...document.querySelectorAll('button')].find(b => b.textContent.trim() === '智能生成' || b.textContent.trim() === '添加剪辑版');
  if (clipBtn) clipBtn.click();
})()""")
time.sleep(3)

print("  Step 1 表单已就绪，准备点击下一步...")
# 8. 点击 Step 1 的「下一步」
res = js("""(() => {
  const btns = [...document.querySelectorAll('button')].filter(b => b.textContent.trim() === '下一步');
  const activeBtn = btns.find(b => !b.disabled);
  if (activeBtn) {
    activeBtn.click();
    return {clicked: true};
  }
  return {clicked: false, btns: btns.map(b => ({cls: b.className, dis: b.disabled}))};
})()""")
print("  点击下一步进入 Step 2:", res)
time.sleep(4)

# 9. 处理 Step 2 授权信息
print("  正在处理 Step 2 授权与真实姓名...")
# 词/曲作者真实姓名：王恩博
js("""(() => {
  const inputs = [...document.querySelectorAll('input[placeholder*="真实姓名"]')];
  inputs.forEach(input => {
    input.focus();
    input.value = '王恩博';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
})()""")

# 多余外链切换为「无主页链接」
js("""(() => {
  const rows = [...document.querySelectorAll('.semi-select, [class*="select"]')].filter(s => s.innerText.includes('有主页链接'));
  // 保持第 1 个（QQ音乐），将其余的切换为「无主页链接」
  for (let i = 1; i < rows.length; i++) {
    rows[i].click();
    setTimeout(() => {
      const opt = [...document.querySelectorAll('[role="option"], .semi-select-option')].find(o => o.innerText.includes('无主页链接'));
      if (opt) opt.click();
    }, 300);
  }
})()""")
time.sleep(2)

# 10. 点击 Step 2 的「下一步」直达 Step 3 签署协议
print("  点击 Step 2 下一步，直达签署协议...")
res2 = js("""(() => {
  const btns = [...document.querySelectorAll('button')].filter(b => b.textContent.trim() === '下一步');
  const activeBtn = btns.find(b => !b.disabled);
  if (activeBtn) {
    activeBtn.click();
    return {clicked: true};
  }
  return {clicked: false};
})()""")
print("  到达 Step 3:", res2)
time.sleep(5)

shot = capture_screenshot()
print("SHOT:", shot)
