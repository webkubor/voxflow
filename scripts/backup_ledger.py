#!/usr/bin/env python3
"""
把台账（voxflow.db + 关键 config）备份到 R2 私有桶。

    .venv/bin/python scripts/backup_ledger.py [--dry-run]

## 为什么私有桶

music 桶绑了公开 CDN（music.webkubor.online）—— 整桶公网可读。
台账里有真实姓名、平台账号元数据等个人数据，绝不能进公开桶。
这里用独立的 **voxflow-backup** 私有桶，不绑任何公开域名。

## 布局

    voxflow/<YYYY-MM-DD>/voxflow.db
    voxflow/<YYYY-MM-DD>/configs/*.json
    voxflow/latest/voxflow.db          # 总是最新，恢复时从这拿
    voxflow/latest/configs/*.json

每天一个快照，保留 14 天，更早的自动删（R2 不自动清，脚本负责）。

## 备份什么

- voxflow.db —— SQLite 台账真源，用 sqlite backup API 拷贝，后端在跑也一致
- configs/ 下现役的 json：personas / artist / publish_accounts / scripts /
  platform_accounts / generated/*
  *.migrated 和 configs.backup-* 是迁移遗留，不备份（见 docs/TODO.md 清理项）

## 凭证

CF_API_TOKEN 环境变量优先，否则 `cs kyvault get secret://cloudflare/api-token`。
上传走 Cloudflare API PUT（cs 内部同款通道），见 scripts/sync_r2.py。
"""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
import urllib.parse
import urllib.error
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.paths import DATA_DIR, CONFIG_DIR            # noqa: E402

BUCKET = "voxflow-backup"
ACCOUNT_ID = os.environ.get("CF_ACCOUNT_ID", "916ebb1b9f240bf4c8826021dd161692")
KEEP_DAYS = 14

DB_PATH = DATA_DIR / "voxflow.db"
LIVE_CONFIGS = ["personas.json", "artist.json", "publish_accounts.json",
                "scripts.json", "platform_accounts.json"]
# 2026-11-19：删掉了 GENERATED_DIR（CONFIG_DIR / "generated"）。
# 那是音色配方的第二份副本（只写不读）—— 真源是 configs/personas.json，
# 上面 LIVE_CONFIGS 已经备份它了。

# ── 两个仓的数据都要备 ──
#
# 2026-10-11 拆分后发行台账搬去了 suno-publisher（独立库 + 独立 configs）。
# 只备 voxflow 那份的话，**发行台账没有备份** —— 而它记的是上架记录、
# 平台账号、播放量、收益，丢了没法从别处重建（平台后台只给当前值，不给历史）。
#
# 布局沿用同一个 R2 桶，按仓分前缀：
#     voxflow/<日期>/…        suno-publisher/<日期>/…
VAULT_REPOS = [
    ("voxflow", DATA_DIR, CONFIG_DIR, LIVE_CONFIGS),
    ("suno-publisher",
     Path.home() / ".suno-publisher",
     Path.home() / ".suno-publisher" / "configs",
     ["artist.json", "platforms.json", "platform_accounts.json", "notify.json"]),
]


def _cs_binary() -> str:
    """找 cs 可执行文件。

    2026-11-19：原来写死 dev/gitlab/webkubor/CortexOS，而本机在 dev/cs/CortexOS ——
    定时任务一跑就 FileNotFoundError。按顺序探测，找不到就明说。
    """
    hit = shutil.which("cs")
    if hit:
        return hit
    candidates = [Path.home() / "dev" / "cs" / "CortexOS" / "bin" / "cs",
                  Path.home() / "dev" / "gitlab" / "webkubor" / "CortexOS" / "bin" / "cs"]
    root = os.environ.get("CORTEXOS_ROOT")
    if root:
        candidates.insert(0, Path(root) / "bin" / "cs")
    for cand in candidates:
        if cand.is_file():
            return str(cand)
    raise RuntimeError("找不到 cs：设置 CF_API_TOKEN 环境变量，或设 CORTEXOS_ROOT 指向 CortexOS 目录")


def api_token() -> str:
    env = os.environ.get("CF_API_TOKEN")
    if env:
        return env.strip()
    out = subprocess.run([_cs_binary(), "kyvault", "get", "secret://cloudflare/api-token"],
                         capture_output=True, text=True, check=True)
    return out.stdout.strip().splitlines()[-1].strip()


def api(method: str, path: str, token: str, data: bytes | None = None,
        content_type: str = "application/octet-stream") -> dict:
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/r2/{path}"
    req = urllib.request.Request(url, data=data, method=method, headers={
        "Authorization": "Bearer " + token,
        **({"Content-Type": content_type} if data is not None else {}),
    })
    with urllib.request.urlopen(req, timeout=120) as r:
        return json.loads(r.read().decode())


def ensure_bucket(token: str) -> None:
    """桶不存在就建一个。

    2026-11-19 实测：`voxflow-backup` 这个桶**从来不存在过** ——
    脚本只管往里 PUT，从不检查桶在不在；Cloudflare 对不存在的桶返回
    404，于是每一次备份都在第一步就失败，而失败信息淹没在输出里没人看。
    结果是「有备份脚本」但**从来没有一份备份存在**。

    台账记的是上架记录、平台账号、播放量、收益 —— 丢了没法从别处重建
    （平台后台只给当前值，不给历史）。这种「以为有、其实没有」比没有更危险，
    所以这里在建桶这一步失败时明确报出来，而不是让它带着 404 一路走下去。
    """
    url = f"https://api.cloudflare.com/client/v4/accounts/{ACCOUNT_ID}/r2/buckets"
    body = json.dumps({"name": BUCKET, "locationHint": "apac"}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + token,
        "Content-Type": "application/json",
    })
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            resp = json.loads(r.read().decode())
        if resp.get("success"):
            print(f"✓ 已创建备份桶 {BUCKET}")
    except urllib.error.HTTPError as e:
        # 已存在时 Cloudflare 返回 8xxx 的业务错误，不是 HTTP 错误
        detail = e.read().decode()[:200]
        if "already exists" in detail:
            return
        raise RuntimeError(f"创建备份桶 {BUCKET} 失败：HTTP {e.code} {detail}") from e


def put(token: str, key: str, data: bytes, content_type: str) -> None:
    resp = api("PUT", f"buckets/{BUCKET}/objects/{urllib.parse.quote(key, safe='/')}",
               token, data, content_type)
    if not resp.get("success"):
        raise RuntimeError(f"上传失败 {key}: {resp.get('errors')}")


def _snapshot_db(db_path: Path) -> bytes:
    """用 sqlite backup API 拷一份 —— **后端在跑也拿到一致快照**。

    直接读文件会在写入中途拿到半个事务，恢复出来是坏库。
    """
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    src = sqlite3.connect(str(db_path))
    dst = sqlite3.connect(str(tmp_path))
    try:
        src.backup(dst)
    finally:
        dst.close()
        src.close()
    data = tmp_path.read_bytes()
    tmp_path.unlink()
    return data


def main() -> None:
    dry = "--dry-run" in sys.argv
    token = "" if dry else api_token()
    today = datetime.now().strftime("%Y-%m-%d")

    # ── 1. 每个仓各自快照 + 收 configs ──
    plan: list[tuple[str, bytes, str, str]] = []     # (key 后缀, 内容, mime, 中文名)
    missing: list[str] = []
    for repo, data_dir, cfg_dir, live in VAULT_REPOS:
        db_path = data_dir / ("voxflow.db" if repo == "voxflow" else "suno-publisher.db")
        if not db_path.exists():
            # 不抛异常：一个仓还没建库不该让另一个仓的备份也失败
            missing.append(f"{repo}（{db_path}）")
            continue
        db_bytes = _snapshot_db(db_path)
        plan.append((f"{repo}.db", db_bytes, "application/octet-stream", repo))
        for name in live:
            f = cfg_dir / name
            if f.exists():
                plan.append((f"configs/{name}", f.read_bytes(), "application/json", repo))
        # 2026-11-19：删掉了 configs/generated/ 的备份。
        # 那是音色配方的第二份副本（只写不读），真源是 configs/personas.json
        # —— 上面 LIVE_CONFIGS 已经备份它了，备一份没人读的副本没有意义。
        print(f"  {repo:<16} {len(db_bytes)/1e6:>6.2f} MB + "
              f"{sum(1 for k, _, _, r in plan if r == repo) - 1} configs")

    if missing:
        print(f"⚠ 跳过（库不存在）：{'、'.join(missing)}")

    if not plan:
        print("✗ 没有任何可备份的东西")
        raise SystemExit(1)

    if dry:
        print("\n[dry-run] 不上传。将写：")
        for key, _, _, repo in plan:
            print(f"  {repo}/{today}/{key}")
            print(f"  {repo}/latest/{key}")
        return

    # ── 2. 上传：每个仓各自「快照 + latest」双写 ──
    ensure_bucket(token)          # 桶不存在就建 —— 见 ensure_bucket 的说明
    for repo, _, _, _ in VAULT_REPOS:
        for prefix in (f"{repo}/{today}/", f"{repo}/latest/"):
            for key, data, ct, r in plan:
                if r == repo:
                    put(token, f"{prefix}{key}", data, ct)
    n_repos = len({r for _, _, _, r in plan})
    print(f"✓ 已备份 {today} 快照 + latest（{n_repos} 个仓，共 {len(plan)} 个对象）")

    # ── 3. 清理过期快照（每个仓各自保留 KEEP_DAYS 天）──
    total_stale = 0
    cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    for repo, _, _, _ in VAULT_REPOS:
        resp = api("GET", f"buckets/{BUCKET}/objects?prefix={repo}/", token)
        objects = resp.get("result", [])   # 这个接口 result 直接是对象数组
        stale: list[str] = []
        base = len(repo) + 1               # "repo/" 之后才是日期
        for o in objects:
            key = o.get("key", "")
            # 只删 <repo>/YYYY-MM-DD/ 快照，latest/ 不按日期清。
            # 用 len(repo)+1 而不是写死 8：仓名长度不同，写死会把日期切错，
            # 字符串比较恒小于真日期 → 今天的快照被误删。
            if (key.startswith(f"{repo}/") and len(key) > base + 10
                    and key[base:base + 10].count("-") == 2):
                if key[base:base + 10] < cutoff:
                    stale.append(key)
        for key in stale:
            api("DELETE", f"buckets/{BUCKET}/objects/{urllib.parse.quote(key, safe='/')}", token)
        total_stale += len(stale)
        if stale:
            print(f"  {repo}：清理 {len(stale)} 个过期对象")
    print(f"✓ 共清理 {total_stale} 个过期对象（早于 {cutoff}）")


if __name__ == "__main__":
    main()
