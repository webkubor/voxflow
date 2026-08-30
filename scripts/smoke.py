#!/usr/bin/env python3
"""
冒烟测试 —— 起服务前后跑一遍，挡住「不报错但没生效」那类问题。

    .venv/bin/python scripts/smoke.py

## 为什么需要它

今天一天出了六个 bug，形态完全一样：**静默失败**。

| Bug | 表现 |
|---|---|
| store 方法名拼错 | 界面空白，零报错 |
| 删除按钮条件恒假 | 按钮从没出现过 |
| 复选框 value 是 undefined | 勾了等于没勾 |
| 音色路径靠名字拼 | 改名后播的是别的音频 |
| SQL 列名写错 | 端点 500，前端只显示「加载失败」 |

没有一个会抛异常，全都是「看起来正常，其实没生效」。人肉 curl + 截图验证
必然漏，因为人只会去看自己想到的那几处。

这个脚本做的就是**把「我以为它好着呢」变成断言**。

## 检查什么

1. 后端能起、关键端点返回 200
2. 数据自洽：专辑曲目数 == 平台在线数 == 平台自报数
3. 资产文件真的存在（封面、参考音频指向的路径）
4. 敏感信息不经 API 外泄
5. 前端 store 导出的方法，模板里调用的都存在（今天那个 bug 的专项防线）
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
PROJECT = Path(__file__).resolve().parent.parent
BASE = "http://127.0.0.1:8866"

failures: list[str] = []
checks = 0


def check(name: str, cond: bool, detail: str = "") -> None:
    global checks
    checks += 1
    if cond:
        print(f"  ✓ {name}")
    else:
        print(f"  ✗ {name}  {detail}")
        failures.append(f"{name} {detail}".strip())


def get(path: str):
    req = urllib.request.Request(BASE + path, headers={"User-Agent": "VoxFlow-smoke"})
    with urllib.request.urlopen(req, timeout=20) as r:
        return r.status, json.loads(r.read().decode())


print("── 后端端点 ──")
try:
    for path in ("/api/status", "/api/personas", "/api/pipeline",
                 "/api/albums", "/api/platform-accounts", "/api/capabilities"):
        code, _ = get(path)
        check(path, code == 200, f"HTTP {code}")
except Exception as e:
    check("后端可达", False, str(e)[:60])
    print("\n服务没起？先跑 ./run.sh web")
    raise SystemExit(1)

print("\n── 数据自洽 ──")
_, pipe = get("/api/pipeline")
_, albums = get("/api/albums")
_, accounts = get("/api/platform-accounts")

tracks = pipe["tracks"]
check("作品台账非空", len(tracks) > 0, f"{len(tracks)} 首")

for pk, acc in accounts["accounts"].items():
    reported = acc.get("song_count", 0)
    local = acc.get("local_online_count", 0)
    check(f"{acc.get('label') or pk}：平台自报 vs 台账在线",
          reported == local, f"{reported} vs {local}")

alb = albums["albums"]
if alb:
    declared = sum(a["track_count"] for a in alb.values())
    joined = sum(len(a["tracks"]) for a in alb.values())
    check("专辑曲目数 vs join 出来的曲目数", declared == joined, f"{declared} vs {joined}")

print("\n── 资产文件 ──")
from core.paths import DATA_DIR      # noqa: E402

missing_cover = [a["title"] for a in alb.values()
                 if a.get("cover_local") and not (DATA_DIR / a["cover_local"]).exists()]
check("专辑封面文件都在", not missing_cover, str(missing_cover[:3]))

_, personas = get("/api/personas")
bad_ref = [k for k, v in personas["personas"].items()
           if v.get("ref") and not (DATA_DIR / v["ref"]).exists()]
check("音色参考音频都在", not bad_ref, str(bad_ref))

print("\n── 隐私 ──")
raw = json.dumps(pipe, ensure_ascii=False)
artist_f = DATA_DIR / "configs" / "artist.json"
if artist_f.exists():
    real_name = json.loads(artist_f.read_text(encoding="utf-8")).get("real_name", "")
    check("真实姓名不经 API 外泄", bool(real_name) and real_name not in raw)
ignored = subprocess.run(["git", "check-ignore", "configs/artist.json"],
                         cwd=PROJECT, capture_output=True).returncode == 0
check("artist.json 不进 git", ignored)

print("\n── 前端：调用的 store 方法真的存在吗 ──")
# 今天那个 bug 的专项防线：MainLayout 调了 capabilitiesStore.fetchCapabilities()，
# 而 store 里根本没这个方法 —— Promise.all 第一步就 TypeError，音色库永远是空的。
# JS 没有类型检查，这种拼写错误只能靠扫。
stores_dir = PROJECT / "web/ui/src/stores"
exported: dict[str, set[str]] = {}
for f in stores_dir.glob("*.js"):
    text = f.read_text(encoding="utf-8")
    m = re.search(r"return \{(.*?)\};", text, re.S)
    if m:
        exported[f.stem] = {x.strip().split(":")[0].strip()
                            for x in m.group(1).replace("\n", " ").split(",") if x.strip()}

store_var = {"capabilitiesStore": "capabilities", "voicesStore": "voices",
             "tasksStore": "tasks", "libraryStore": "library", "synthStore": "synth",
             "sunoStore": "suno", "pipelineStore": "pipeline"}
bad_calls = []
def strip_comments(src: str) -> str:
    """
    去掉注释再扫。

    第一版没做这步，结果把「注释里解释历史 bug 的那行代码」也当成了真调用 ——
    检测工具自己误报，比不检测更浪费时间。
    """
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)      # 块注释
    src = re.sub(r"^\s*//.*$", "", src, flags=re.M)       # 整行 //
    src = re.sub(r"<!--.*?-->", "", src, flags=re.S)      # HTML 注释
    return src


for vue in (PROJECT / "web/ui/src").rglob("*.vue"):
    text = strip_comments(vue.read_text(encoding="utf-8"))
    for var, store in store_var.items():
        for call in re.findall(rf"{var}\.(\w+)\(", text):
            if store in exported and call not in exported[store]:
                bad_calls.append(f"{vue.name}: {var}.{call}() 不存在于 {store} store")
check("组件调用的 store 方法都存在", not bad_calls, "; ".join(bad_calls[:3]))

# storeToRefs 解构出来的状态，store 里真的有吗。
# 「globalLoading 在 tasks store 却从 synth 取」就是这么漏的 ——
# 取错拿到 undefined，n-spin 的 :show 收到 undefined 会一直转，页面永远 loading。
bad_refs = []
for vue in (PROJECT / "web/ui/src").rglob("*.vue"):
    text = strip_comments(vue.read_text(encoding="utf-8"))
    for names, var in re.findall(r"storeToRefs?\s*\(\s*(\w+)\s*\)", text) and \
                      re.findall(r"const\s*\{([^}]+)\}\s*=\s*storeToRefs\((\w+)\)", text):
        store = store_var.get(var)
        if not store or store not in exported:
            continue
        for name in [n.strip().split(":")[0].strip() for n in names.split(",") if n.strip()]:
            if name and name not in exported[store]:
                bad_refs.append(f"{vue.name}: {name} 不在 {store} store 里（从 {var} 解构）")
check("组件解构的 store 状态都存在", not bad_refs, "; ".join(bad_refs[:3]))

print(f"\n{'─' * 40}")
if failures:
    print(f"✗ {len(failures)}/{checks} 项没过：")
    for f in failures:
        print(f"    {f}")
    raise SystemExit(1)
print(f"✓ {checks} 项全过")
