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
                 "/api/albums", "/api/platform-accounts", "/api/capabilities",
                 # 可观测性四件套。它们坏了不会有人立刻发现 —— 没人会每天
                 # 主动打开成本看板，等到想看的时候才发现三个月没数据了。
                 "/api/health", "/api/metrics", "/api/logs", "/api/economics"):
        code, _ = get(path)
        check(path, code == 200, f"HTTP {code}")
except Exception as e:
    check("后端可达", False, str(e)[:60])
    print("\n服务没起？先跑 ./run.sh web")
    raise SystemExit(1)

print("\n── 数据自洽 ──")
# 健康端点返回 200 只说明它自己没崩，真正要看的是它判断出来的结论。
# 这里断言的是**结构**而不是「必须 ok」—— 磁盘快满时它就该报 degraded，
# 那时候测试不该失败，失败的应该是「它连 degraded 都报不出来」。
_, health = get("/api/health")
check("健康端点给出三档状态之一",
      health.get("status") in ("ok", "degraded", "down"),
      f"status={health.get('status')}")
check("健康端点列出了体检项",
      isinstance(health.get("checks"), dict) and len(health["checks"]) >= 3,
      f"checks={list((health.get('checks') or {}).keys())}")
check("坏掉的体检项都进了 failed 清单",
      sorted(health.get("failed", [])) ==
      sorted([k for k, v in (health.get("checks") or {}).items() if not v.get("ok")]))

# 首次体验：这几条挡的是「新用户装完打不开」那一类问题，它们不会报错，
# 只会让人默默关掉页面。
_, dl = get("/api/models/download")
check("模型下载端点给出「现在能做什么」",
      isinstance(dl.get("can_do_now"), list) and len(dl["can_do_now"]) >= 1,
      f"can_do_now={dl.get('can_do_now')}")
check("install.sh 把模型下到数据目录而不是项目目录",
      "VOXFLOW_MODELS_DIR" in (PROJECT / "install.sh").read_text(encoding="utf-8")
      and "--local_dir ./models/" not in (PROJECT / "install.sh").read_text(encoding="utf-8"),
      "install.sh 还在往 ./models/ 下模型，运行时按 core/paths.py 去 ~/.voxflow/models 找，对不上")
check("模型没下不算 down（degraded 才对）",
      health["checks"]["tts_models"].get("ok") is True,
      "「还没下模型」被判成故障，新用户打开就是红色报错")

# 主内容区不能被整体隐藏。
#
# 2026-09-06 的事故：MainLayout 的 `.hidden-tabs { display: none }` 把整个
# n-tabs 隐藏了 —— 而**八个屏的内容全在它里面**。页面上只剩顶栏、音色库和
# 那排 tab 按钮，点什么都是一片空白，看起来就是「黑屏 / 数据全没了」。
#
# 那个 class 的本意只是隐藏 n-tabs **自带的导航条**（上面那排手搓的 .tab-nav
# 才是给人点的），写成隐藏整个容器就把内容一起藏了。
#
# **为什么这个 bug 能溜过所有既有检查**：接口全 200、store 方法都在、
# 控制台零报错，而 `document.querySelector('.kpi')` 照样能找到元素 ——
# `display:none` 的节点在 DOM 里活得好好的。「在 DOM 里」≠「看得见」，
# 而人看的是后者。
_ml = (PROJECT / "web/ui/src/components/MainLayout.vue").read_text(encoding="utf-8")
_bad_hide = re.search(r"^\.hidden-tabs\s*\{[^}]*display:\s*none", _ml, re.M)
check("n-tabs 容器没有被整体隐藏（内容区在里面）",
      not _bad_hide,
      "`.hidden-tabs { display:none }` 会把八个屏的内容一起藏掉 —— "
      "只能隐藏 :deep(.n-tabs-nav)")

# UI 一致性：图标语言只能有一套。
#
# Icon.vue 的文件头写清了为什么不用 emoji（三套系统渲染完全不同、不能跟主题
# 变色），但老屏幕的表单标签一度全是 emoji —— 同一个产品里两套图标语言，
# 是最容易被忽略又最显廉价的不一致。改净之后这条断言挡住它再混回来。
#
# 只查**元件位**（标签、标题、pill 这类），不查文案里的 emoji ——
# 提示语里出现一个表情是文案风格，不是 UI 元件。
import re as _re                                                  # noqa: E402
_EMOJI = _re.compile(r"[\U0001F300-\U0001FAFF]")
_ELEMENT_TAG = _re.compile(
    r'<(?:label|span|div)\s+class="[^"]*'
    r'(?:form-label|param-label|meta-label|line-label|panel-title|lines-title'
    r'|chart-title|section-title|meta-pill|credit-pill|upload-icon|empty-icon)'
    r'[^"]*"\s*>[^<]*'
)
_emoji_hits = []
for _vue in sorted((PROJECT / "web/ui/src").rglob("*.vue")):
    for _m in _ELEMENT_TAG.finditer(_vue.read_text(encoding="utf-8")):
        if _EMOJI.search(_m.group(0)):
            _emoji_hits.append(f"{_vue.name}: {_m.group(0)[:60]}")
check("UI 元件位没有 emoji（图标统一走 Icon.vue）",
      not _emoji_hits, "; ".join(_emoji_hits[:3]))

_, eco = get("/api/economics")
check("成本端点带覆盖率（0 元要能和「没记账」区分开）",
      "covered" in eco and "total_tracks" in eco and "revenue_covered" in eco)
# null 和 0 必须分开：「—」是还没抓数据，「0」是真的没播。混在一起会让
# 「没同步」被读成「没人听」，那是两个完全不同的行动。
_no_rev = [t for t in eco.get("tracks", []) if t.get("earned_cny") is None]
check("没有收入数据的作品用 null 而不是 0 表示",
      all(t.get("plays") is None and t.get("roi") is None for t in _no_rev),
      "有作品 earned_cny 是 null 但 plays/roi 给了 0，含义会被读错")

_, pipe = get("/api/pipeline")
_, albums = get("/api/albums")
_, accounts = get("/api/platform-accounts")

tracks = pipe["tracks"]
check("作品台账非空", len(tracks) > 0, f"{len(tracks)} 首")

for pk, acc in accounts["accounts"].items():
    reported = acc.get("song_count", 0)
    local = acc.get("local_online_count", 0)
    label = acc.get("label") or pk
    # ⚠️ **「没同步过」不是「平台说 0」。**
    #
    # 汽水没有同步脚本（netease / qq 都有 sync_*.py），platform_accounts
    # 里压根没有它那一行，song_count 就是默认值 0。而这里原本直接拿 0 去
    # 比对，报出来是「平台自报 0 vs 台账在线 1」—— 读起来像汽水在反驳我们，
    # 人会跑去后台查「为什么歌没了」，其实歌好好的，是我们从没问过它。
    #
    # 没同步过就说没同步过，不要拿缺失当数据。
    if not acc.get("synced_at"):
        check(f"{label}：平台数据", True,
              f"没同步过（台账记 {local} 首在线）—— 缺 scripts/sync_{pk}.py，无法核对")
        continue
    check(f"{label}：平台自报 vs 台账在线",
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

# 组件和 store 里不该再出现裸 fetch —— 全部走 src/api 那一层。
# 散写 fetch 的代价今天已经付过：错误处理各写各的、端点路径散落、没有类型。
raw_fetch = []
for f in list((PROJECT / "web/ui/src").rglob("*.vue")) + list((PROJECT / "web/ui/src/stores").glob("*.*")):
    if "src/api" in str(f):
        continue
    text = strip_comments(f.read_text(encoding="utf-8"))
    n = len(re.findall(r"\bfetch\s*\(", text))
    if n:
        raw_fetch.append(f"{f.name}×{n}")
check("没有绕过 api 层的裸 fetch", not raw_fetch, ", ".join(raw_fetch[:4]))

# naive-ui 组件交给 unplugin-vue-components 自动解析，不再手工注册。
# 这里只确认那套自动引入还接着 —— 它一旦掉了，所有组件会同时消失，
# 比漏注册一个更严重。
vite_cfg = (PROJECT / "web/ui/vite.config.js").read_text(encoding="utf-8")
check("naive-ui 自动按需引入已启用",
      "NaiveUiResolver" in vite_cfg and "unplugin-vue-components" in vite_cfg)

print(f"\n{'─' * 40}")
if failures:
    print(f"✗ {len(failures)}/{checks} 项没过：")
    for f in failures:
        print(f"    {f}")
    raise SystemExit(1)
print(f"✓ {checks} 项全过")
