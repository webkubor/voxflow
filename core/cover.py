"""
封面出图 —— 走 museav 中台。

## 为什么要有这个模块

平台对封面有硬性尺寸要求（汽水 ≥1440×1440、网易云 ≥1400×1400），而 Suno
给的封面只有 360×360。之前的做法是 PIL 放大 —— 放大出来是糊的，而封面是
上架物料里唯一有审美要求的东西，糊图直接影响点击率。

中台本来就是干这个的，接进来即可。

## 为什么调 HTTP 而不是 museav CLI

museav-cli 的 README 写得很清楚：CLI 是给「人在终端」和「agent 跑 shell」
用的，做产品集成一律走 HTTP API 或把 StudioClient 当库导入。VoxFlow 的后端
属于产品集成，所以直接打 `/api/generate`。

（对比 Suno：那边只有 CLI，没有可用的公开 API，所以只能 subprocess。
两边形状不一致不是随意，是上游给的条件不同。）

## 计费：一张 1 积分，**不要传 quality**

中台按成品规格计价（真源 `shared/credits-catalog.js`）：标准档 1 分、hd 档 2 分，
而 `generate.js` 是按 `quality === 'high'` 判 hd。

一开始这里传了 `quality: "high"`，想着「封面要高清」—— 那是**纯亏一倍**：

1. `quality` 是 gpt-image 系的**私有画质参数，不控制尺寸**
   （`shared/cli-meta.js`：`--quality low|medium|high（仅 gpt-image 系列）`）。
2. gen-worker 里本来就有默认：**不传 quality 时，gpt-image 系自动按 high 出**
   （index.js:615，owner 2026-08-27 要求）。
3. `providers.js` 的注释：「有带画质参数的也有不带的，单张价基本纹丝不动」——
   **上游成本不因 quality 变化**。

即：传 high 和不传，出来的画质一模一样，但计费差一倍。所以不传。

## 比例：不写死，任意 W:H

`ratio` 是可传参数，**不限枚举**。中台的 gpt-image-2 可以传任意
WIDTHxHEIGHT（约束是 16 倍数 / 长边 ≤3840 / 长短边比 ≤3:1 / 像素 655k~8.29M，
见 `shared/image-size.js`），`parseRatio` 也支持小数比例如 `1:2.1`。
museav CLI 帮助里那个 `3:4|9:16|1:1|4:3|16:9` 只是常用值提示，不是白名单。

封面默认 `1:1`（专辑封面就是方的），但调用方可以传任何比例 —— 这个模块
不该把上游的能力阉掉。合法性交给中台判定，这里只挡格式明显写错的。

## 尺寸：现在拿不到 1440×1440，而且没有「换个上游」这条路

平台要 ≥1440（汽水）/ ≥1400（网易云），实测出来是 **1254×1254**（2026-09-05，
job e2f4d996，PIL 读的真实像素）。

尺寸由 `ratio` 和上游决定，跟 quality 无关。中台**当前所有启用的出图上游都是
gpt-image-2**（查 upstream_routing_profiles：token4ai-upstream-1 / xinhankr /
tronzen / jizhi / modelgo，清一色 openai-images adapter），它们走
`resolveImage2Size(ratio, {prefer: 1_572_864})`，1:1 恒定 1254×1254。

⚠️ `providers.js` 里有个 `ratioToVolcSize`（1:1 → 2048×2048）看着像出路，
**它是死代码**：路由表里没有任何 volcengine 行（连 disabled 的都没有），
`gen_jobs` 里 volcengine 共 19 单、最后一单停在 2026-08-13。
`provider.kind === 'volcengine'` 恒为假，那个函数永远不会被调到。
（我第一次读代码时把它当成了「可选方案」，是没查路由表就下结论 —— 记在这里
免得下次又被同一段死代码骗到。）

所以现状是：**出来的封面不满足平台尺寸要求，只能当预览/试稿用**。
要真正解决，得中台那边接一个能出大图的上游 —— 那件事在 museav-manager，
不在这里。本地放大不算方案：会糊，而封面是上架物料里唯一有审美要求的东西
（见 docs/ROADMAP.md 对放大的评价）。
"""

from __future__ import annotations

import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from core import obs
from core.paths import DATA_DIR

COVERS_DIR = DATA_DIR / "library" / "covers" / "museav"

# 一张图的积分数。写死在这里而不是读 pricing.json：这是**中台的计费规则**，
# 不是我们的定价，改的时候要跟着中台的 credits-catalog.js 走。
# pricing.json 管的是「一积分值多少钱」，两件事分开。
#
# 默认走标准档（1 分）。见文件头「不要传 quality」那段：hd 档除了多扣一分，
# 换不来任何东西。
CREDITS_PER_COVER = 1
CREDITS_HD = 2          # 仅在显式传 quality='high' 时用得上，正常路径不该走到

# 封面边长。取各平台要求的最大值：汽水 ≥1440、网易云 ≥1400 —— 按 1440 出，
# 一张图两个平台都够用，不用为每个平台各出一版。
#
# 1440 是 16 的倍数（1440 = 16×90），满足中台 IMAGE2_RULES 的 step 约束；
# 1:1 时 2,073,600 像素，在 655,360~8,294,400 的区间内。
COVER_SIDE = 1440

_POLL_INTERVAL = 3.0

# 比例的写法与中台的 parseRatio 一致：`W:H`，允许小数（1:2.1）和全角冒号。
# **不在这里限定枚举** —— 中台支持任意比例（gpt-image-2 可传任意
# WIDTHxHEIGHT），CLI 帮助里那个 `3:4|9:16|1:1|4:3|16:9` 只是常用值提示。
# 写死枚举等于把上游的能力阉掉一半，而且哪天中台加了新比例这里还得跟着改。
_RATIO_RE = re.compile(r"^\d+(?:\.\d+)?\s*[:：]\s*\d+(?:\.\d+)?$")

# 常用比例，只用来给界面填下拉。**不是白名单** —— 用户输入别的照样放行，
# 合不合法由中台判定（它才是尺寸规则的真源，见 shared/image-size.js）。
COMMON_RATIOS = [
    ("1:1", "方形 · 专辑封面"),
    ("3:4", "竖版 · 海报"),
    ("4:3", "横版"),
    ("9:16", "竖屏 · 短视频封面"),
    ("16:9", "横屏 · 视频封面"),
]


def normalize_ratio(ratio: str) -> str:
    """
    校验并归一化比例。**只挡明显写错的**，不做尺寸判断。

    尺寸能不能出（16 倍数、长边 3840、长短边比 ≤3:1、像素区间）是中台的
    规则，在 `shared/image-size.js` 里，那是唯一真源。在这里复制一份判断
    只会有两个后果：要么和中台对不上，要么中台改了这边不知道。
    所以这里只做「一眼就知道不对」的格式校验，剩下的让中台报错 ——
    它的错误消息本来就写得很清楚（「长短边比 3.5:1 超过上限 3:1」）。
    """
    r = (ratio or "").strip().replace("：", ":")
    if not r:
        return "1:1"
    if not _RATIO_RE.match(r):
        raise CoverError(f"看不懂的比例「{ratio}」，要写成 W:H（如 1:1、3:4、1:2.1）")
    return r


class CoverError(RuntimeError):
    """出图失败。消息直接面向用户，不要再包一层。"""


def _base_url() -> str:
    return (os.environ.get("VOXFLOW_LLM_BASE_URL") or "").rstrip("/")


def _api_key() -> str:
    return os.environ.get("VOXFLOW_LLM_API_KEY") or ""


def available() -> bool:
    """中台配好了吗。没配就是没配，调用方据此决定是灰掉按钮还是报错。"""
    return bool(_base_url() and _api_key() and "manager.museav" in _base_url())


def _request(path: str, payload: dict | None = None, timeout: int = 30) -> dict:
    """
    打一次中台。租户 Key 走 X-API-Key（见 museav-manager 的 _middleware.js），
    同时带上 Authorization —— 两种通道中台都认，多发一个头不会有副作用，
    少发一个就可能因为哪个端点只认另一种而 401，而 401 看起来像「key 过期了」。

    **必须带 User-Agent**：默认的 Python-urllib/3.x 会被 CDN 当爬虫挡掉（403），
    而 curl 同样的请求是通的 —— 这种差异很容易被误判成「网络不通」。
    （同样的坑 web/app.py 的中台探针里也踩过，那边的注释是先例。）
    """
    key = _api_key()
    req = urllib.request.Request(
        f"{_base_url()}{path}",
        data=json.dumps(payload).encode() if payload is not None else None,
        headers={
            "X-API-Key": key,
            "Authorization": f"Bearer {key}",
            "Content-Type": "application/json",
            "User-Agent": "VoxFlow/0.4.0",
        },
        method="POST" if payload is not None else "GET",
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode())
    except urllib.error.HTTPError as e:
        # 中台的错误体是 {"error": "..."}，把它带出来 —— 「积分不足，本次需要
        # 2 积分」这种话直接给用户看就是最好的提示，包成「请求失败」反而更糟。
        try:
            detail = json.loads(e.read().decode()).get("error", "")
        except Exception:
            detail = ""
        raise CoverError(f"中台返回 {e.code}：{detail or e.reason}") from e
    except Exception as e:
        raise CoverError(f"连不上中台：{type(e).__name__} {str(e)[:80]}") from e


def balance() -> dict:
    """
    中台还剩多少积分。

    为什么值得单独暴露：积分是**硬约束** —— 没了就出不了图。顶栏早就显示
    Suno 的积分余额了，中台积分是同一性质的东西却一直看不见，结果是提交出图
    才发现「积分不足」，那时候人已经等了几秒、还以为是功能坏了。
    （2026-09-05 实测：租户余额确实已经是 0，而界面上任何地方都看不出来。）

    读不到就回 available=False，不抛异常 —— 查余额失败不该挡住别的功能。

    ⚠️ **余额是 0 不一定意味着「该充值」**。voxcraft 是自家租户，额度闸门
    本来就不该卡自己 —— 中台的 `deduct_tenant_credit` 硬检查
    `credits_balance >= amount` 且没有任何豁免，而 `_credit-charge.js` 里
    那条「负责人不吃个人额度」的例外只覆盖个人账户路径，租户拿 API Key
    直调根本进不去那个分支。真正的修法在中台侧（让 is_platform 租户跳过
    扣减），不在这里。这里只负责如实报告状态。
    """
    if not available():
        return {"available": False, "credits": 0, "unmetered": False, "detail": "未接中台"}
    try:
        d = _request("/balance", timeout=12)
        credits = int(d.get("credits") or 0)
        # unmetered = 这个主体不受额度闸门约束（自家租户）。中台在
        # 20260906090000 之后对 is_platform 租户放行扣费且不减余额，
        # 于是**余额恒为 0 而出图完全正常** —— 只看 credits 会把它误判成
        # 「用完了」然后灰掉按钮。中台的 _credits-remaining.js 里那句
        # 「否则会出现『显示 0 但能出图』」说的就是这个。
        #
        # 老版本中台不返回这个字段 → 取不到时按 False 处理，退回原来的
        # 「按余额判断」行为，不会因为升级顺序不同而误灰或误亮。
        unmetered = bool(d.get("unmetered"))
        return {"available": True, "credits": credits, "unmetered": unmetered,
                "identity": d.get("identity", ""),
                "covers_left": -1 if unmetered else credits // CREDITS_PER_COVER,
                "detail": ("自家租户，不受额度限制" if unmetered
                           else f"中台剩 {credits} 积分（够出 {credits // CREDITS_HD} 张封面）"
                           if credits else "中台余额闸门拦住了 —— 见 balance() 的说明")}
    except CoverError as e:
        return {"available": False, "credits": 0, "unmetered": False, "detail": str(e)}


def generate(
    prompt: str,
    *,
    track_id: str = "",
    ratio: str = "1:1",
    size: str = "",             # 留空则按 ratio 算一个短边 ≥1440 的合法尺寸
    quality: str = "",          # 留空 —— 见文件头，传 high 只是多扣一分
    timeout: int = 300,
    on_progress: Callable[[int, str], None] | None = None,
) -> dict:
    """
    出一张封面，等它做完，下载到本地，返回 {path, url, credits, elapsed_ms}。

    同步阻塞（内部轮询）。调用方应该把它丢进任务队列，不要在请求线程里等 ——
    出图要几十秒，而 `_run_cover_task` 已经在后台线程里跑。

    失败也计量：中台是**先扣分再入队**（见 generate.js 的流程注释），
    所以任务失败时积分已经扣了。只记成功的话账对不上。
    """
    if not available():
        raise CoverError("未接中台：需要 VOXFLOW_LLM_BASE_URL + VOXFLOW_LLM_API_KEY"
                         "（用 run.sh 启动会自动注入）")
    if not prompt.strip():
        raise CoverError("封面提示词不能为空")
    ratio = normalize_ratio(ratio)
    size = size or _size_for(ratio)

    credits = CREDITS_HD if quality == "high" else CREDITS_PER_COVER
    t0 = time.perf_counter()

    def _done(ok: bool, **meta):
        obs.meter("museav", "cover", qty=1, credits=credits, track_id=track_id,
                  duration_ms=int((time.perf_counter() - t0) * 1000), ok=ok,
                  quality=quality, ratio=ratio, **meta)

    if on_progress:
        on_progress(10, "提交中台出图...")
    try:
        # quality 为空就不发这个字段：发 quality:"" 会被中台的
        # `['low','medium','high'].includes(quality)` 判掉（忽略，行为一致），
        # 但不发更干净 —— 少一个会让人以为「我明明传了」的字段。
        payload = {"prompt": prompt.strip(), "ratio": ratio}
        if size:
            payload["size"] = size
        if quality:
            payload["quality"] = quality
        sub = _request("/generate", payload)
    except CoverError as e:
        # 提交就失败（积分不足、上游停用）—— 这种情况中台**没有**扣分，
        # 所以 credits 记 0，只留一条失败事件。把没花的钱记成花了同样是错账。
        obs.meter("museav", "cover", qty=1, credits=0, track_id=track_id,
                  duration_ms=int((time.perf_counter() - t0) * 1000), ok=False,
                  error=str(e)[:200])
        raise

    job_id = sub.get("jobId")
    if not job_id:
        _done(False, error=f"中台没有返回 jobId: {str(sub)[:120]}")
        raise CoverError(f"中台没有返回 jobId：{str(sub)[:120]}")

    # 轮询。中台是异步出图（POST 秒返 jobId，worker 在后台跑）。
    deadline = time.time() + timeout
    job: dict = {}
    while time.time() < deadline:
        time.sleep(_POLL_INTERVAL)
        try:
            job = _request(f"/jobs?id={job_id}")
        except CoverError:
            continue                      # 单次查询失败不算数，下一轮再试
        # 列表端点也可能返回数组形状，两种都收
        if isinstance(job, list):
            job = job[0] if job else {}
        status = str(job.get("status") or "").lower()
        if status in ("done", "success", "ok", "succeeded"):
            break
        if status in ("failed", "fail", "error"):
            err = job.get("error") or "中台未给出原因"
            _done(False, job_id=job_id, error=str(err)[:200])
            raise CoverError(f"出图失败：{err}")
        if on_progress:
            elapsed = int(time.time() - (deadline - timeout))
            on_progress(min(85, 20 + elapsed), f"中台出图中...（{elapsed}s）")
    else:
        _done(False, job_id=job_id, error="超时")
        raise CoverError(f"出图超时（{timeout}s）。任务 {job_id} 可能还在跑，"
                         f"去中台后台看结果。")

    cdn_url = job.get("cdn_url")
    if not cdn_url:
        _done(False, job_id=job_id, error="完成但没有 cdn_url")
        raise CoverError("中台报告完成，但没给图片地址")

    if on_progress:
        on_progress(90, "下载封面...")
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    name = f"{track_id or job_id}.png"
    dest = COVERS_DIR / name
    try:
        rq = urllib.request.Request(cdn_url, headers={"User-Agent": "VoxFlow/0.4.0"})
        with urllib.request.urlopen(rq, timeout=60) as r, dest.open("wb") as f:
            f.write(r.read())
    except Exception as e:
        # 图已经出了、分也扣了，只是没下下来 —— 记成功并把 URL 带回去，
        # 用户至少还能手动存。记成失败的话账面上会少一笔真实开销。
        _done(True, job_id=job_id, cdn_url=cdn_url, download_failed=str(e)[:80])
        raise CoverError(f"图已生成但下载失败：{str(e)[:80]}\n直链：{cdn_url}") from e

    # 校验上游有没有按请求的比例出图。
    #
    # 有的上游会**偷偷改成方图**：2026-09-05 实测 tronzen 收到 800x1680（1:2.1）
    # 返回的是 1680x1680；同一天 jizhi / xinhankr 收到 1792x1008（16:9）
    # 返回 1791x1007 / 1792x1009，是遵守的。所以这不是普遍行为，是某几家的毛病。
    #
    # 中台的 shared/image-size.js 里写着「不要偷偷改成一个接近的比例：用户拿到
    # 比例不对的图而不知情，比直接报错糟糕得多」—— 上游正在干这件事，
    # 那就由我们把它说出来。**不重试也不报错**（图是好图，只是画幅不对），
    # 只是如实带回去，让人自己决定要不要换个上游重出。
    actual = _image_size(dest)
    ratio_ok = _ratio_matches(ratio, actual)
    if actual and not ratio_ok:
        obs.log("cover_ratio_mismatch", level="warn", job_id=job_id,
                requested=ratio, actual=f"{actual[0]}x{actual[1]}",
                model=job.get("model", ""), track_id=track_id)

    _done(True, job_id=job_id, cdn_url=cdn_url, file=str(dest),
          size=f"{actual[0]}x{actual[1]}" if actual else "", ratio_ok=ratio_ok)
    return {
        "ok": True,
        "path": str(dest),
        "cdn_url": cdn_url,
        "job_id": job_id,
        "credits": credits,
        "elapsed_ms": job.get("elapsed_ms") or int((time.perf_counter() - t0) * 1000),
        "model": job.get("model", ""),
        "width": actual[0] if actual else None,
        "height": actual[1] if actual else None,
        # None = 量不出来（没装 Pillow / 文件坏了），和 False 是两回事：
        # 前者是「不知道」，后者是「确认不符」。
        "ratio_ok": ratio_ok,
        "ratio_requested": ratio,
    }


def _size_for(ratio: str, min_side: int = COVER_SIDE) -> str:
    """
    按比例算一个「短边不小于 min_side、两边都是 16 的倍数」的尺寸。

    为什么要显式算而不是只传 ratio：中台的 `ratioToSize` 把像素预算写死在
    1,572,864（而 gpt-image-2 的上限是 8,294,400，只用了 19%），1:1 只能出到
    1248×1248 —— 达不到平台要的 1440。中台已经支持传 size 绕开这个预算
    （见 20260906120000 那次改动），这里就是用它。

    算不出来（比例太极端、超出上限）就返回空串，让调用方退回「只传 ratio」——
    宁可拿一张小一点的图，也不要因为尺寸算不出来就出不了图。
    合法性的最终判定在中台（IMAGE2_RULES 是真源），这里只做够用的推算。
    """
    try:
        w_s, h_s = ratio.replace("：", ":").split(":")
        rw, rh = float(w_s), float(h_s)
    except Exception:
        return ""
    if rw <= 0 or rh <= 0:
        return ""
    # 短边定为 min_side，长边按比例放大，两边都向上取到 16 的倍数
    if rw <= rh:
        w, h = min_side, min_side * rh / rw
    else:
        w, h = min_side * rw / rh, min_side
    up16 = lambda v: int((v + 15) // 16 * 16)          # noqa: E731
    w, h = up16(w), up16(h)
    # 中台的硬约束：长边 ≤3840、总像素 ≤8,294,400。超了就放弃显式尺寸，
    # 回落到只传 ratio —— 那条路一定能出图，只是小一点。
    if max(w, h) > 3840 or w * h > 8_294_400:
        return ""
    return f"{w}x{h}"


def _image_size(path: Path) -> tuple[int, int] | None:
    """
    读图片真实像素。Pillow 不在 pyproject 的依赖里（它是被 torch 那套顺带装上的），
    所以**量不出来就返回 None**，绝不因为缺个可选依赖让出图失败 ——
    这只是一道事后校验，不是主流程。
    """
    try:
        from PIL import Image  # noqa: PLC0415
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def _ratio_matches(ratio: str, size: tuple[int, int] | None, tol: float = 0.05) -> bool | None:
    """
    实际画幅是不是请求的比例。量不出来返回 None（「不知道」≠「不符」）。

    容差 5%：上游返回的像素常有 1~2px 偏差（实测 1792x1008 → 1791x1007），
    那是正常的取整，不该报成不符。而 tronzen 那种把 1:2.1 出成 1:1 的，
    偏差远超 5%，一抓一个准。
    """
    if not size:
        return None
    try:
        w_s, h_s = str(ratio).replace("：", ":").split(":")
        want = float(w_s) / float(h_s)
    except Exception:
        return None
    w, h = size
    if not h:
        return None
    got = w / h
    return abs(got - want) / want <= tol


def build_prompt(title: str, tags: str = "", lyrics: str = "") -> str:
    """
    从作品信息拼一句封面提示词。

    不调 LLM 展开 —— 中台的模板通道（template_slug）本来就会做提示词展开，
    而这里只是给「自由出图」通道一句像样的描述。多绕一次 LLM 只是多一次
    失败点和多一笔 token 钱，换不来更好的图。

    刻意不放歌词原文：歌词进提示词容易让模型把字画到图上，而中文字在出图
    模型手里基本必然是乱码 —— 封面上有乱码汉字是最典型的 AI 味。
    """
    parts = [f"专辑封面设计，主题：{title}"]
    if tags.strip():
        parts.append(f"音乐风格：{tags.strip()}")
    parts.append("正方形构图，具有氛围感的视觉意象，画面中不要出现任何文字")
    return "，".join(parts)
