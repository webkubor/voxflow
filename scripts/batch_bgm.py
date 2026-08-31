#!/usr/bin/env python3
"""
batch_bgm.py — 一行命令批量生成 BGM

走 voxflow 后端的 /api/suno/batch 端点，不碰 suno CLI，不开浏览器。
用户看到的所有「自动化」都封装在 voxflow 项目内。

用法:
  ./scripts/batch_bgm.py "标题1:风格标签1" "标题2:风格标签2" ...
  ./scripts/batch_bgm.py \\
    "破晓:epic orchestral, cinematic, inspirational, building, 120 BPM" \\
    "长安月:chinese folk, guzheng, erhu, cinematic, traditional, 100 BPM" \\
    "心跳节拍:trap, transition hit, drop, cinematic, 110 BPM"

可选参数:
  --backend URL      voxflow 后端地址（默认 http://127.0.0.1:8866）
  --ai theme         让 LLM 自动生成 tags（覆盖手填的）
  --wait             等所有任务完成才退出
  --timeout 秒       单次等待超时（默认 600）

环境变量:
  VOXFLOW_BACKEND    等价 --backend
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from typing import Any

try:
    import requests
except ImportError:
    print("❌ 需要 requests 库: pip install requests", file=sys.stderr)
    sys.exit(2)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="批量生成 BGM（走 voxflow 后端 API）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument(
        "songs",
        nargs="*",
        help='「标题:风格标签」对，例如 "破晓:epic orchestral, 120 BPM"',
    )
    parser.add_argument(
        "--backend",
        default=os.environ.get("VOXFLOW_BACKEND", "http://127.0.0.1:8866"),
        help="voxflow 后端地址",
    )
    parser.add_argument(
        "--ai",
        metavar="THEME",
        help="用 LLM 根据主题自动生成风格标签（覆盖手填的 tags）",
    )
    parser.add_argument(
        "--wait",
        action="store_true",
        help="等所有任务完成才退出",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=600,
        help="等待超时秒数（默认 600）",
    )
    return parser.parse_args()


def ai_generate_tags(backend: str, theme: str) -> str:
    """
    让 voxflow 的 LLM 根据主题生成风格标签。
    调用 /api/llm/generate，用项目内已有的 AI 能力 —— 不用外部工具。
    """
    print(f"🤖 AI 生成 tags · 主题: {theme}")
    try:
        r = requests.post(
            f"{backend}/api/llm/generate",
            json={
                "prompt": (
                    f"为一个 BGM 风格写 5-7 个英文 Suno 风格标签。"
                    f"主题：{theme}。"
                    f"只输出标签本身，逗号分隔，不要解释。"
                    f"标签要包含 BPM（如 110 BPM）、乐器、流派、情绪。"
                ),
            },
            timeout=30,
        )
        if r.ok:
            text = (r.json() or {}).get("text", "").strip()
            if text:
                # 去掉可能的引号包裹
                text = text.strip('"').strip("'").strip("`")
                return text
        print(f"⚠️  AI 生成失败，使用默认标签: {r.status_code}", file=sys.stderr)
    except Exception as e:
        print(f"⚠️  AI 调用异常: {e}", file=sys.stderr)
    return "lo-fi, ambient, calm piano, 90 BPM"


def parse_song_spec(spec: str, ai_tags: str | None) -> dict[str, Any] | None:
    """「标题:标签」字符串 → dict。BGM 模式 lyrics 留空让后端自动加 instrumental。"""
    if ":" not in spec:
        return None
    title, raw_tags = spec.split(":", 1)
    title = title.strip()
    if not title:
        return None
    tags = (ai_tags or raw_tags).strip()
    return {"title": title, "tags": tags, "lyrics": ""}


def call_batch(backend: str, items: list[dict], wait: bool, timeout: int) -> dict:
    print(f"🚀 提交 {len(items)} 首到 {backend}/api/suno/batch")
    r = requests.post(
        f"{backend}/api/suno/batch",
        json={
            "items": items,
            "wait": wait,
            "timeout_sec": timeout,
            "poll_interval_sec": 5,
        },
        timeout=timeout + 30,
    )
    r.raise_for_status()
    return r.json()


def main() -> int:
    args = parse_args()

    if not args.songs:
        print("用法: ./scripts/batch_bgm.py \"标题1:标签1\" \"标题2:标签2\" ...")
        print("      ./scripts/batch_bgm.py --ai 治愈 \"标题1\" \"标题2\"  # AI 自动生成 tags")
        return 1

    # AI 生成 tags（覆盖所有）
    ai_tags = None
    if args.ai:
        ai_tags = ai_generate_tags(args.backend, args.ai)
        print(f"   AI tags: {ai_tags}")

    # 解析每个 spec
    items: list[dict] = []
    for spec in args.songs:
        item = parse_song_spec(spec, ai_tags)
        if not item:
            print(f"⚠️  跳过格式错误的 spec: {spec}", file=sys.stderr)
            continue
        items.append(item)
        print(f"   · {item['title']} · tags={item['tags'][:60]}{'...' if len(item['tags']) > 60 else ''}")

    if not items:
        print("❌ 没有有效的歌曲项", file=sys.stderr)
        return 1

    # 调后端
    backend = args.backend.rstrip("/")
    print()
    try:
        result = call_batch(backend, items, args.wait, args.timeout)
    except requests.exceptions.ConnectionError:
        print(f"❌ 连不上 voxflow 后端: {backend}", file=sys.stderr)
        print(f"   先跑 ./run.sh 启动后端", file=sys.stderr)
        return 2
    except requests.exceptions.HTTPError as e:
        print(f"❌ 后端返回错误: {e.response.status_code} {e.response.text[:200]}", file=sys.stderr)
        return 2

    # 输出结果
    print()
    print("═" * 56)
    if args.wait:
        print(f"🎉 批量完成（耗时 {result.get('elapsed_sec', '?')}s）")
        for r in result.get("results", []):
            files = r.get("files", [])
            file_str = files[0] if files else "（无文件）"
            icon = "✅" if r["status"] == "done" else ("❌" if r["status"] == "error" else "⏳")
            print(f"  {icon} {r['title']:20s} {r['status']:8s} {file_str}")
    else:
        print(f"📋 已提交 {len(result.get('task_ids', []))} 个任务")
        for entry in result.get("task_ids", []):
            print(f"  · {entry['title']:20s} → {entry['task_id']}")
        print()
        print("   任务面板: http://127.0.0.1:8866 (web UI)")
        print("   或加 --wait 等完成")
    print("═" * 56)
    return 0


if __name__ == "__main__":
    sys.exit(main())
