"""直连 Suno HTTP API —— 不再依赖外部 suno CLI。

## 为什么要自己实现

2026-09-11 Suno 服务端强推 v6：老模型一律 403 `paid_upsell`
（"You don't have access to this model. Please switch to v6!"），
而 `paperfoot/suno-cli` 0.9.0 的 `--model` 枚举最高只到 v5.5，
上游 2026-07-20 之后再没更新。等它 = 无限期停工。

模型在 API 里传的是**代号**不是版本号，而且是随机词（凤凰、鹰、比目鱼），
靠命名规律推不出来 —— `MODELS` 那张表是从 suno.com 前端 bundle 的
`ModelTier` 映射里挖出来的，不是猜的。Suno 出新版本时这张表要跟着更新：
下载 suno.com 首页，把 `/_next/static/immutable/chunks/*.js` 全抓下来
`grep -oE 'chirp-[a-z0-9-]+'`，再找 `ModelTier.V6]:"chirp-hawk"` 那段映射。

## 认证：自己维护，不经过 suno CLI

Suno 用 Clerk 做身份，两层凭据：

- `__client` cookie —— 长效（~7 天），是真正的身份，只能从浏览器拿。
- JWT —— **约 1 分钟就过期**，每次调用前用 `__client` 换一把新的。

所以「登录一次就能一直用」靠的是自动换 JWT（`refresh_jwt()`），不是把 JWT 存下来。
早期版本直接读 suno CLI 存的 JWT，结果隔一分钟就 401 —— 那不是 bug，
是把短命令牌当长凭据用。

凭据存 `~/.voxflow/suno.json`（0600）。首次会自动从 suno CLI 的 auth.json
导入一次 `__client`，导入后就跟 CLI 无关了；CLI 删掉也不影响。
`__client` 也过期时跑 `login()`，从日常 Chrome 里取一把新的。

## hCaptcha：借 browser-harness，不抄那 958 行

`POST /api/c/check` 说这个账号 `required: true`，纯 HTTP 客户端拿不到 token
（hCaptcha 要在真实浏览器里跑 `hcaptcha.execute()`）。suno-cli 为此写了
958 行 Chrome 生命周期管理 + headless 反检测。

这里复用项目已有的 `browser-harness`：它附着的就是用户日常那个 Chrome，
已登录 suno、已被 hCaptcha 认作真人，实测 8 秒出 token，一行都不用抄。
代价是**必须有一个能开图形界面的 Chrome**，纯服务器跑不了 —— 对一个
装在自己机器上的本地工具，这个前提本来就成立。
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Any

from core.net import opener
from core.paths import DATA_DIR, IS_WINDOWS

_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
       "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36")
BASE = "https://studio-api-prod.suno.com"
SITEKEY = "d65453de-3f1a-4aac-9366-a0f06e52b2ce"
CRED_FILE = DATA_DIR / "suno.json"
# 一次性导入源：suno CLI 的凭据。导入后不再读它，CLI 删掉也不影响。
# 它自己按平台放在不同位置（Rust 的 directories crate 约定），路径不存在就
# 走「跑 login」那条分支，不会崩 —— 所以没装过 CLI 的机器也正常。
_LEGACY_CLI_AUTH = (
    Path(os.environ.get("APPDATA", Path.home())) / "com.suno-cli.suno-cli" / "data" / "auth.json"
    if IS_WINDOWS
    else Path.home() / "Library/Application Support/com.suno-cli.suno-cli/auth.json"
)

CLERK_BASE = "https://auth.suno.com"
_CLERK_V = "?__clerk_api_version=2025-11-10&_clerk_js_version=5.117.0"

# 版本号 → API 代号。见文件头「为什么要自己实现」，别手改成猜的值。
MODELS = {
    "v6": "chirp-hawk",
    "v6-mini": "chirp-goose",
    "v5.5": "chirp-fenix",
    "v5": "chirp-crow",
    "v4.5+": "chirp-bluejay",
    "v4.5": "chirp-auk",
    "v4": "chirp-v4",
    "v3.5": "chirp-v3-5",
}
DEFAULT_MODEL = "v6"


class SunoError(RuntimeError):
    """调用失败。message 是给人看的，不要再包一层。"""


def _load() -> dict[str, Any]:
    if CRED_FILE.exists():
        return json.loads(CRED_FILE.read_text())
    if _LEGACY_CLI_AUTH.exists():
        d = json.loads(_LEGACY_CLI_AUTH.read_text())
        _save(d)
        return d
    raise SunoError("没有 Suno 凭据 —— 跑一次 `voice suno login`（会打开浏览器）")


def _save(d: dict[str, Any]) -> None:
    CRED_FILE.parent.mkdir(parents=True, exist_ok=True)
    CRED_FILE.write_text(json.dumps(d, indent=2))
    CRED_FILE.chmod(0o600)   # 默认 644 会让同机其它用户读到身份凭据


def _clerk_headers(client_cookie: str) -> dict[str, str]:
    return {"authorization": client_cookie, "cookie": f"__client={client_cookie}",
            "origin": "https://suno.com", "referer": "https://suno.com/",
            "User-Agent": _UA}


def refresh_jwt() -> str:
    """用长效 `__client` cookie 换一把新 JWT，写回凭据文件。

    两步，缺一不可：先 GET /v1/client 拿当前 session id，再 POST 那个
    session 的 tokens。session id 不能缓存太久 —— 换设备登录会让它失效。
    """
    d = _load()
    cc = d.get("clerk_client_cookie") or ""
    if not cc:
        raise SunoError("凭据里没有 __client —— 跑一次 `voice suno login`")
    h = _clerk_headers(cc)
    r = json.loads(opener().open(
        urllib.request.Request(f"{CLERK_BASE}/v1/client{_CLERK_V}", headers=h), timeout=30).read())
    resp = r.get("response") or {}
    sid = resp.get("last_active_session_id") or ((resp.get("sessions") or [{}])[0] or {}).get("id")
    if not sid:
        raise SunoError("Clerk 里没有活跃 session —— 先在浏览器登录 suno.com，再跑 `voice suno login`")
    req = urllib.request.Request(f"{CLERK_BASE}/v1/client/sessions/{sid}/tokens{_CLERK_V}",
                                 data=b"", method="POST",
                                 headers={**h, "content-type": "application/x-www-form-urlencoded"})
    jwt = json.loads(opener().open(req, timeout=30).read()).get("jwt") or ""
    if not jwt:
        raise SunoError("Clerk 没有返回 JWT —— __client 可能过期了，跑 `voice suno login`")
    d["jwt"], d["session_id"] = jwt, sid
    _save(d)
    return jwt


def _browser_token() -> str:
    """Suno 要的 browser-token：就是个 base64 时间戳，没有校验意义但缺了会 4xx。"""
    payload = json.dumps({"timestamp": int(time.time() * 1000)}, separators=(",", ":"))
    return json.dumps({"token": base64.b64encode(payload.encode()).decode()}, separators=(",", ":"))


def _request(path: str, body: dict | None = None, timeout: int = 60, _retried: bool = False) -> Any:
    a = _load()
    headers = {
        "Authorization": f"Bearer {a['jwt']}",
        "Cookie": a.get("cookie", ""),
        "device-id": a.get("device_id") or "00000000-0000-0000-0000-000000000000",
        "browser-token": _browser_token(),
        "Origin": "https://suno.com",
        "Referer": "https://suno.com/",
        "Content-Type": "application/json",
        "User-Agent": _UA,
    }
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers,
                                 method="POST" if data else "GET")
    try:
        with opener().open(req, timeout=timeout) as r:
            return json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:400]
        # JWT 只活约 1 分钟，401 是常态不是异常 —— 换一把再打一次。
        # 只重试一次：__client 也失效时会连着 401，无限重试会把人卡死在这。
        if e.code == 401 and not _retried:
            refresh_jwt()
            return _request(path, body, timeout, _retried=True)
        if e.code == 401:
            raise SunoError("凭据失效 —— 跑一次 `voice suno login` 重新授权") from e
        raise SunoError(f"HTTP {e.code}: {detail}") from e


def captcha_required() -> bool:
    """这个账号生成时要不要过验证码。只读，不花钱。"""
    return bool(_request("/api/c/check", {"ctype": "generation"}).get("required"))


def credits() -> dict[str, Any]:
    """余额与套餐。只读，不花钱。"""
    d = _request("/api/billing/info/")
    return {"left": d.get("total_credits_left"), "monthly_usage": d.get("monthly_usage"),
            "monthly_limit": d.get("monthly_limit"),
            "plan": (d.get("plan") or {}).get("name", "")}


def solve_captcha(timeout_s: int = 90) -> str:
    """在日常 Chrome 里解一个 hCaptcha token。

    走 browser-harness 而不是自己起浏览器：登录态和"真人信誉"都在那个
    Chrome 上，另起一个干净实例反而更容易被 hCaptcha 挡。
    """
    script = f"""
ensure_real_tab()
import time, json as _j
if "suno.com" not in (page_info().get("url") or ""):
    goto_url("https://suno.com/create"); time.sleep(6)
js('''(() => {{
  window.__vfCap = {{state:'start'}};
  try {{
    let el = document.getElementById('vf-cap');
    if (!el) {{ el = document.createElement('div'); el.id='vf-cap'; el.style.display='none'; document.body.appendChild(el); }}
    const id = window.hcaptcha.render('vf-cap', {{sitekey:'{SITEKEY}', size:'invisible'}});
    window.hcaptcha.execute(id, {{async:true}})
      .then(r => {{ window.__vfCap = {{state:'ok', token:(r && r.response) ? r.response : String(r)}}; }})
      .catch(e => {{ window.__vfCap = {{state:'err', err:String(e).slice(0,160)}}; }});
  }} catch(e) {{ window.__vfCap = {{state:'throw', err:String(e).slice(0,160)}}; }}
  return 'started';
}})()''')
for _ in range({timeout_s // 3}):
    time.sleep(3)
    s = _j.loads(js("JSON.stringify(window.__vfCap)"))
    if s.get("state") != "start":
        print("VFCAP:" + _j.dumps(s)); break
else:
    print('VFCAP:{{"state":"timeout"}}')
"""
    p = subprocess.run(["browser-harness"], input=script, capture_output=True,
                       text=True, timeout=timeout_s + 30)
    line = next((l for l in p.stdout.splitlines() if l.startswith("VFCAP:")), "")
    if not line:
        raise SunoError(f"解验证码失败，browser-harness 没有回话：{p.stderr[-300:]}")
    s = json.loads(line[len("VFCAP:"):])
    if s.get("state") != "ok":
        raise SunoError(f"解验证码失败：{s}")
    return s["token"]


def generate(title: str, tags: str, *, instrumental: bool = False,
             lyrics: str = "", model: str = DEFAULT_MODEL,
             _extra: dict | None = None) -> list[dict]:
    """提交一次生成，返回 clip 列表（通常两首）。**这一步花积分。**

    lyrics 为空 = inspiration 模式（Suno 自己写词）；BGM 请传 instrumental=True。
    """
    mv = MODELS.get(model, model)   # 也允许直接传 chirp-* 代号
    body = {
        "token": solve_captcha() if captcha_required() else None,
        "generation_type": "TEXT",
        "title": title or None,
        "tags": tags or None,
        "negative_tags": "",
        "mv": mv,
        "prompt": lyrics,
        "make_instrumental": instrumental,
        "user_uploaded_images_b64": None,
        "metadata": {
            "web_client_pathname": "/create",
            "is_max_mode": False,
            "is_mumble": False,
            "create_mode": "custom",
            "user_tier": "",
            "create_session_token": str(uuid.uuid4()),
            "disable_volume_normalization": False,
        },
        "override_fields": [],
        "cover_clip_id": None, "cover_start_s": None, "cover_end_s": None,
        "persona_id": None,
        "artist_clip_id": None, "artist_start_s": None, "artist_end_s": None,
        "continue_clip_id": None, "continued_aligned_prompt": None, "continue_at": None,
        "transaction_uuid": str(uuid.uuid4()),
    }
    for k, v in (_extra or {}).items():
        if k == "metadata_create_mode":
            body["metadata"]["create_mode"] = v
        elif k == "metadata_control_sliders":
            body["metadata"]["control_sliders"] = v
        else:
            body[k] = v
    r = _request("/api/generate/v2-web/", body, timeout=120)
    clips = r.get("clips") or []
    # HTTP 200 + status=error 或空 clips 都是失败：积分可能已经报价，但什么都没建。
    # 当成功处理会让调用方去轮询一个不存在的 id，最后超时收场，看不出真因。
    if str(r.get("status", "")).lower() == "error" or not clips:
        raise SunoError(f"Suno 拒绝了这次生成：{json.dumps(r, ensure_ascii=False)[:300]}")
    return clips


def get_clips(clip_ids: list[str]) -> list[dict]:
    """按 id 批量查 clip。只读，不花钱。

    两个坑，都是照抄会踩的：路径是 `/api/feed/`**不是** `/api/feed/v3`
    （v3 是列库用的，不认 ids 参数），响应体**直接是数组**不是 {clips:[...]}；
    而且一次最多 2 个 id —— 多了会被截断，且不报错。
    """
    out: list[dict] = []
    for i in range(0, len(clip_ids), 2):
        chunk = ",".join(clip_ids[i:i + 2])
        r = _request(f"/api/feed/?ids={chunk}")
        out.extend(r if isinstance(r, list) else r.get("clips") or [])
    return out


# 音频 CDN。**不要用 clip 里的 audio_url** —— 那个字段现在返回
# "https://studio-api.prod.suno.com/api/forbidden"，Suno 把 API 侧的直链关了。
# 网页播放器实际拉的是这个 CloudFront 地址，无签名、无 Referer 校验，
# 拿 clip id 拼出来就能下（2026-09-12 抓浏览器网络请求得到）。
# 它要是哪天也关了，重新抓一次：playwright 打开歌曲页，看 .m4a 那条请求。
_AUDIO_CDN = "https://d2lwuy8qc234o3.cloudfront.net/1/clip/{clip_id}.m4a"


def download(clip_id: str, dest: "pathlib.Path | str") -> int:
    """把一首歌的音频下到本地，返回字节数。只读 CDN，不花积分。"""
    import shutil

    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)
    req = urllib.request.Request(_AUDIO_CDN.format(clip_id=clip_id), headers={"User-Agent": _UA})
    with opener().open(req, timeout=300) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)
    return dest.stat().st_size


def poll(clip_ids: list[str], timeout_s: int = 600, interval_s: int = 8) -> list[dict]:
    """轮询到每个 clip 都进终态（complete / error）。只读，不额外花钱。"""
    deadline = time.time() + timeout_s
    clips: list[dict] = []
    while time.time() < deadline:
        clips = get_clips(clip_ids)
        # 按**请求的 id** 判断而不是返回的列表：少返回一个 id 也是「还没好」，
        # 用返回列表判断会在部分完成时提前收工，下载到一半的东西。
        done = {c["id"] for c in clips if c.get("status") in ("complete", "error")}
        if all(i in done for i in clip_ids):
            return clips
        time.sleep(interval_s)
    got = {c.get("id") for c in clips}
    raise SunoError(f"等待超时（{timeout_s}s），未完成：{[i for i in clip_ids if i not in got]}")


def list_clips(limit: int = 20, cursor: str = "") -> dict:
    """列作品库。只读，不花钱。翻页用返回里的 next_cursor —— feed/v3 不认页码。"""
    # 空字段必须**整个不发**，不能发 null —— 服务端把 filters 当 dict 校验，
    # 发 null 直接 422（`Input should be a valid dictionary`）。
    body: dict = {"limit": limit}
    if cursor:
        body["cursor"] = cursor
    r = _request("/api/feed/v3", body)
    return {"clips": r.get("clips") or [], "next_cursor": r.get("next_cursor")}


def cover(clip_id: str, *, tags: str = "", model: str = DEFAULT_MODEL,
          audio_influence: float | None = None) -> list[dict]:
    """翻唱一首已有的 clip。**这一步花积分。**

    走的还是 /api/generate/v2-web/，只是带上 cover_clip_id。
    `audio_influence` 是界面上的 0-100，API 收的是 0-1 的 audio_weight。
    """
    extra: dict = {"cover_clip_id": clip_id, "metadata_create_mode": "cover"}
    if audio_influence is not None:
        v = float(audio_influence)
        extra["metadata_control_sliders"] = {"audio_weight": v / 100 if v > 1 else v}
    return generate("", tags, model=model, _extra=extra)


if __name__ == "__main__":
    # 只读自检，不花一分钱：凭据能用、余额读得到、验证码策略明确、模型表非空。
    c = credits()
    assert c["left"] is not None, "读不到余额"
    req = captcha_required()
    assert MODELS["v6"] == "chirp-hawk", "v6 代号被改坏了"
    print(f"✓ 凭据可用 · {c['plan']} · 剩 {c['left']} · 本月已用 {c['monthly_usage']}/{c['monthly_limit']}")
    print(f"✓ 验证码：{'每次生成都要解' if req else '不需要'}")
    print(f"✓ 默认模型 {DEFAULT_MODEL} → {MODELS[DEFAULT_MODEL]}")
