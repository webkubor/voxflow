"""飞书通知 —— 音乐生成/发布的阶段性推送，按公司账户切换。

## 两条通道，按配置里有什么自动选

| 通道 | 需要什么 | 能干什么 | 什么时候用 |
|---|---|---|---|
| `lark-cli` | 已登录的 profile | 发群卡片 **+ 写飞书表格** | 首选 |
| `webhook`  | 一个 URL | 只能发消息 | 没装 lark-cli 时兜底 |

**webhook 写不了表格** —— 群机器人 webhook 是纯单向的消息入口，
表格读写必须走应用凭据（app_id/app_secret）。所以要同步表格就得用 lark-cli。

## 多公司：不写死，按 `active` 切

一台机器上同时有好几家公司的飞书（好易美 / ModelGo / larkpay…），
每家的机器人在各自的群里、各自的表格里。所以配置是
「一堆具名账户 + 一个 active 指针」，换公司只改 `active` 那一行，
或者调用时传 `account=` 临时指定 —— **任何地方都不写死某一家**。

profile 名沿用 lark-cli 自己的（`lark-cli profile list` 能看到），
voxflow 不复制一份账号体系，只记「这个账户用哪个 profile」。

## ⚠️ HTTP 200 不代表消息送达

webhook 通道最常见的坑：机器人被移出群、被停用、触发群安全设置、
关键词不匹配——飞书在这些情况下**照样返回 HTTP 200**，
真正的失败码藏在响应体的 `code` 里。只判断状态码会把这些当成成功，
然后没人收到、也没人知道没收到。所以 `_post()` 必须解析响应体。

## 通知永远不能把生成搞挂

推送是旁路：没配、网络不通、飞书挂了，都只记一条日志，
绝不让异常冒泡——不然「群通知坏了」会变成「歌生不出来」。
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import urllib.error
import urllib.request
from typing import Any

from core import obs
from core.paths import CONFIG_DIR

TIMEOUT_S = 10
CONFIG_FILE = CONFIG_DIR / "notify.json"

# 卡片主题色跟事件好坏走，扫一眼颜色就知道要不要点开
COLORS = {"start": "blue", "done": "green", "published": "green",
          "error": "red", "warn": "orange"}


def config() -> dict:
    """整份通知配置。文件不存在/坏了都返回空 dict —— 等于「没开通知」。"""
    if not CONFIG_FILE.exists():
        return {}
    try:
        return json.loads(CONFIG_FILE.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as e:
        obs.log("notify_config_bad", level="warn", error=str(e)[:120])
        return {}


def account(name: str = "") -> dict:
    """取一个公司账户的配置。

    优先级：显式传入 > 环境变量 `VOXFLOW_NOTIFY_ACCOUNT` > 配置里的 `active`。
    环境变量那一档是给「这次跑用另一家公司」准备的，不用改文件。
    """
    cfg = config()
    key = name or os.environ.get("VOXFLOW_NOTIFY_ACCOUNT") or cfg.get("active", "")
    acc = dict((cfg.get("accounts") or {}).get(key) or {})
    if acc:
        acc.setdefault("_key", key)
    return acc


def _post(webhook: str, payload: dict) -> tuple[bool, str]:
    """webhook 通道。返回 (是否真送达, 错误说明)。"""
    req = urllib.request.Request(
        webhook,
        data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
        headers={"Content-Type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_S) as resp:
            body = json.loads(resp.read().decode("utf-8") or "{}")
    except urllib.error.HTTPError as e:
        return False, f"HTTP {e.code}"
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as e:
        return False, str(e)[:120]
    # ↓ 关键：200 也可能是失败，看 code
    code = body.get("code", body.get("StatusCode", 0))
    if code:
        return False, f"code={code} {body.get('msg') or body.get('StatusMessage') or ''}"[:120]
    return True, ""


def _lark_cli(acc: dict, card: dict, dedupe_key: str = "") -> tuple[bool, str]:
    """lark-cli 通道：以机器人身份往群里发交互卡片。"""
    exe = shutil.which("lark-cli")
    if not exe:
        return False, "lark-cli 未安装"
    cmd = [exe, "--profile", acc["profile"], "im", "+messages-send",
           "--as", "bot", "--chat-id", acc["chat_id"],
           "--msg-type", "interactive",
           "--content", json.dumps(card["card"], ensure_ascii=False),
           "--format", "json"]
    if dedupe_key:
        # 同一个任务重试时不会在群里刷两条
        cmd += ["--idempotency-key", dedupe_key[:50]]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S * 3)
    except (subprocess.SubprocessError, OSError) as e:
        return False, str(e)[:120]
    try:
        out = json.loads(r.stdout or "{}")
    except json.JSONDecodeError:
        return r.returncode == 0, (r.stderr or "")[:120]
    if out.get("ok"):
        return True, ""
    return False, json.dumps(out.get("error", {}), ensure_ascii=False)[:160]


def _card(title: str, color: str, fields: dict[str, str],
          buttons: list[dict] | None = None) -> dict:
    """拼飞书交互卡片。

    `fields` 里空值的行直接丢掉 —— 生成阶段还没有平台/专辑，
    与其显示「平台：—」不如不显示，卡片才不会越推越长。
    """
    lines = [f"**{k}**：{v}" for k, v in fields.items() if str(v).strip()]
    elements: list[dict] = [{"tag": "div", "text": {
        "tag": "lark_md", "content": "\n".join(lines) or "—"}}]
    btns = [b for b in (buttons or []) if b.get("url")]
    if btns:
        elements.append({"tag": "action", "actions": [
            {"tag": "button", "text": {"tag": "plain_text", "content": b["text"]},
             "url": b["url"], "type": b.get("type", "default")} for b in btns]})
    return {
        "msg_type": "interactive",
        "card": {
            "config": {"wide_screen_mode": True},
            "header": {"template": color,
                       "title": {"tag": "plain_text", "content": title}},
            "elements": elements,
        },
    }


def notify(title: str, fields: dict[str, Any], *, level: str = "done",
           buttons: list[dict] | None = None, event: str = "",
           account_name: str = "", dedupe_key: str = "") -> bool:
    """推一条卡片。**任何情况下都不抛异常** —— 见模块头。

    通道选择：账户里配了 profile+chat_id 就走 lark-cli，否则走 webhook。
    两个都没有 = 没开通知，直接返回 False，不刷日志。
    """
    acc = account(account_name)
    if not acc:
        return False
    if event and event in set(acc.get("mute") or []):
        return False                       # 单独静音某类事件
    fields = {k: str(v) for k, v in fields.items()}
    card = _card(title, COLORS.get(level, "blue"), fields, buttons)
    try:
        if acc.get("profile") and acc.get("chat_id"):
            ok, err = _lark_cli(acc, card, dedupe_key)
        elif acc.get("webhook"):
            ok, err = _post(acc["webhook"], card)
        else:
            return False
    except Exception as e:                 # noqa: BLE001 —— 旁路，绝不影响主流程
        ok, err = False, str(e)[:120]
    if not ok:
        obs.log("notify_failed", level="warn", event=event or level,
                account=acc.get("_key", ""), error=err)
    return ok


# ─────────────────────────── 多维表格台账 ───────────────────────────
#
# 群消息是**看的**，台账是**用的** —— 一首歌发出去之后谁在跟、上架没有、
# 归在谁名下，这些只有表能回答，消息流一刷就沉底了。所以两边都写。
#
# ⚠️ 只有 lark-cli 通道能写表：webhook 是纯单向的消息入口，碰不到表格 API。

def _lark_json(acc: dict, method: str, path: str,
               body: dict | None = None) -> dict:
    exe = shutil.which("lark-cli")
    if not exe:
        return {"ok": False, "error": "lark-cli 未安装"}
    cmd = [exe, "--profile", acc["profile"], "api", method, path, "--as", "bot"]
    if body is not None:
        cmd += ["--data", json.dumps(body, ensure_ascii=False)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S * 3)
        return json.loads(r.stdout or "{}")
    except (subprocess.SubprocessError, OSError, json.JSONDecodeError) as e:
        return {"ok": False, "error": str(e)[:120]}


def ledger_add(fields: dict[str, Any], *, account_name: str = "") -> str:
    """往台账加一行，返回 record_id（失败返回空串，**不抛异常**）。

    `fields` 的键必须和表里的字段名一字不差 —— 飞书按名字匹配，
    对不上的键会被整条拒绝（不是忽略那一个键）。所以这里先拉一次
    字段表把不认识的键剔掉，宁可少写一栏也不要整行丢掉。
    """
    acc = account(account_name)
    base = acc.get("base") or {}
    if not (acc.get("profile") and base.get("app_token") and base.get("table_id")):
        return ""
    root = f"/open-apis/bitable/v1/apps/{base['app_token']}/tables/{base['table_id']}"
    known = {f["field_name"] for f in
             (_lark_json(acc, "GET", f"{root}/fields").get("data") or {}).get("items", [])}
    if known:
        dropped = set(fields) - known
        if dropped:
            obs.log("ledger_field_unknown", level="warn", fields=",".join(sorted(dropped)))
        fields = {k: v for k, v in fields.items() if k in known}
    r = _lark_json(acc, "POST", f"{root}/records", {"fields": fields})
    if not r.get("ok"):
        obs.log("ledger_add_failed", level="warn",
                error=json.dumps(r.get("error", {}), ensure_ascii=False)[:160])
        return ""
    return (r.get("data") or {}).get("record", {}).get("record_id", "")
