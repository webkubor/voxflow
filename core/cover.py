"""
封面出图 —— 走 museav CLI（`museav gen` + 短边不够再本地超分）。

平台要 ≥1440（汽水）/ ≥1400（网易云）。Suno 封面只有 360×360，拿来硬拉
或只超分一张不是自己的图，都不是封面。以后一律自己出：

- `museav gen` 出图（1 积分）
- 短边不够再 `museav upscale`（本地 GPU，不花积分）

本机已经登录 museav CLI（`~/.museav.json`）。Agent 和产品出封面是同一条
命令，不要再抄一份 HTTP 客户端。

| | |
|---|---|
| 计费 | 一张 1 积分。单价在 `configs/pricing.json` |
| `quality` | **不要传**。传 high 按 hd 档扣 2 分，图还是一样大 |
| `ratio` | 任意 `W:H`。CLI 没有 `--size`，短边不够就本地超分到 1440 |
| 额度 | `museav balance` 的 `unmetered`：自家租户余额可能是 0 但仍能出图 |

中台规则在 `museav-manager` 仓库，运行时状态在数据库里。不要把中台内部
实现抄到这里。
"""

from __future__ import annotations

import json
import re
import shutil
import subprocess
import time
import urllib.request
from pathlib import Path
from typing import Callable

from core import net, obs
from core.paths import DATA_DIR

COVERS_DIR = DATA_DIR / "library" / "covers" / "museav"

# 一张图消耗几个积分。写死在这里而不是读 pricing.json：这是中台的计价规则，
# pricing.json 管的是「一积分值多少钱」，两件事分开。
CREDITS_PER_COVER = 1
CREDITS_HD = 2          # 仅在显式传 quality='high' 时用得上，正常路径不该走到

# 封面边长。汽水 ≥1440、网易云 ≥1400 —— 按 1440 出，一张两个平台都够。
# 1440 = 16×90，中台要求边长按 16 对齐。
COVER_SIDE = 1440

SIZE_STEP = 16
MAX_SIDE = 3840
MAX_PIXELS = 8_294_400

_RATIO_RE = re.compile(r"^\d+(?:\.\d+)?\s*[:：]\s*\d+(?:\.\d+)?$")

# 常用比例，只用来给界面填下拉。**不是白名单**。
COMMON_RATIOS = [
    ("1:1", "方形 · 专辑封面"),
    ("3:4", "竖版 · 海报"),
    ("4:3", "横版"),
    ("9:16", "竖屏 · 短视频封面"),
    ("16:9", "横屏 · 视频封面"),
]


def normalize_ratio(ratio: str) -> str:
    """只挡明显写错的比例，尺寸合不合法由中台判定。"""
    r = (ratio or "").strip().replace("：", ":")
    if not r:
        return "1:1"
    if not _RATIO_RE.match(r):
        raise CoverError(f"看不懂的比例「{ratio}」，要写成 W:H（如 1:1、3:4、1:2.1）")
    return r


class CoverError(RuntimeError):
    """出图失败。消息直接面向用户，不要再包一层。"""


def _ca_bundle() -> str:
    """抓包代理的根证书路径，和 R2 共用一份配置。没配返回空串。"""
    from core.paths import CONFIG_DIR
    f = CONFIG_DIR / "r2.json"
    if not f.exists():
        return ""
    try:
        return json.loads(f.read_text(encoding="utf-8")).get("ca_bundle", "")
    except (OSError, ValueError):
        return ""


def _museav_bin() -> str:
    p = shutil.which("museav")
    if p:
        return p
    fallback = Path.home() / ".local/share/mise/shims/museav"
    if fallback.is_file():
        return str(fallback)
    raise CoverError("找不到 museav CLI。装好后 `museav whoami` 能跑即可")


def _museav_logged_in() -> bool:
    cfg = Path.home() / ".museav.json"
    if not cfg.is_file():
        return False
    try:
        data = json.loads(cfg.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return False
    return bool(data.get("apiKey") or data.get("token") or data.get("api_key"))


def available() -> bool:
    """museav CLI 在且已登录。调用方据此决定是灰掉按钮还是报错。"""
    try:
        _museav_bin()
    except CoverError:
        return False
    return _museav_logged_in()


def _cli_json(stdout: str) -> dict:
    """从 CLI stdout 里倒着找最后一段 JSON（人话在前、JSON 在后）。"""
    for ln in reversed((stdout or "").splitlines()):
        s = ln.strip()
        if s.startswith("{") and s.endswith("}"):
            try:
                return json.loads(s)
            except json.JSONDecodeError:
                continue
    return {}


def cdn_url_from_gen_stdout(stdout: str) -> str:
    """museav gen 成功时 stdout 最后一行是成图 URL。"""
    for ln in reversed((stdout or "").splitlines()):
        s = ln.strip()
        if s.startswith("https://"):
            return s
    raise CoverError("museav gen 没给出图片地址")


def balance() -> dict:
    """中台还剩多少积分。读不到就回 available=False，不抛异常。"""
    if not available():
        return {"available": False, "credits": 0, "unmetered": False,
                "detail": "museav CLI 未登录"}
    try:
        r = subprocess.run(
            [_museav_bin(), "balance"],
            capture_output=True, text=True, timeout=15,
        )
        d = _cli_json(r.stdout)
        if r.returncode != 0 or not d:
            err = (r.stderr or r.stdout or "balance 失败").strip()[-120:]
            return {"available": False, "credits": 0, "unmetered": False,
                    "detail": err}
        credits = int(d.get("credits") or 0)
        unmetered = bool(d.get("unmetered"))
        return {"available": True, "credits": credits, "unmetered": unmetered,
                "identity": d.get("identity", ""),
                "covers_left": -1 if unmetered else credits // CREDITS_PER_COVER,
                "detail": ("自家租户，不受额度限制" if unmetered
                           else f"中台剩 {credits} 积分（够出 {credits // CREDITS_PER_COVER} 张封面）"
                           if credits else "中台余额闸门拦住了 —— 见 balance() 的说明")}
    except (CoverError, OSError, subprocess.TimeoutExpired) as e:
        return {"available": False, "credits": 0, "unmetered": False,
                "detail": str(e)[:120]}


def generate(
    prompt: str,
    *,
    track_id: str = "",
    ratio: str = "1:1",
    size: str = "",
    quality: str = "",
    timeout: int = 300,
    on_progress: Callable[[int, str], None] | None = None,
) -> dict:
    """
    `museav gen` 出一张封面，下载到本地。短边 < 1440 且是方图时再本地超分。

    size 参数保留只为兼容调用方：CLI 没有 --size。
    """
    _ = size
    if not available():
        raise CoverError("museav CLI 未登录。终端跑一次 `museav login`")
    if not prompt.strip():
        raise CoverError("封面提示词不能为空")
    ratio = normalize_ratio(ratio)

    credits = CREDITS_HD if quality == "high" else CREDITS_PER_COVER
    t0 = time.perf_counter()

    def _done(ok: bool, **meta):
        obs.meter("museav", "cover", qty=1, credits=credits, track_id=track_id,
                  duration_ms=int((time.perf_counter() - t0) * 1000), ok=ok,
                  quality=quality, ratio=ratio, **meta)

    cmd = [_museav_bin(), "gen", "-p", prompt.strip(), "-r", ratio]
    if quality:
        cmd += ["-q", quality]
    if on_progress:
        on_progress(10, "museav gen 出图中…")
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        _done(False, error="超时")
        raise CoverError(f"出图超时（{timeout}s）") from None
    except OSError as e:
        obs.meter("museav", "cover", qty=1, credits=0, track_id=track_id,
                  duration_ms=int((time.perf_counter() - t0) * 1000), ok=False,
                  error=str(e)[:200])
        raise CoverError(f"拉不起 museav：{e}") from e

    if r.returncode != 0:
        err = (r.stderr or r.stdout or "出图失败").strip()[-400:]
        no_charge = "积分不足" in err or "未登录" in err or "login" in err.lower()
        obs.meter("museav", "cover", qty=1, credits=0 if no_charge else credits,
                  track_id=track_id,
                  duration_ms=int((time.perf_counter() - t0) * 1000), ok=False,
                  error=err[:200])
        raise CoverError(err)

    try:
        cdn_url = cdn_url_from_gen_stdout(r.stdout)
    except CoverError as e:
        _done(False, error=str(e)[:200])
        raise

    if on_progress:
        on_progress(70, "下载封面…")
    COVERS_DIR.mkdir(parents=True, exist_ok=True)
    dest = COVERS_DIR / f"{track_id or int(time.time())}.png"
    try:
        rq = urllib.request.Request(cdn_url, headers={"User-Agent": "VoxFlow/0.4.0"})
        with net.opener(_ca_bundle(), False).open(rq, timeout=60) as resp, dest.open("wb") as f:
            f.write(resp.read())
    except Exception as e:
        _done(True, cdn_url=cdn_url, download_failed=str(e)[:80])
        raise CoverError(f"图已生成但下载失败：{str(e)[:80]}\n直链：{cdn_url}") from e

    actual = _image_size(dest)
    if actual and min(actual) < COVER_SIDE and ratio == "1:1":
        if on_progress:
            on_progress(80, f"短边 {min(actual)} < {COVER_SIDE}，本地超分…")
        up_dest = dest.with_name(dest.stem + f"_{COVER_SIDE}.jpg")
        dest = upscale_local(dest, up_dest)
        actual = _image_size(dest)

    ratio_ok = _ratio_matches(ratio, actual)
    if actual and not ratio_ok:
        obs.log("cover_ratio_mismatch", level="warn",
                requested=ratio, actual=f"{actual[0]}x{actual[1]}",
                track_id=track_id)

    _done(True, cdn_url=cdn_url, file=str(dest),
          size=f"{actual[0]}x{actual[1]}" if actual else "", ratio_ok=ratio_ok)
    return {
        "ok": True,
        "path": str(dest),
        "cdn_url": cdn_url,
        "job_id": "",
        "credits": credits,
        "elapsed_ms": int((time.perf_counter() - t0) * 1000),
        "model": "",
        "width": actual[0] if actual else None,
        "height": actual[1] if actual else None,
        "ratio_ok": ratio_ok,
        "ratio_requested": ratio,
    }


def upscale_local(
    src: Path,
    dest: Path,
    *,
    scale: int = 2,
    on_progress: Callable[[int, str], None] | None = None,
) -> Path:
    """本地 Real-ESRGAN 超分（museav upscale），再落到 1440 方图。不花积分。"""
    bin_path = _museav_bin()
    src = Path(src)
    dest = Path(dest)
    if not src.is_file():
        raise CoverError(f"没有这张图：{src}")
    if on_progress:
        on_progress(15, "本地 GPU 超分中…")
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_name(dest.stem + f".{scale}x.png")
    r = subprocess.run(
        [bin_path, "upscale", str(src), "--out", str(tmp),
         "--scale", str(scale), "--overwrite"],
        capture_output=True, text=True, timeout=300,
    )
    if r.returncode != 0:
        raise CoverError((r.stderr or r.stdout or "超分失败")[-400:])
    if on_progress:
        on_progress(75, f"裁到 {COVER_SIDE}×{COVER_SIDE}…")
    from PIL import Image
    with Image.open(tmp) as im:
        out = im.convert("RGB").resize((COVER_SIDE, COVER_SIDE), Image.Resampling.LANCZOS)
        out.save(dest, quality=92)
    if tmp != dest and tmp.exists():
        tmp.unlink(missing_ok=True)
    if on_progress:
        on_progress(100, "完成")
    return dest


def _size_for(ratio: str, min_side: int = COVER_SIDE) -> str:
    """按比例算一个短边不小于 min_side、两边都是 16 倍数的尺寸。给界面展示用。"""
    try:
        w_s, h_s = ratio.replace("：", ":").split(":")
        rw, rh = float(w_s), float(h_s)
    except Exception:
        return ""
    if rw <= 0 or rh <= 0:
        return ""
    if rw <= rh:
        w, h = min_side, min_side * rh / rw
    else:
        w, h = min_side * rw / rh, min_side
    align = lambda v: int((v + SIZE_STEP - 1) // SIZE_STEP * SIZE_STEP)   # noqa: E731
    w, h = align(w), align(h)
    if max(w, h) > MAX_SIDE or w * h > MAX_PIXELS:
        return ""
    return f"{w}x{h}"


def _image_size(path: Path) -> tuple[int, int] | None:
    """读图片真实像素。量不出来返回 None，不让缺 Pillow 挡住出图。"""
    try:
        from PIL import Image  # noqa: PLC0415
        with Image.open(path) as im:
            return im.size
    except Exception:
        return None


def _ratio_matches(ratio: str, size: tuple[int, int] | None, tol: float = 0.05) -> bool | None:
    """实际画幅是不是请求的比例。量不出来返回 None。"""
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
    """从作品信息拼一句封面提示词。不放歌词，避免模型把字画到图上。"""
    parts = [f"专辑封面设计，主题：{title}"]
    if tags.strip():
        parts.append(f"音乐风格：{tags.strip()}")
    parts.append("正方形构图，具有氛围感的视觉意象，画面中不要出现任何文字")
    return "，".join(parts)
