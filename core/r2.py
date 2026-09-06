"""Cloudflare R2 上传 —— 把生成的音频/封面变成一条公网直链。

## 为什么需要它

台账里「音乐地址」那一栏是给**别人**看的：负责发行的人拿到一行，
第一件事就是下载音频和封面去平台上传。本地路径对他毫无意义。

## 为什么是手写签名，不是 boto3

voxflow 是开源项目，装一个 50MB 的 botocore 只为了 PUT 一个文件不划算 ——
别人 clone 下来跑本地 TTS，凭什么要为一个可选的云存储付这个代价。

R2 兼容 S3 协议，而 S3 的 SigV4 签名用 stdlib 的 hmac/hashlib 就能算完，
六十行。跟 `core/cover.py` 一样：零第三方依赖，stdlib urllib 打天下。

## ⚠️ 配置只在本地，永远不进仓库

`~/.voxflow/configs/r2.json`（或环境变量）。这个文件里是 access key，
**泄露等于别人可以往你的桶里写任何东西、也可以删光它**。

数据目录本来就在仓库外（见 `core/paths.py`），所以只要不把它复制进项目目录
就是安全的。代码里不写任何默认值、不留任何示例密钥。

## 没配 = 功能关闭，不是错误

绝大多数人跑 voxflow 只用本地 TTS，根本不需要云存储。所以没配置时
`upload()` 安静返回空串，调用方按「没有链接」处理即可 —— 不抛、不刷日志。
"""
from __future__ import annotations

import hashlib
import hmac
import json
import mimetypes
import os
import ssl
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

from core import obs
from core.paths import CONFIG_DIR

CONFIG_FILE = CONFIG_DIR / "r2.json"
TIMEOUT_S = 120          # 音频文件可能几十 MB，别用默认的短超时
REGION = "auto"          # R2 固定 auto
SERVICE = "s3"


def _ssl_context() -> ssl.SSLContext:
    """带根证书的 SSL context。

    ⚠️ 不能只用 `ssl.create_default_context()`。macOS 上的 Python
    （python.org 安装包、homebrew、pyenv 都可能）**默认找不到根证书** ——
    `ssl.get_default_verify_paths()` 指向一个不存在的 openssl 目录，
    于是每个 https 请求都是 `CERTIFICATE_VERIFY_FAILED: unable to get
    local issuer certificate`。

    这个错看起来像「对方证书有问题」，实际是本机根本没有信任库，
    换个机器又好了 —— 最难查的那类环境问题。

    certifi 在依赖树里本来就有（transformers 带的），直接用它兜底。
    **绝不能改成 `verify=False` 那种绕法** ——那是把中间人攻击的门打开，
    而这里传的是要公开分发的资产、用的是能写整个桶的密钥。

    ## 抓包代理（Reqable / Charles / mitmproxy）

    本机开着 HTTPS 抓包代理时，**certifi 也救不了** —— 代理做的就是中间人，
    它出示的是自己签的证书，本来就不在任何公共信任库里。
    症状一模一样（`CERTIFICATE_VERIFY_FAILED`），但根因完全不同，
    很容易顺着「证书」这个词一路查到 CA 去，其实是代理的问题。

    识别方法：`scutil --proxy | grep HTTPSProxy` 有值就是它。

    解法是在 `r2.json` 里配 `ca_bundle` 指向一份**合并了代理根证书**的
    pem（代理的 CA 通常在系统钥匙串里，可以导出来和 certifi 的拼在一起）。
    关掉代理也行。**不要改成不验证证书** —— 这里用的密钥能写整个桶。
    """
    cfg = config()
    if (bundle := cfg.get("ca_bundle")) and Path(bundle).expanduser().is_file():
        return ssl.create_default_context(cafile=str(Path(bundle).expanduser()))
    try:
        import certifi
        return ssl.create_default_context(cafile=certifi.where())
    except ImportError:
        return ssl.create_default_context()


def config() -> dict:
    """R2 配置。环境变量优先，方便 CI/容器注入而不落盘。"""
    cfg: dict = {}
    if CONFIG_FILE.exists():
        try:
            cfg = json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as e:
            obs.log("r2_config_bad", level="warn", error=str(e)[:120])
    for env_key, cfg_key in (
        ("R2_ACCOUNT_ID", "account_id"),
        ("R2_ACCESS_KEY_ID", "access_key_id"),
        ("R2_SECRET_ACCESS_KEY", "secret_access_key"),
        ("R2_BUCKET", "bucket"),
        ("R2_PUBLIC_BASE", "public_base"),
    ):
        if v := os.environ.get(env_key):
            cfg[cfg_key] = v
    return cfg


def enabled() -> bool:
    c = config()
    return all(c.get(k) for k in
               ("account_id", "access_key_id", "secret_access_key", "bucket"))


def _sign(key: bytes, msg: str) -> bytes:
    return hmac.new(key, msg.encode("utf-8"), hashlib.sha256).digest()


def _auth_headers(cfg: dict, method: str, host: str, path: str,
                  payload_sha: str, content_type: str) -> dict[str, str]:
    """AWS SigV4。

    签名覆盖的 header 必须和实际发出去的**一字不差**（顺序、大小写、空格），
    差一个字节就是 403 SignatureDoesNotMatch，而错误信息不会告诉你差在哪。
    所以这里把 signed_headers 和 headers 从同一份数据生成，杜绝两处不同步。
    """
    now = datetime.now(timezone.utc)
    amz_date = now.strftime("%Y%m%dT%H%M%SZ")
    date_stamp = now.strftime("%Y%m%d")

    signed = {
        "content-type": content_type,
        "host": host,
        "x-amz-content-sha256": payload_sha,
        "x-amz-date": amz_date,
    }
    signed_headers = ";".join(sorted(signed))
    canonical_headers = "".join(f"{k}:{signed[k]}\n" for k in sorted(signed))
    canonical_request = "\n".join([
        method,
        # ⚠️ path 传进来时**已经是编码过的**，这里绝不能再 quote 一次。
        # 编码两次的后果极其阴险：ASCII 文件名 quote 是空操作，照传不误；
        # 只有中文名会变成 %25E9%2580%2586（%25 是 % 自己被编码），
        # 于是签名算的是双编码路径、请求发的是单编码路径，对不上 → 服务器拒绝。
        # 而大文件在服务器读完 body 前就被拒，客户端看到的是
        # `Broken pipe` 而不是 403 —— 一个看起来像网络问题的鉴权错误。
        path,
        "",                                  # 无 query
        canonical_headers,
        signed_headers,
        payload_sha,
    ])
    scope = f"{date_stamp}/{REGION}/{SERVICE}/aws4_request"
    to_sign = "\n".join([
        "AWS4-HMAC-SHA256", amz_date, scope,
        hashlib.sha256(canonical_request.encode("utf-8")).hexdigest(),
    ])
    k = _sign(f"AWS4{cfg['secret_access_key']}".encode(), date_stamp)
    for part in (REGION, SERVICE, "aws4_request"):
        k = _sign(k, part)
    signature = hmac.new(k, to_sign.encode("utf-8"), hashlib.sha256).hexdigest()

    return {
        **{key: val for key, val in signed.items() if key != "host"},
        "Authorization": (f"AWS4-HMAC-SHA256 Credential={cfg['access_key_id']}/{scope}, "
                          f"SignedHeaders={signed_headers}, Signature={signature}"),
    }


def _opener() -> urllib.request.OpenerDirector:
    """构造 opener，**默认绕过系统代理**。

    音频动辄几 MB 到几十 MB，走本机抓包代理（Reqable / Charles）会
    `Broken pipe` —— 代理为了能展示请求体会先整个缓存下来，大文件直接把它撑爆。
    而且资产上传本来也没有抓包的价值：内容就是那个文件本身。

    所以默认不走代理。真需要经过代理（比如公司网络只允许代理出网），
    在 `r2.json` 里设 `"use_proxy": true`。

    ⚠️ 这条和上面的 `ca_bundle` 是**同一个问题的两半**：代理先让证书验不过
    （CERTIFICATE_VERIFY_FAILED），信任了它之后再让大文件传不上去
    （Broken pipe）。只解决前一半会以为快好了，其实还差一半。
    """
    handlers: list = [urllib.request.HTTPSHandler(context=_ssl_context())]
    if not config().get("use_proxy"):
        handlers.append(urllib.request.ProxyHandler({}))   # 空 dict = 不走任何代理
    return urllib.request.build_opener(*handlers)


def upload(path: str | Path, key: str = "") -> str:
    """上传一个文件，返回公网直链。**没配置或失败都返回空串，不抛。**

    `key` 不传就用 `<prefix>/<文件名>`。同名会**覆盖** —— voxflow 的文件名
    自带时间戳（`[Suno]标题_20260906_143012.mp3`），天然不重名。
    """
    cfg = config()
    if not enabled():
        return ""
    p = Path(path)
    if not p.is_file():
        obs.log("r2_upload_skip", level="warn", reason="文件不存在", path=str(p)[:160])
        return ""

    key = key or f"{cfg.get('prefix', 'voxflow').strip('/')}/{p.name}"
    body = p.read_bytes()
    payload_sha = hashlib.sha256(body).hexdigest()
    content_type = mimetypes.guess_type(p.name)[0] or "application/octet-stream"
    host = f"{cfg['account_id']}.r2.cloudflarestorage.com"
    obj_path = f"/{cfg['bucket']}/{urllib.parse.quote(key)}"

    headers = _auth_headers(cfg, "PUT", host, obj_path, payload_sha, content_type)
    req = urllib.request.Request(f"https://{host}{obj_path}", data=body,
                                 headers=headers, method="PUT")
    try:
        with _opener().open(req, timeout=TIMEOUT_S) as resp:
            if resp.status not in (200, 201):
                raise urllib.error.HTTPError(req.full_url, resp.status,
                                             "unexpected status", resp.headers, None)
    except urllib.error.HTTPError as e:
        # R2 的错误正文里有 <Code>，比状态码有用得多（AccessDenied vs NoSuchBucket）
        detail = ""
        try:
            detail = e.read().decode("utf-8", "replace")[:200]
        except Exception:  # noqa: BLE001
            pass
        obs.log("r2_upload_failed", level="error", key=key,
                error=f"HTTP {e.code} {detail}")
        return ""
    except (urllib.error.URLError, TimeoutError, OSError) as e:
        obs.log("r2_upload_failed", level="error", key=key, error=str(e)[:160])
        return ""

    base = (cfg.get("public_base") or "").rstrip("/")
    if not base:
        # 桶没开公网访问就没有可分享的链接。返回空串而不是拼一个打不开的地址 ——
        # 台账里放一条 404 链接，比空着更浪费别人时间。
        obs.log("r2_no_public_base", level="warn", key=key)
        return ""
    return f"{base}/{urllib.parse.quote(key)}"
