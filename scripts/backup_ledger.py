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
import sqlite3
import subprocess
import sys
import tempfile
import urllib.request
import urllib.parse
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
GENERATED_DIR = CONFIG_DIR / "generated"

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


def api_token() -> str:
    env = os.environ.get("CF_API_TOKEN")
    if env:
        return env.strip()
    cs = os.environ.get("CORTEXOS_ROOT", str(Path.home() / "dev/gitlab/webkubor/CortexOS")) + "/bin/cs"
    out = subprocess.run([cs, "kyvault", "get", "secret://cloudflare/api-token"],
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
        gen = cfg_dir / "generated"
        if gen.is_dir():
            for f in sorted(gen.glob("*.json")):
                plan.append((f"configs/generated/{f.name}", f.read_bytes(),
                             "application/json", repo))
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
