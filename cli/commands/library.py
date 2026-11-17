"""生成库命令：列出生成的音频、把设计样音收藏进音色库、删除未受保护的文件。

与 Web「生成库」同一套规则（core/voice_library.py）：
关联音色已收藏的文件不能删；收藏不重新生成，也不改动原文件。
"""
from typing import Optional

import typer
from rich.table import Table

from core import voice_library as vlib
from cli.output import JSON_OPTION, confirm_or_fail, console, emit, fail_from

app = typer.Typer(help="生成库：list / save（收藏设计样音）/ rm（仅未受保护的文件）。")

KINDS = ("design", "clone", "dialogue", "preview", "other")


@app.command("list")
def library_list(
    kind: Optional[str] = typer.Option(None, "--kind", "-k", help=f"只看某类：{' / '.join(KINDS)}"),
    unsaved: bool = typer.Option(False, "--unsaved", help="只看还没收藏进音色库的"),
    limit: int = typer.Option(0, "--limit", "-n", help="最多返回几条（0 = 全部）"),
    as_json: bool = JSON_OPTION,
):
    """列出生成库（新的在前）"""
    try:
        files = vlib.list_generated(kinds=[kind] if kind else None)
    except vlib.VoiceLibraryError as exc:
        fail_from(exc, as_json)
    if unsaved:
        files = [f for f in files if not f["voice"]]
    if limit > 0:
        files = files[:limit]

    def human():
        table = Table(title=f"[bold gold1]生成库[/bold gold1]  共 {len(files)} 条")
        table.add_column("文件", style="cyan")
        table.add_column("类型", justify="center")
        table.add_column("时间", style="dim")
        table.add_column("音色库")
        for f in files:
            v = f["voice"]
            state = f"{'★ 已收藏' if v['favorite'] else '☆ 未收藏'} · {v['name']}" if v else "—"
            table.add_row(f["filename"], f["kind"], f["created"], state)
        console.print(table)

    emit({"files": files, "total": len(files)}, as_json, human)


@app.command("save")
def library_save(
    filename: str = typer.Argument(..., help="生成库里的设计文件名（[设计]….wav）"),
    voice_name: str = typer.Argument(..., help="收藏后的音色名称"),
    ref_text: str = typer.Option("", "--ref-text", help="样音实际念的原文；有记录时可省略（历史文件必填）"),
    instruction: str = typer.Option("", "--instruction", "-i", help="音色描述"),
    as_json: bool = JSON_OPTION,
):
    """把已生成的设计样音收藏进音色库（不重新生成）"""
    try:
        saved = vlib.save_design(filename, voice_name, instruction, ref_text)
    except vlib.VoiceLibraryError as exc:
        fail_from(exc, as_json)
    emit({"voice": saved}, as_json, lambda: console.print(
        f"[green]✓[/green] 已收藏到音色库：{saved['name']}（key: {saved['persona_key']}）"))


@app.command("rm")
def library_rm(
    filename: str = typer.Argument(..., help="要删除的生成文件名"),
    yes: bool = typer.Option(False, "--yes", "-y", help="跳过确认"),
    as_json: bool = JSON_OPTION,
):
    """删除生成文件（--yes 即确认影响；关联音色已收藏时也一样）"""
    confirm_or_fail(f"删除生成文件 {filename}？", yes, as_json)
    try:
        removed = vlib.delete_generated(filename, confirm=True)
    except vlib.VoiceLibraryError as exc:
        fail_from(exc, as_json)
    emit({"removed": removed}, as_json, lambda: console.print(f"[green]✓[/green] 已删除：{removed['filename']}"))
