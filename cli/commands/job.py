import json
import os
from datetime import datetime, timedelta
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from core.paths import DATA_DIR as BASE_DIR  # 数据根，不是代码目录

console = Console()
app = typer.Typer(help="任务历史：查看、清理生成记录。")


def _load_all_histories():
    prod_dir = BASE_DIR / "assets" / "production"
    if not prod_dir.exists():
        return []
    histories = []
    for fp in prod_dir.glob("*_生成历史.json"):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            if isinstance(data, dict) and "records" in data:
                data["_file"] = fp.name
                histories.append(data)
        except Exception:
            pass
    return histories


def _flatten_records(histories):
    rows = []
    for hist in histories:
        persona = hist.get("persona", "未知")
        for rec in reversed(hist.get("records", [])):
            rows.append(
                {
                    "persona": persona,
                    "audio_file": rec.get("audio_file", ""),
                    "title": rec.get("title", ""),
                    "episode": rec.get("episode", ""),
                    "timestamp": rec.get("timestamp", ""),
                    "is_dialogue": rec.get("is_dialogue", False),
                    "text": rec.get("text", ""),
                }
            )
    return rows


@app.command("list")
def job_list(
    limit: int = typer.Option(20, "--limit", "-n", help="显示最近 N 条记录"),
    persona: str = typer.Option(None, "--persona", "-p", help="只显示特定角色的记录"),
):
    """列出最近生成记录（默认最近 20 条）"""
    histories = _load_all_histories()
    if not histories:
        console.print("[yellow]暂无生成记录。[/yellow]")
        return

    rows = _flatten_records(histories)
    if persona:
        rows = [r for r in rows if persona in r["persona"]]
    rows = rows[:limit]

    table = Table(title=f"[bold gold1]生成历史[/bold gold1]  共 {len(rows)} 条")
    table.add_column("时间", style="dim", width=16)
    table.add_column("角色", style="cyan")
    table.add_column("标题", style="white")
    table.add_column("文本预览", style="dim", max_width=30)
    table.add_column("文件", style="white", max_width=35)

    for r in rows:
        mode_tag = "对话" if r["is_dialogue"] else "克隆/设计"
        text = r["text"][:28] + "..." if len(r["text"]) > 28 else r["text"]
        table.add_row(
            r["timestamp"].split(" ")[-1] if " " in r["timestamp"] else r["timestamp"],
            r["persona"],
            f"[{mode_tag}] {r['title']}",
            text,
            r["audio_file"],
        )

    console.print(table)


@app.command("show")
def job_show(
    persona: str = typer.Argument(..., help="角色名称（模糊匹配）"),
    limit: int = typer.Option(10, "--limit", "-n", help="显示该角色最近 N 条记录"),
):
    """查看特定角色的生成记录详情"""
    histories = _load_all_histories()
    matched = [h for h in histories if persona in h.get("persona", "")]
    if not matched:
        console.print(f"[yellow]未找到角色：{persona}[/yellow]")
        raise typer.Exit(1)

    for hist in matched:
        hist = dict(hist)
        pname = hist.pop("persona")
        records = hist.pop("records", [])
        file_path = hist.pop("_file", "")

        console.print(f"\n[bold cyan]角色：[/bold cyan] {pname}")
        console.print(f"[bold cyan]历史文件：[/bold cyan] {file_path}\n")

        for i, rec in enumerate(reversed(records[:limit]), 1):
            mode = "[对话]" if rec.get("is_dialogue") else "[克隆]"
            console.print(
                f"  {i}. [{rec.get('timestamp', '')}] {mode} {rec.get('title', '未命名')}"
            )
            if rec.get("text"):
                console.print(f"     文本：{rec['text']}")
            console.print(f"     文件：{rec.get('audio_file', '')}\n")

    if len(matched) > 1:
        console.print(
            f"\n[dim]共匹配 {len(matched)} 个角色，请使用更精确的名称。[/dim]"
        )


@app.command("clean")
def job_clean(
    days: int = typer.Option(7, "--days", "-d", help="清理 N 天前的成品文件"),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="仅显示将被删除的文件，不实际删除"
    ),
    persona: str = typer.Option(None, "--persona", "-p", help="只清理特定角色的成品"),
):
    """清理 out/ 目录下超过指定天数的成品 WAV 文件"""
    out_dir = BASE_DIR / "out"
    if not out_dir.exists():
        console.print("[yellow]out/ 目录不存在。[/yellow]")
        return

    cutoff = datetime.now() - timedelta(days=days)
    removed = []
    kept = []

    for fp in out_dir.glob("*.wav"):
        mtime = datetime.fromtimestamp(fp.stat().st_mtime)
        if mtime < cutoff:
            removed.append(fp)
        else:
            kept.append(fp)

    if persona:
        removed = [f for f in removed if persona in f.name]
        kept = [f for f in kept if persona in f.name]

    console.print(
        f"[bold]扫描结果：[/bold] 共 {len(kept)} 个在期内，{len(removed)} 个将清理"
    )
    if not removed:
        console.print("[green]无需清理。[/green]")
        return

    for fp in removed:
        console.print(f"  [red]-[/red] {fp.name} ({fp.stat().st_size // 1024}KB)")

    if dry_run:
        console.print(f"\n[yellow]--dry-run 模式，仅显示不删除。[/yellow]")
        return

    confirm = typer.prompt(f"\n确认删除 {len(removed)} 个文件？输入 y 确认：")
    if confirm.lower() != "y":
        console.print("[yellow]已取消。[/yellow]")
        return

    for fp in removed:
        fp.unlink()
    console.print(f"[green]✓ 已删除 {len(removed)} 个文件。[/green]")


if __name__ == "__main__":
    app()
