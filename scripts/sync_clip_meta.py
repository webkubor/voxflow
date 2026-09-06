#!/usr/bin/env python3
"""
回填台账的 Clip ID 与时长。

    .venv/bin/python scripts/sync_clip_meta.py [--dry-run]

## 为什么非要有 Clip ID 这一列

**歌会重名，而且是必然重名**：Suno 一次生成出两首，标题一模一样
（都叫「破晓」），只有旋律不同。发行时各改各的名，但曲库里、日志里、
Suno 后台里，它们仍然同名。

所以「哪一首」这个问题，靠名字永远答不了。唯一能锚定的是 clip id ——
它在 Suno、在台账、在生成日志里是同一个值，出问题时顺着它能一路查到底。

时长是给人用的：两首同名歌，一首 2:33 一首 3:07，扫一眼就分得清，
不用去比对 36 位的 uuid。

## 只补不覆盖

已经填了的不动 —— 人手工改过的时长（比如剪辑后的）比云端的准。
"""
import json
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import notify  # noqa: E402

DRY = "--dry-run" in sys.argv
SUNO = str(Path.home() / ".cargo/bin/suno")
UUID = re.compile(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}")


def txt(v):
    if isinstance(v, list) and v and isinstance(v[0], dict):
        return v[0].get("text", "")
    if isinstance(v, dict):
        return v.get("link") or v.get("text", "")
    return v or ""


def main() -> int:
    acc = notify.account()
    base = acc.get("base") or {}
    if not base.get("app_token"):
        print("❌ 当前账户没配多维表格")
        return 1
    root = f"/open-apis/bitable/v1/apps/{base['app_token']}/tables/{base['table_id']}"

    have = {f["field_name"] for f in
            (notify._lark_json(acc, "GET", f"{root}/fields").get("data") or {}).get("items", [])}
    if "Clip ID" not in have and not DRY:
        r = notify._lark_json(acc, "POST", f"{root}/fields",
                              {"field_name": "Clip ID", "type": 1})
        print("新增字段 Clip ID:", "✓" if r.get("ok") else str(r.get("error"))[:120])

    out = subprocess.run([SUNO, "list", "--json"], capture_output=True, text=True, timeout=90).stdout
    clips = {c["id"]: c for c in json.loads(out or "{}").get("data", {}).get("clips", [])}
    print(f"Suno 上 {len(clips)} 首")

    recs = (notify._lark_json(acc, "GET", f"{root}/records",
                              params={"page_size": 500}).get("data") or {}).get("items", [])
    ups = []
    for r in recs:
        f = r["fields"]
        # clip id 可能在备注里，也可能在源文件链接里 —— 两处都找
        blob = txt(f.get("备注")) + " " + txt(f.get("源文件链接"))
        m = UUID.search(blob)
        if not m:
            continue
        cid = m.group(0)
        fields = {}
        if not txt(f.get("Clip ID")):
            fields["Clip ID"] = cid
        if not f.get("时长秒"):
            dur = ((clips.get(cid) or {}).get("metadata") or {}).get("duration")
            if dur:
                fields["时长秒"] = round(float(dur))
        if fields:
            ups.append({"record_id": r["record_id"], "fields": fields})
            mm, ss = divmod(int(fields.get("时长秒") or 0), 60)
            print(f"  {txt(f.get('发行歌名')) or txt(f.get('曲名')):12} "
                  f"{cid[:8]}  {f'{mm}:{ss:02d}' if fields.get('时长秒') else '(无时长)'}")

    if not ups:
        print("没有需要补的")
        return 0
    if DRY:
        print(f"\n（预演）待更新 {len(ups)} 行")
        return 0
    for i in range(0, len(ups), 200):
        res = notify._lark_json(acc, "POST", f"{root}/records/batch_update",
                                {"records": ups[i:i + 200]})
        print("更新:", "✓" if res.get("ok") else str(res.get("error"))[:160])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
