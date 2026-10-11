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
from pathlib import Path
import subprocess
import urllib.error
import urllib.request
from typing import Any

from core import net, obs
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
        # 走共享 opener：webhook 同样会被抓包代理挡住（实测
        # CERTIFICATE_VERIFY_FAILED），而 lark-cli 那条通道不受影响，
        # 因为它是独立二进制、有自己的信任库 —— 两条通道表现不一致过。
        cfg = config()
        with net.opener(cfg.get("ca_bundle", ""), bool(cfg.get("use_proxy"))).open(
                req, timeout=TIMEOUT_S) as resp:
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


def find_lark_cli() -> str:
    """定位 lark-cli。查找规则统一在 core/exe.py，那里写着为什么不能只靠 which。"""
    from core.exe import find_exe  # noqa: PLC0415

    return find_exe("lark-cli")


def _lark_cli(acc: dict, card: dict, dedupe_key: str = "") -> tuple[bool, str]:
    """lark-cli 通道：以机器人身份往群里发交互卡片。"""
    exe = find_lark_cli()
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
        # ⚠️ 字段名不能叫 `event` —— obs.log 的第一个位置参数就是 event，
        # 传 event= 会 TypeError。而这行在**失败路径**上，撞了就等于
        # 「通知失败」变成往调用方抛异常，正好破坏本模块「永不抛」的承诺。
        obs.log("notify_failed", level="warn", kind=event or level,
                account=acc.get("_key", ""), error=err)
    return ok


# ─────────────────────────── 多维表格台账 ───────────────────────────
#
# 群消息是**看的**，台账是**用的** —— 一首歌发出去之后谁在跟、上架没有、
# 归在谁名下，这些只有表能回答，消息流一刷就沉底了。所以两边都写。
#
# ⚠️ 只有 lark-cli 通道能写表：webhook 是纯单向的消息入口，碰不到表格 API。

def _lark_json(acc: dict, method: str, path: str,
               body: dict | None = None, params: dict | None = None) -> dict:
    """调 lark-cli 的原生 API 通道。

    ⚠️ `path` 里**不能带 query string** —— lark-cli 会直接拒绝
    （"path must not contain a query string"）。分页之类的参数走 `params`。
    踩过：分页写成 `?page_size=500` 后判重查询永远返回空，
    于是每同步一次就把整张表再插一遍。
    """
    exe = find_lark_cli()
    if not exe:
        return {"ok": False, "error": "lark-cli 未安装"}
    cmd = [exe, "--profile", acc["profile"], "api", method, path, "--as", "bot"]
    if body is not None:
        cmd += ["--data", json.dumps(body, ensure_ascii=False)]
    if params:
        cmd += ["--params", json.dumps(params, ensure_ascii=False)]
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=TIMEOUT_S * 3)
    except (subprocess.SubprocessError, OSError) as e:
        return {"ok": False, "error": str(e)[:120]}
    # ⚠️ lark-cli 出错时把 JSON 写到 **stderr**，stdout 是空的。
    # 只读 stdout 的话，每一个 API 错误都会变成 `{}` —— 调用方看到的是
    # 「失败了但没有原因」，而真正的原因（这次是 URLFieldConvFail）
    # 就躺在 stderr 里。为这个白查了两轮。
    for stream in (r.stdout, r.stderr):
        if stream and stream.strip():
            try:
                return json.loads(stream)
            except json.JSONDecodeError:
                continue
    return {"ok": False, "error": f"无输出 (rc={r.returncode})"}


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
    items = (_lark_json(acc, "GET", f"{root}/fields").get("data") or {}).get("items", [])
    known = {f["field_name"] for f in items}
    if known:
        dropped = set(fields) - known
        if dropped:
            obs.log("ledger_field_unknown", level="warn", fields=",".join(sorted(dropped)))
        fields = {k: v for k, v in fields.items() if k in known}
        # URL 字段（type 15）**只收对象**，传字符串整批被拒（1254068
        # URLFieldConvFail）。ledger_sync 里早就处理了，ledger_add 一直没有 ——
        # 于是单条写入只要带 URL 就必失败，而失败只记在日志里，界面上毫无迹象。
        url_fields = {f["field_name"] for f in items if f.get("type") == 15}
        for k in list(fields):
            if k in url_fields and isinstance(fields[k], str):
                fields[k] = {"link": fields[k], "text": fields[k]} if fields[k] else None
        fields = {k: v for k, v in fields.items() if v is not None}
    r = _lark_json(acc, "POST", f"{root}/records", {"fields": fields})
    if not r.get("ok"):
        obs.log("ledger_add_failed", level="warn",
                error=json.dumps(r.get("error", {}), ensure_ascii=False)[:160])
        return ""
    return (r.get("data") or {}).get("record", {}).get("record_id", "")


# ─────────────────────── 从本地库回填台账 ───────────────────────
#
# 台账要能回答一个问题：**哪些歌发过、哪些没发过。**
# 独家授权的前提下这尤其要紧 —— 一首歌只能发一个平台，重复投是违约。
#
# 真源是本地的 voxflow.db（tracks + track_platforms），飞书表是它的
# **对外视图**：别人不给他开数据库，但要能认领发行。所以是单向同步，
# 数据库 → 飞书，不反向。人在飞书上填的东西（负责账号、发行歌名）
# 不会被这个函数覆盖。

# 本地状态 → 台账状态。本地只记 online/reviewing，台账的粒度更细，
# 所以是「多对一的反向」：本地没有的中间态由人在表里推进。






def _date_ms(s: str) -> int:
    """'2026-03-29' → 毫秒时间戳。解析不了就返回 0（飞书会忽略）。"""
    from datetime import datetime
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y-%m-%dT%H:%M:%S"):
        try:
            return int(datetime.strptime(s[:len(fmt) + 2], fmt).timestamp() * 1000)
        except ValueError:
            continue
    return 0


def release(version: str, title: str, changes: list[str], *,
            highlight: str = "", link: str = "") -> bool:
    """推一条版本更新日志。

    和音乐通知**分在不同的群**：那边是作品流水（每天几条、只有做歌的人关心），
    这边是产品变更（几天一条、所有用这个工具的人都要看到）。
    混在一起的结果是两边都被对方刷掉。

    `changes` 一条一行，写**用户能感知的变化**，不写内部重构 ——
    「修了 XX 的空指针」对看的人没有任何意义，「点了没反应的播放按钮好了」才有。
    """
    fields = {"版本": version}
    if highlight:
        fields["重点"] = highlight
    fields["更新内容"] = "\n" + "\n".join(f"· {c}" for c in changes)
    btns = [{"text": "查看详情", "url": link, "type": "primary"}] if link else None
    ok = notify(f"🚀 {title}", fields, level="start", event="release",
                account_name="changelog", dedupe_key=f"vf-release-{version}", buttons=btns)
    if ok:
        return True
    # changelog 那个群走的是 webhook，而 webhook 会因为「机器人被停用 / 被移出群 /
    # 触发群安全设置」静默失效（实测 code 19007 Bot Not Enabled）。
    # 版本更新是两类通知之一，不该因为一个群的机器人被停就整条没了 ——
    # 回退到默认账号的 lark-cli 通道，那条路是以机器人身份发的，不受群 webhook 开关影响。
    return notify(f"🚀 {title}", fields, level="start", event="release",
                  dedupe_key=f"vf-release-{version}-fb", buttons=btns)




def _cfg_base() -> dict:
    return (account() or {}).get("base") or {}


def assign_owner(pair_index: int, *, seed: str = "", account_name: str = "") -> dict:
    """一次生成出的第 N 首该归谁发。

    规则：**第一首归 owner 自己，第二首随机分给 others 里的一个人。**

    为什么第二首要分出去：Suno 一次出两首、旋律不同，是两个独立作品，
    各自要走一遍上架（填表、传封面、等审核）。全压在一个人身上，
    多出来的那首多半就烂在库里了 —— 生成成本已经花掉，不发等于白花。

    `seed` 传 clip id：同一首歌**每次算出来的人必须一样**。
    用真随机的话，重跑一次同步就换个人，@ 来 @ 去没人知道到底归谁。
    """
    import hashlib
    import random

    cfg = (account(account_name) or {}).get("assignees") or {}
    owner = cfg.get("owner") or {}
    others = [x for x in (cfg.get("others") or []) if x.get("open_id")]
    if pair_index <= 0 or not others:
        return owner
    # 用 clip id 做种子 → 同一首歌永远分给同一个人
    rnd = random.Random(hashlib.sha256((seed or str(pair_index)).encode()).hexdigest())
    return others[rnd.randrange(len(others))]
