"""MUSE AV 应用授权（设备码流程）—— 用用户自己的账户，不用租户 Key。

## 为什么要换掉租户 Key

文案（LLM）这条线原来靠环境变量注入 voxcraft **租户** Key。租户模型的含义是
「应用方持 Key、花应用方的池子」—— 对 VoxFlow 是错的：它是装在用户自己机器上的
工具，该花的是**用户自己的积分**，产出也该归用户自己。而且租户 Key 一旦发出去就
只能整把吊销，事后也查不出哪一次调用是哪个工具发的。

应用授权解决的正是这三件事：一个应用一把 Key、用户能单独撤销、中台能记下
是哪个应用代表用户调的。

## 与封面出图的关系

封面出图走的是 `museav` CLI（`~/.museav.json` 里的**全局**账户 Key），
那把 Key 给了 voxflow 就等于给了本机所有工具。这里不动它 —— 换掉租户 Key 是
当前的目标；CLI 那条线另议（见 README 的「凭据」一节）。
"""

from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
import webbrowser
from pathlib import Path
from typing import Optional

API_BASE = "https://manager.museav.top/api"
APP_SLUG = "voxflow"
CONFIG_PATH = Path.home() / ".voxflow" / "museav.json"


class AuthError(RuntimeError):
    """授权流程里的可预期失败（码过期、用户没批准、网络不通）"""


def _post(path: str, payload: dict, headers: Optional[dict] = None) -> dict:
    body = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{API_BASE}{path}",
        data=body,
        headers={"Content-Type": "application/json", "User-Agent": f"voxflow/{APP_SLUG}", **(headers or {})},
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        detail = ""
        try:
            detail = json.loads(e.read().decode("utf-8")).get("error", "")
        except Exception:  # noqa: BLE001 - 也可能是 Cloudflare 的 HTML 错误页
            pass
        raise AuthError(detail or f"请求失败（HTTP {e.code}）") from e
    except urllib.error.URLError as e:
        raise AuthError(f"连不上 MUSE AV：{e.reason}") from e


def load_key() -> str:
    """本机存的应用 Key。没有就返回空串。"""
    if not CONFIG_PATH.is_file():
        return ""
    try:
        return str(json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("api_key") or "")
    except (OSError, json.JSONDecodeError):
        return ""


def load_account() -> str:
    if not CONFIG_PATH.is_file():
        return ""
    try:
        return str(json.loads(CONFIG_PATH.read_text(encoding="utf-8")).get("account_email") or "")
    except (OSError, json.JSONDecodeError):
        return ""


def _save(api_key: str, account_email: str, scopes: list[str]) -> None:
    CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(
        json.dumps({"api_key": api_key, "account_email": account_email, "scopes": scopes}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    # 凭据文件只给自己读：默认 644 会让同机其它用户拿到这把 Key
    os.chmod(CONFIG_PATH, 0o600)


def forget() -> None:
    """本机断开。**不等于**在 MUSE AV 那边撤销 —— 真撤销要去「账户 → 已授权应用」。"""
    CONFIG_PATH.unlink(missing_ok=True)


def login_start() -> dict:
    """只做设备码流程的第一步：拿码和验证地址，立刻返回。

    拆出来是为了让**界面**也能登录 —— 原来的 login() 会一直阻塞到用户批准，
    HTTP 端点不能那么干（浏览器会先超时）。界面拿到码之后自己轮询 login_poll()。
    命令行那条路仍然走 login()，行为不变。
    """
    d = _post("/app-auth/start", {"app_slug": APP_SLUG})
    return {"device_code": d["device_code"], "user_code": d["user_code"],
            "verification_uri": d["verification_uri"],
            "interval": int(d.get("interval") or 3),
            "expires_in": int(d.get("expires_in") or 600)}


def login_poll(device_code: str) -> dict:
    """查一次授权结果。{"status": "pending" | "approved" | "expired"}，不阻塞。"""
    d = _post("/app-auth/poll", {"device_code": device_code})
    status = d.get("status")
    if status == "approved":
        _save(d["api_key"], d.get("account_email") or "", d.get("scopes") or [])
        return {"status": "approved", "account_email": d.get("account_email") or "",
                "scopes": d.get("scopes") or []}
    return {"status": status or "pending"}


def login(open_browser: bool = True, on_code=None) -> dict:
    """走设备码流程拿这台机器的应用 Key。

    on_code(user_code, verification_uri) 会在拿到码之后、开始轮询之前调用一次，
    给调用方打印提示用。阻塞直到用户批准或超时。
    """
    start = _post("/app-auth/start", {"app_slug": APP_SLUG})
    device_code = start["device_code"]
    user_code = start["user_code"]
    uri = start["verification_uri"]
    interval = int(start.get("interval") or 3)
    expires_in = int(start.get("expires_in") or 600)

    if on_code:
        on_code(user_code, uri)
    if open_browser:
        try:
            webbrowser.open(uri)
        except Exception:  # noqa: BLE001 - 无头机器上打不开浏览器是正常的，码已经打出来了
            pass

    deadline = time.time() + expires_in
    while time.time() < deadline:
        time.sleep(interval)
        d = _post("/app-auth/poll", {"device_code": device_code})
        status = d.get("status")
        if status == "approved":
            _save(d["api_key"], d.get("account_email") or "", d.get("scopes") or [])
            return {"account_email": d.get("account_email") or "", "scopes": d.get("scopes") or []}
        if status == "expired":
            raise AuthError("授权码已过期，重新跑一次 `voice museav login`")
    raise AuthError("等待授权超时")


def whoami() -> dict:
    """用本机 Key 查账户与剩余积分。没连接就抛 AuthError。"""
    key = load_key()
    if not key:
        raise AuthError("还没连接 MUSE AV 账户，先跑 `voice museav login`")
    req = urllib.request.Request(f"{API_BASE}/me", headers={"X-API-Key": key, "User-Agent": f"voxflow/{APP_SLUG}"})
    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            d = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        # 401 = 用户已在 MUSE AV 撤销授权。留着一把废 Key 只会让后面每次调用都失败
        if e.code == 401:
            forget()
            raise AuthError("授权已被撤销，请重新跑 `voice museav login`") from e
        raise AuthError(f"查询失败（HTTP {e.code}）") from e
    except urllib.error.URLError as e:
        raise AuthError(f"连不上 MUSE AV：{e.reason}") from e
    return {"email": d.get("email") or "", "nickname": d.get("nickname") or "", "credits": int(d.get("credits") or 0)}
