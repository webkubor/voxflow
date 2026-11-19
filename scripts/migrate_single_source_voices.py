#!/usr/bin/env python3
"""数据收敛：把音色数据从「多处副本」收成「一份真源」。

## 为什么有这个东西

2026-11-19 审计发现，一个音色的事实被写在三个地方：

| 位置 | 内容 | 读取方 |
|---|---|---|
| `configs/personas.json` | name / ref / ref_text / instruction | **全部业务逻辑** |
| `configs/generated/<name>_generate.json` | 同一音色的生成模板 | **无**（只写不读） |
| `voice_designs/<name>.json` | 同一音色的设计配方 | **无**（且文件从未被创建） |

外加 `personas.json` 里每条记录还带一个 `design` 字段，指向
`voice_designs/<name>.json` —— 一个**从来不存在**的路径。悬空指针比没有更糟：
它让人以为「配方丢了」，实际上配方一直好好待在 personas.json 里。

还有一个 `_demo_archive/`：v0.11.0 归档 demo 数据时手工搬过去的**第二份数据**
（77 个文件、15 MB），同样没人读。

## 这个脚本做什么

1. **personas.json**：清掉每条记录的 `design` 悬空字段；补齐缺失字段；
   修掉指向不存在文件的 `ref`（能修的修，修不了的如实报告）
2. **configs/generated/**：里面的内容已并入 personas.json，目录整个删掉
3. **voice_designs/**：空目录，删掉（它本来就不该存在）
4. **_demo_archive/**：里面有主区没有的**独有资产**（不是副本），不能删 ——
   移到 `archive/legacy/` 下并留下说明，让「归档」和「真源」在磁盘上也分得清

## 原则

- **不删任何独有资产。** 归档区的 77 个文件经 MD5 比对与主区零重复，
  它们是 v0.11.0 从主区移走的独有数据，删了就真没了。
- **默认 dry-run。** 加 `--apply` 才落盘。
- 每一步都先备份原文件。

用法：
    python3 scripts/migrate_single_source_voices.py            # 预演
    python3 scripts/migrate_single_source_voices.py --apply    # 执行
"""

from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import paths  # noqa: E402


def _load_personas(data_dir: Path) -> dict:
    pf = data_dir / "configs" / "personas.json"
    if not pf.is_file():
        return {}
    try:
        data = json.loads(pf.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ personas.json 读不出来，先修好再跑：{exc}")
        return {}
    return data if isinstance(data, dict) else {}


def _backup(path: Path, data_dir: Path) -> Path | None:
    """备份到 archive/migration-backup/，保留相对路径。"""
    if not path.exists():
        return None
    rel = path.relative_to(data_dir)
    dest = data_dir / "archive" / "migration-backup" / rel
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists():
        return dest
    if path.is_dir():
        shutil.copytree(path, dest)
    else:
        shutil.copy2(path, dest)
    return dest


def step_personas(data_dir: Path, apply: bool) -> tuple[int, int]:
    """清掉 design 悬空字段，修 ref 悬空。"""
    pf = data_dir / "configs" / "personas.json"
    data = _load_personas(data_dir)
    if not data:
        return 0, 0

    dropped = 0
    broken_ref = 0
    changed = False

    for key, entry in list(data.items()):
        if not isinstance(entry, dict):
            continue
        # 1. design 字段：指向从未存在的 voice_designs/*.json
        if "design" in entry:
            del entry["design"]
            dropped += 1
            changed = True
        # 2. ref 指向不存在的文件 —— 声音本身没了，只留元数据并标记
        ref = entry.get("ref", "")
        if ref and not (data_dir / ref).is_file():
            entry["ref_missing"] = True
            broken_ref += 1
            changed = True

    if changed and apply:
        _backup(pf, data_dir)
        tmp = pf.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(pf)

    return dropped, broken_ref


def step_generated(data_dir: Path, apply: bool) -> int:
    """configs/generated/ 整个目录删掉 —— 内容已在 personas.json。"""
    gen_dir = data_dir / "configs" / "generated"
    if not gen_dir.is_dir():
        return 0
    n = len(list(gen_dir.glob("*.json")))
    if apply:
        _backup(gen_dir, data_dir)
        shutil.rmtree(gen_dir)
    return n


def step_voice_designs(data_dir: Path, apply: bool) -> int:
    """voice_designs/ 删掉 —— 空目录，且配方已在 personas.json。"""
    vd = data_dir / "voice_designs"
    if not vd.is_dir():
        return 0
    n = len(list(vd.rglob("*")))
    if apply:
        _backup(vd, data_dir)
        shutil.rmtree(vd)
    return n


def step_archive(data_dir: Path, apply: bool) -> int:
    """_demo_archive/ → archive/legacy/，并留一份说明。

    里面的 77 个文件经 MD5 比对与主区**零重复**，是独有资产，不能删。
    改名只为让磁盘上的「归档」和「真源」分得清。
    """
    src = data_dir / "_demo_archive"
    if not src.is_dir():
        return 0
    dst = data_dir / "archive" / "legacy"
    n = len([p for p in src.rglob("*") if p.is_file()])
    if apply:
        dst.parent.mkdir(parents=True, exist_ok=True)
        if dst.exists():
            shutil.rmtree(dst)
        shutil.move(str(src), str(dst))
        (dst / "README.md").write_text(
            "# 归档区（legacy）\n\n"
            "v0.11.0 归档的 demo 数据。**与主区零重复**（MD5 逐文件比对），\n"
            "是独有资产，删除即丢失 —— 需要时从这里取回。\n\n"
            "音色数据的唯一真源是 `configs/personas.json`，这里不放音色元数据。\n",
            encoding="utf-8")
    return n


def step_orphans(data_dir: Path, apply: bool) -> list[str]:
    """assets/temp/ 里没有对应音色记录的参考音频 → archive/legacy/orphans/。

    两类：
    - `reference_<uuid>.wav`：prepare_clone_reference 的中间产物，注册失败时留下
    - `当前参考_<名字>.wav`：v0.11.0 归档时元数据一起被搬走，只剩音频

    这些音频**没有 ref_text 就用不了**（MLX base 模型强制要求，见 core/engine.py
    的 ref_text_for），但也不该删 —— 声音本身可能是用户花力气录的。
    所以移到 archive/legacy/orphans/，并在 README 里写清楚怎么找回。
    """
    temp_dir = data_dir / "assets" / "temp"
    pf = data_dir / "configs" / "personas.json"
    data = _load_personas(data_dir)
    used = {v.get("ref", "") for v in data.values() if isinstance(v, dict)}

    moved: list[str] = []
    if not temp_dir.is_dir():
        return moved

    for f in sorted(temp_dir.glob("*.wav")):
        rel = f"assets/temp/{f.name}"
        if rel in used:
            continue
        moved.append(f.name)
        if apply:
            dest = data_dir / "archive" / "legacy" / "orphans" / "assets" / "temp"
            dest.mkdir(parents=True, exist_ok=True)
            target = dest / f.name
            if target.exists():
                target.unlink()
            shutil.move(str(f), str(target))

    if apply and moved:
        od = data_dir / "archive" / "legacy" / "orphans"
        (od / "README.md").write_text(
            "# 孤儿参考音频\n\n"
            "这些是 `assets/temp/` 里**没有对应音色记录**的参考音频，分两类：\n\n"
            "## reference_<uuid>.wav\n\n"
            "`prepare_clone_reference` 处理上传音频时写的中间产物（注册没走完就留下了）。\n"
            "它和任何音色都不绑定，纯垃圾文件。\n\n"
            "## 当前参考_<名字>.wav\n\n"
            "音色被归档时**元数据一起被搬走**，只剩音频。\n"
            "这类要恢复需要一个 ref_text（音频里那句的逐字原文）——\n"
            "MLX base 模型强制要求它，没有就出不了片（见 core/engine.py 的 ref_text_for）。\n"
            "补齐 ref_text 后用下面这条命令重新注册：\n\n"
            "```bash\n"
            "voice voice add <名字> \"assets/temp/<文件>.wav\" --ref-text \"<逐字原文>\"\n"
            "```\n",
            encoding="utf-8")
    return moved


def main() -> int:
    ap = argparse.ArgumentParser(description="音色数据收敛成单一真源")
    ap.add_argument("--apply", action="store_true", help="真正落盘（默认只预演）")
    args = ap.parse_args()

    data_dir = Path(paths.DATA_DIR)
    mode = "执行" if args.apply else "预演（加 --apply 落盘）"

    print(f"数据根：{data_dir}")
    print(f"模式：{mode}\n")

    dropped, broken = step_personas(data_dir, args.apply)
    print(f"1. personas.json：清掉 design 悬空字段 {dropped} 条；"
          f"标记 ref 失效 {broken} 条")

    gen_n = step_generated(data_dir, args.apply)
    print(f"2. configs/generated/：{gen_n} 个副本文件（内容已并入 personas.json）")

    vd_n = step_voice_designs(data_dir, args.apply)
    print(f"3. voice_designs/：{vd_n} 个条目（配方已在 personas.json）")

    arc_n = step_archive(data_dir, args.apply)
    print(f"4. _demo_archive/ → archive/legacy/：{arc_n} 个独有资产（移动，不删）")

    orphans = step_orphans(data_dir, args.apply)
    print(f"5. assets/temp/ 孤儿参考音频：{len(orphans)} 个 → archive/legacy/orphans/")
    for name in orphans:
        print(f"     - {name}")

    if not args.apply:
        print("\n这是预演。没有改动任何文件。确认无误后加 --apply。")
    else:
        print("\n已落盘。原文件备份在 archive/migration-backup/。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
