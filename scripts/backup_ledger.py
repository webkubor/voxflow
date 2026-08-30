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
import time
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


def main() -> None:
    dry = "--dry-run" in sys.argv
    token = "" if dry else api_token()
    today = datetime.now().strftime("%Y-%m-%d")
    snap_prefix = f"voxflow/{today}/"
    latest_prefix = "voxflow/latest/"

    if not DB_PATH.exists():
        print(f"✗ 台账库不存在：{DB_PATH}")
        raise SystemExit(1)

    # ── 1. voxflow.db（sqlite backup API，后端在跑也拿到一致快照）──
    with tempfile.NamedTemporaryFile(suffix=".db", delete=False) as tmp:
        tmp_path = Path(tmp.name)
    src = sqlite3.connect(str(DB_PATH))
    dst = sqlite3.connect(str(tmp_path))
    try:
        src.backup(dst)
    finally:
        dst.close(); src.close()
    db_bytes = tmp_path.read_bytes()
    tmp_path.unlink()

    # ── 2. configs ──
    configs: list[tuple[str, bytes, str]] = []
    for name in LIVE_CONFIGS:
        p = CONFIG_DIR / name
        if p.exists():
            configs.append((f"configs/{name}", p.read_bytes(), "application/json"))
    if GENERATED_DIR.is_dir():
        for p in sorted(GENERATED_DIR.glob("*.json")):
            configs.append((f"configs/generated/{p.name}", p.read_bytes(), "application/json"))

    print(f"台账库 {len(db_bytes)/1e6:.1f} MB · configs {len(configs)} 个")
    if dry:
        print("[dry-run] 不上传。将写：")
        print(f"  {snap_prefix}voxflow.db")
        for key, _, _ in configs:
            print(f"  {snap_prefix}{key}")
        print(f"  {latest_prefix}...（latest 覆盖）")
        return

    # ── 3. 上传：快照 + latest 双写 ──
    for prefix in (snap_prefix, latest_prefix):
        put(token, f"{prefix}voxflow.db", db_bytes, "application/octet-stream")
        for key, data, ct in configs:
            put(token, f"{prefix}{key}", data, ct)
    print(f"✓ 已备份 {today} 快照 + latest（{len(db_bytes)/1e6:.1f} MB + {len(configs)} configs）")

    # ── 4. 清理过期快照（保留 KEEP_DAYS 天）──
    resp = api("GET", f"buckets/{BUCKET}/objects?prefix=voxflow/", token)
    objects = resp.get("result", [])   # 这个接口 result 直接是对象数组
    cutoff = (datetime.now() - timedelta(days=KEEP_DAYS)).strftime("%Y-%m-%d")
    stale: list[str] = []
    for o in objects:
        key = o.get("key", "")
        # 只删 voxflow/YYYY-MM-DD/ 快照，latest/ 不按日期清。
        # 前缀 "voxflow/" 是 8 个字符，日期从 index 8 开始 —— 从 7 开始会
        # 把 "/2026-08-3" 当日期，字符串比较恒小于真日期，今天的快照全被误删。
        if key.startswith("voxflow/") and len(key) > 18 and key[8:18].count("-") == 2:
            date_part = key[8:18]
            if date_part < cutoff:
                stale.append(key)
    for key in stale:
        api("DELETE", f"buckets/{BUCKET}/objects/{urllib.parse.quote(key, safe='/')}", token)
    print(f"✓ 清理 {len(stale)} 个过期对象（早于 {cutoff}）")


if __name__ == "__main__":
    main()
