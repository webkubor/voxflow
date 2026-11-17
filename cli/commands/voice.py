"""音色库命令 —— 规则全部来自 core/voice_library.py，与 Web 端同一份。

收藏的音色不能删（先 unfavorite）；删除只去掉映射，参考音频保留。
每个命令都支持 --json，退出码约定见 cli/output.py。
"""
import json
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.panel import Panel
from rich.table import Table

from core import voice_library as vlib
from core.paths import DATA_DIR as BASE_DIR  # 数据根，不是代码目录
from cli.output import (JSON_OPTION, confirm_or_fail, console, emit, fail, fail_from,
                        progress_console)

app = typer.Typer(help="音色库：录制 / 注册、收藏、重命名、删除（仅未收藏）、试听。")

ALLOWED_AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac", ".webm", ".mp4")


def _resolve_audio(path: str, as_json: bool) -> Path:
    p = Path(path).expanduser()
    if not p.is_absolute():
        p = (Path.cwd() / p) if (Path.cwd() / p).exists() else BASE_DIR / path
    if not p.is_file():
        fail(f"音频文件不存在：{p}", as_json, 404)
    if p.suffix.lower() not in ALLOWED_AUDIO_EXTS:
        fail(f"不支持的格式：{p.suffix}，仅支持 {', '.join(ALLOWED_AUDIO_EXTS)}", as_json)
    return p


def _get(key: str, as_json: bool) -> dict:
    try:
        personas = vlib.load_personas()
    except vlib.VoiceLibraryError as exc:
        fail_from(exc, as_json)
    if key not in personas:
        fail(f"音色不存在：{key}", as_json, 404)
    return vlib.describe_voice(key, personas[key])


@app.command("list")
def voice_list(
    favorites: bool = typer.Option(False, "--favorites", "-F", help="只列收藏音色（音色库）"),
    as_json: bool = JSON_OPTION,
):
    """列出音色（默认全部，含收藏状态）"""
    try:
        voices = vlib.list_voices(favorites_only=favorites)
    except vlib.VoiceLibraryError as exc:
        fail_from(exc, as_json)

    def human():
        if not voices:
            console.print("[yellow]音色库为空：用 voice voice record 或 voice voice add 注册。[/yellow]")
            return
        table = Table(title="[bold gold1]收藏音色库[/bold gold1]" if favorites else "[bold gold1]音色[/bold gold1]")
        table.add_column("Key", style="cyan", no_wrap=True)
        table.add_column("名称")
        table.add_column("收藏", justify="center")
        table.add_column("样音", justify="center")
        table.add_column("来源", style="dim")
        for v in voices:
            table.add_row(v["key"], v["name"], "★" if v["favorite"] else "☆",
                          "✓" if v["has_audio"] else "[red]✗[/red]", v["source_filename"] or "")
        console.print(table)
        console.print(f"[dim]共 {len(voices)} 个；未收藏的才能删除[/dim]")

    emit({"voices": voices, "total": len(voices)}, as_json, human)


@app.command("show")
def voice_show(key: str = typer.Argument(..., help="音色 key"), as_json: bool = JSON_OPTION):
    """查看音色详情"""
    v = _get(key, as_json)

    def human():
        lines = [f"[bold cyan]{k}:[/bold cyan] {v[k]}" for k in
                 ("key", "name", "favorite", "ref", "has_audio", "ref_text", "instruction", "source_filename") if v[k] != ""]
        console.print(Panel("\n".join(lines), title=f"[gold1]音色 — {v['name']}[/gold1]", expand=False))

    emit({"voice": v}, as_json, human)


def _register(key, audio_path, ref_text, name, instruction, as_json, extra=None):
    try:
        out = vlib.register_voice(key, audio_path, ref_text, name=name, instruction=instruction or "",
                                  data_dir=BASE_DIR)
    except vlib.VoiceLibraryError as exc:
        fail_from(exc, as_json)
    out = {**out, "favorite": True, **(extra or {})}
    emit({"voice": out}, as_json, lambda: console.print(
        f"[green]✓[/green] 音色 [bold]{out['name']}[/bold]（{out['key']}）已注册并收藏\n  样音 → {out['ref']}"))


@app.command("add")
def voice_add(
    key: str = typer.Argument(..., help="音色唯一标识（英文/拼音，如 my_voice）"),
    audio: str = typer.Argument(..., help="参考音频路径（0.5–30 秒，建议 10–30 秒安静环境）"),
    ref_text: str = typer.Option(..., "--ref-text", help="参考音频中逐字对应的原文"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="显示名，默认等于 key"),
    instruction: Optional[str] = typer.Option(None, "--instruction", "-i", help="音色基础指令/描述"),
    as_json: bool = JSON_OPTION,
):
    """用已有音频注册音色（克隆自己的声音）。重名直接失败，不覆盖。"""
    _register(key, _resolve_audio(audio, as_json), ref_text, name, instruction, as_json)


@app.command("record")
def voice_record(
    key: str = typer.Argument(..., help="音色唯一标识"),
    ref_text: str = typer.Option(..., "--ref-text", help="你将要朗读的原文（录音须逐字念出）"),
    seconds: int = typer.Option(15, "--seconds", "-s", min=3, max=30, help="录音时长（3–30 秒）"),
    name: Optional[str] = typer.Option(None, "--name", "-n", help="显示名，默认等于 key"),
    device: str = typer.Option(":0", "--device", help="ffmpeg avfoundation 音频设备，默认 :0"),
    as_json: bool = JSON_OPTION,
):
    """用麦克风录一段自己的声音并注册（需要终端的麦克风权限）。

    原始录音保存在 assets/reference_audio/，不会删除。
    """
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        fail("未找到 ffmpeg，无法录音；可先用其他工具录好再 voice voice add", as_json)
    raw_dir = BASE_DIR / "assets" / "reference_audio"
    raw_dir.mkdir(parents=True, exist_ok=True)
    raw = raw_dir / f"录音_{key}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    out = progress_console(as_json)
    out.print(f"[gold1]请朗读：[/gold1]{ref_text}")
    out.print(f"[cyan]● 录音 {seconds} 秒…[/cyan]")
    r = subprocess.run([ffmpeg, "-hide_banner", "-loglevel", "error", "-f", "avfoundation",
                        "-i", device, "-t", str(seconds), "-ac", "1", "-ar", "24000", str(raw)],
                       capture_output=True, text=True)
    if r.returncode != 0 or not raw.is_file():
        fail(f"录音失败（检查终端的麦克风权限与 --device）：{r.stderr.strip()[-300:]}", as_json)
    _register(key, raw, ref_text, name, None, as_json, {"recording": str(raw)})


@app.command("rename")
def voice_rename(key: str = typer.Argument(...), new_name: str = typer.Argument(..., help="新的显示名"),
                 as_json: bool = JSON_OPTION):
    """重命名（只改显示名，不动音频和 key）"""
    try:
        v = vlib.update_voice(key, name=new_name)
    except vlib.VoiceLibraryError as exc:
        fail_from(exc, as_json)
    emit({"voice": v}, as_json, lambda: console.print(f"[green]✓[/green] {key} → {v['name']}"))


def _set_favorite(key: str, value: bool, as_json: bool):
    try:
        v = vlib.update_voice(key, favorite=value)
    except vlib.VoiceLibraryError as exc:
        fail_from(exc, as_json)
    emit({"voice": v}, as_json, lambda: console.print(
        f"[green]✓[/green] {v['name']} {'已收藏' if value else '已取消收藏（现在可以删除）'}"))


@app.command("favorite")
def voice_favorite(key: str = typer.Argument(...), as_json: bool = JSON_OPTION):
    """收藏音色（收藏后受保护，不可删除）"""
    _set_favorite(key, True, as_json)


@app.command("unfavorite")
def voice_unfavorite(key: str = typer.Argument(...), as_json: bool = JSON_OPTION):
    """取消收藏（之后才能删除）"""
    _set_favorite(key, False, as_json)


@app.command("rm")
def voice_rm(
    key: str = typer.Argument(..., help="要删除的音色 key（必须未收藏）"),
    yes: bool = typer.Option(False, "--yes", "-y", "--force", "-f", help="跳过确认"),
    as_json: bool = JSON_OPTION,
):
    """删除未收藏的音色（只移除映射，参考音频保留）"""
    v = _get(key, as_json)
    if v["favorite"]:
        fail("已收藏的音色不能删除，请先 voice voice unfavorite", as_json, 409)
    confirm_or_fail(f"删除音色 {v['name']}（{key}）？", yes, as_json)
    try:
        removed = vlib.delete_voice(key)
    except vlib.VoiceLibraryError as exc:
        fail_from(exc, as_json)
    emit({"removed": removed}, as_json, lambda: console.print(
        f"[green]✓[/green] 已删除：{key}（参考音频保留在 {removed['ref'] or '—'}）"))


@app.command("import")
def voice_import(
    path: str = typer.Argument(..., help="要导入的 personas.json 路径"),
    overwrite: bool = typer.Option(False, "--overwrite", help="覆盖同名的未收藏音色（收藏音色永不覆盖）"),
    as_json: bool = JSON_OPTION,
):
    """批量导入音色（合并；默认跳过已存在的）"""
    p = Path(path).expanduser()
    if not p.is_file():
        fail(f"文件不存在：{p}", as_json, 404)
    try:
        result = vlib.import_voices(json.loads(p.read_text(encoding="utf-8")), overwrite=overwrite)
    except json.JSONDecodeError as exc:
        fail(f"不是合法 JSON：{exc}", as_json)
    except vlib.VoiceLibraryError as exc:
        fail_from(exc, as_json)
    emit(result, as_json, lambda: console.print(
        f"[green]✓[/green] 新增 {len(result['added'])}，覆盖 {len(result['updated'])}，"
        f"跳过 {len(result['skipped'])}（共 {result['total']} 个）"))


@app.command("preview")
def voice_preview(
    key: str = typer.Argument(..., help="音色 key"),
    text: str = typer.Option("这是一段简短的测试语音，用来验证音色效果。", "--text", "-t", help="试听文本"),
    no_play: bool = typer.Option(False, "--no-play", help="只生成不播放"),
    as_json: bool = JSON_OPTION,
):
    """用短句试听音色（本地模型生成到 out/，默认自动播放）"""
    v = _get(key, as_json)
    if not v["has_audio"]:
        fail(f"音色 {key} 的参考音频缺失：{v['ref'] or '无 ref'}", as_json, 404)
    out_dir = BASE_DIR / "out"
    out_dir.mkdir(exist_ok=True)
    out_path = out_dir / f"[试听]{vlib.safe_voice_name(v['name'])}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.wav"
    progress_console(as_json).print("[cyan]⏳ 正在生成试听音频...[/cyan]")
    try:
        import soundfile as sf
        from core.engine import TTSBaseEngine

        engine = TTSBaseEngine("Base", "1.7B")
        results = list(engine.wrapped_model.generate(
            text=text, ref_audio=str(BASE_DIR / v["ref"]), ref_text=engine.ref_text_for(key),
            lang_code="chinese", temperature=0.7, top_p=0.9, top_k=50,
        ))
        sf.write(str(out_path), results[0].audio, engine.sample_rate)
    except Exception as e:  # noqa: BLE001 — 模型错误原样报告
        fail(f"生成失败：{e}", as_json)

    if not (no_play or as_json):
        from core.paths import IS_MACOS, IS_WINDOWS  # noqa: PLC0415
        cmd = (["afplay", str(out_path)] if IS_MACOS else
               ["cmd", "/c", "start", "", str(out_path)] if IS_WINDOWS else ["xdg-open", str(out_path)])
        try:
            subprocess.run(cmd, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            console.print(f"[yellow]⚠ 无法自动播放，请手动打开：{out_path}[/yellow]")
    emit({"path": str(out_path), "filename": out_path.name}, as_json,
         lambda: console.print(f"[green]✓[/green] 试听音频：{out_path.name}"))


if __name__ == "__main__":
    app()
