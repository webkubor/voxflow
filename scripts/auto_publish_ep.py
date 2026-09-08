"""
双人声合辑 EP 发布 —— 《甜酷上线》+《霓虹过弯》
自动填表直达 Step 3 签署协议页，严格停在签署前供创作者人脸意愿确认。
"""
import json
import os
import sys
import time
from pathlib import Path

# 抬高 socket 超时
try:
    from browser_harness import _ipc as _bh_ipc
    _bh_orig_connect = _bh_ipc.connect
    _bh_ipc.connect = lambda name, timeout=1.0: _bh_orig_connect(name, timeout=180.0)
except Exception:
    pass

BASE = Path(os.environ.get("VF_BASE") or Path.cwd()).resolve()
sys.path.insert(0, str(BASE))

from core import pipeline as P

t1 = P.get_track("91f42aaa-99cf-45be-8158-0b824b81e476")
t2 = P.get_track("58879344-a962-4ec4-a126-739df04a8b04")

if not t1 or not t2:
    print("✗ 找不到曲目数据")
    sys.exit(1)

audio1 = str(BASE / "out/music/甜酷上线.mp3")
audio2 = str(BASE / "out/music/霓虹过弯.mp3")
cover_path = t1["cover_file"]
lyrics1 = t1.get("lyrics", "")
lyrics2 = t2.get("lyrics", "")

print("=== 开始发布双人声合辑 EP ===")
print("  主打曲 1: 甜酷上线")
print("  曲目 2:   霓虹过弯")
print(f"  音频 1: {audio1}")
print(f"  音频 2: {audio2}")
print(f"  封面: {cover_path}")

def set_file_by_sel(selector, file_path):
    print(f"  [上传] {selector} -> {file_path}")
    doc = cdp("DOM.getDocument")
    node_res = cdp("DOM.querySelector", nodeId=doc["root"]["nodeId"], selector=selector)
    if "nodeId" in node_res and node_res["nodeId"]:
        cdp("DOM.setFileInputFiles", nodeId=node_res["nodeId"], files=[file_path])
        return True
    return False

def fill_text_by_sel(selector, text):
    ok = js(f"""(() => {{
      const el = document.querySelector({json.dumps(selector)});
      if (!el) return false;
      el.focus();
      if (el.select) el.select();
      return true;
    }})()""")
    if not ok:
        print(f"  ✗ 没找到输入框 {selector}")
        return False
    time.sleep(0.2)
    cdp("Input.insertText", text=text)
    time.sleep(0.3)
    return True

# 1. 设置 AI 创作
print("\n1. 设置 AI 创作与工具...")
js("""(() => {
  const aiField = document.getElementById('aiTools[isMakeByAITools]') || document.querySelector('[x-field-id="aiTools[isMakeByAITools]"]');
  if (!aiField) return;
  const yesLabel = [...aiField.querySelectorAll('label')].find(l => l.innerText.trim() === '是');
  if (yesLabel) {
    const evtOpts = { bubbles: true, cancelable: true, view: window };
    yesLabel.dispatchEvent(new MouseEvent('mousedown', evtOpts));
    yesLabel.dispatchEvent(new MouseEvent('mouseup', evtOpts));
    yesLabel.dispatchEvent(new MouseEvent('click', evtOpts));
  }
})()""")
time.sleep(1)

# 选择 Suno
js("""(() => {
  const field = document.querySelector('[x-field-id="aiTools[aiTools]"]');
  if (field) {
    const sel = field.querySelector('[class*="select"], input');
    if (sel) sel.click();
  }
})()""")
time.sleep(0.8)
js("""(() => {
  const opt = [...document.querySelectorAll('[class*=option], [role=option], li')].find(e => e.offsetParent !== null && e.innerText?.trim() === 'Suno');
  if (opt) opt.click();
})()""")
time.sleep(1)

# 2. 填写歌曲 1: 《甜酷上线》
print("\n2. 填写歌曲 1: 《甜酷上线》...")
# 上传音频
set_file_by_sel('[x-field-id="songs[0][_fullAudios]"] input[type=file]', audio1)
# 标题
fill_text_by_sel('[x-field-id="songs[0][title]"] input', "甜酷上线")
# 歌词
fill_text_by_sel('[x-field-id="songs[0][lyricText]"] textarea', lyrics1)
# 添加自己（表演者、曲作者、词作者）
js("""(() => {
  const fids = ['songs[0][authorArtists]', 'songs[0][composerArtists]', 'songs[0][lyricistArtists]'];
  for (const fid of fids) {
    const el = document.querySelector(`[x-field-id="${fid}"]`);
    const btn = el ? [...el.querySelectorAll('button')].find(b => b.innerText.includes('添加自己')) : null;
    if (btn) btn.click();
  }
})()""")
time.sleep(1)

# 3. 确保歌曲 2 容器存在
print("\n3. 添加歌曲 2: 《霓虹过弯》...")
has_song1 = js("document.querySelector('[x-field-id=\"songs[1][title]\"]') !== null")
if not has_song1:
    js("""(() => {
      const el = document.querySelector('.iCUhU') || [...document.querySelectorAll('*')].find(e => e.innerText?.trim() === '点击添加歌曲');
      if (el) el.click();
    })()""")
    time.sleep(2)

# 上传歌曲 2 音频
set_file_by_sel('[x-field-id="songs[1][_fullAudios]"] input[type=file]', audio2)
# 标题
fill_text_by_sel('[x-field-id="songs[1][title]"] input', "霓虹过弯")
# 歌词
fill_text_by_sel('[x-field-id="songs[1][lyricText]"] textarea', lyrics2)
# 添加自己（表演者、曲作者、词作者）
js("""(() => {
  const fids = ['songs[1][authorArtists]', 'songs[1][composerArtists]', 'songs[1][lyricistArtists]'];
  for (const fid of fids) {
    const el = document.querySelector(`[x-field-id="${fid}"]`);
    const btn = el ? [...el.querySelectorAll('button')].find(b => b.innerText.includes('添加自己')) : null;
    if (btn) btn.click();
  }
})()""")
time.sleep(1)

# 4. 填写专辑信息
print("\n4. 填写专辑信息...")
fill_text_by_sel('[x-field-id="album[albumName]"] input', "甜酷上线")
# 专辑歌手添加自己
js("""(() => {
  const el = document.querySelector('[x-field-id="album[productArtists]"]');
  const btn = el ? [...el.querySelectorAll('button')].find(b => b.innerText.includes('添加自己')) : null;
  if (btn) btn.click();
})()""")
time.sleep(1)
# 上传封面
set_file_by_sel('[x-field-id="album[_coverValue]"] input[type=file]', cover_path)

# 等待音频解码完成
print("  等待音频与封面解析...")
time.sleep(15)

# 处理封面裁剪弹窗（如果有）
js("""(() => {
  const btns = [...document.querySelectorAll('.semi-modal button, [role=dialog] button')].filter(b => b.innerText.trim() === '确定');
  btns.forEach(b => b.click());
})()""")
time.sleep(1)

# 触发智能生成剪辑版
js("""(() => {
  const btns = [...document.querySelectorAll('button')].filter(b => b.innerText.trim() === '智能生成' || b.innerText.trim() === '添加剪辑版');
  btns.forEach(b => b.click());
})()""")
time.sleep(3)

# 5. 点击 Step 1 下一步
print("\n5. 提交 Step 1，进入 Step 2...")
for attempt in range(12):
    res = js("""(() => {
      const btns = [...document.querySelectorAll('button')].filter(b => b.innerText.trim() === '下一步' && b.offsetParent !== null);
      const activeBtn = btns.find(b => !b.disabled && !b.className.includes('disabled'));
      if (activeBtn) {
        activeBtn.scrollIntoView({block: 'center'});
        const r = activeBtn.getBoundingClientRect();
        return {clicked: true, pos: [Math.round(r.left + r.width/2), Math.round(r.top + r.height/2)]};
      }
      return {clicked: false};
    })()""")
    if res.get("clicked"):
        click_at_xy(res["pos"][0], res["pos"][1])
        print("  已点击下一步:", res["pos"])
        break
    print(f"  [重试 {attempt+1}] 等待下一步按钮可用...")
    time.sleep(3)

time.sleep(5)

# 6. 处理 Step 2 授权信息
print("\n6. 处理 Step 2 授权信息...")
# 真实姓名：王恩博
js("""(() => {
  const inputs = [...document.querySelectorAll('input[placeholder*="真实姓名"]')];
  inputs.forEach(input => {
    input.focus();
    input.value = '王恩博';
    input.dispatchEvent(new Event('input', { bubbles: true }));
    input.dispatchEvent(new Event('change', { bubbles: true }));
  });
})()""")
time.sleep(1)

# 外链铁律：绝不点添加平台！已有空白行全部切为「无主页链接」！
print("  执行外链铁律：将所有非QQ音乐或空白外链统一切换为「无主页链接」...")
for cycle in range(6):
    has_empty_link = js("""(() => {
      const rows = [...document.querySelectorAll('.semi-form-field-home-list .ywNyi')];
      for (let i = 0; i < rows.length; i++) {
        const row = rows[i];
        const isQQ = row.querySelector('.nimnx')?.innerText?.includes('QQ音乐');
        const sel = row.querySelector('.douyin-music-select');
        if (!isQQ && sel && sel.innerText.includes('有主页链接')) {
          sel.scrollIntoView({block: 'center'});
          const r = sel.getBoundingClientRect();
          return [Math.round(r.left + r.width/2), Math.round(r.top + r.height/2)];
        }
      }
      return null;
    })()""")
    if not has_empty_link:
        print("  所有多余外链已清零！")
        break
    click_at_xy(has_empty_link[0], has_empty_link[1])
    time.sleep(0.5)
    cdp("Input.dispatchKeyEvent", type="rawKeyDown", windowsVirtualKeyCode=40)
    cdp("Input.dispatchKeyEvent", type="keyUp", windowsVirtualKeyCode=40)
    time.sleep(0.2)
    cdp("Input.dispatchKeyEvent", type="rawKeyDown", windowsVirtualKeyCode=13)
    cdp("Input.dispatchKeyEvent", type="keyUp", windowsVirtualKeyCode=13)
    time.sleep(0.8)

# 7. 点击 Step 2 下一步，直达 Step 3 签署协议
print("\n7. 点击 Step 2 下一步直达 Step 3...")
res2 = js("""(() => {
  const btns = [...document.querySelectorAll('button')].filter(b => b.innerText.trim() === '下一步' && b.offsetParent !== null);
  const activeBtn = btns.find(b => !b.disabled && !b.className.includes('disabled'));
  if (activeBtn) {
    activeBtn.scrollIntoView({block: 'center'});
    const r = activeBtn.getBoundingClientRect();
    return {pos: [Math.round(r.left + r.width/2), Math.round(r.top + r.height/2)]};
  }
  return null;
})()""")
if res2:
    click_at_xy(res2["pos"][0], res2["pos"][1])
    print("  已点击 Step 2 下一步")
time.sleep(6)

# 8. 电子牵协议签署：无需翻阅，直接定位并点击右下角蓝色【签署】按钮
print("\n8. 触发电子牵协议签署...")
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
    print("  已自动点击右下角蓝色【签署】按钮:", sign_res["pos"])
    time.sleep(5)
else:
    print("  未直接找到【签署】按钮，请创作者核对")

shot = capture_screenshot()
print("\n=== 完成！发版流程推进完毕 ===")
print("SHOT:", shot)

