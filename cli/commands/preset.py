import json
import re
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel

from core import voice_library as vlib
from core.paths import DATA_DIR as BASE_DIR, PROJECT_DIR  # 数据根 / 代码根
from cli.output import JSON_OPTION, emit, fail, fail_from, progress_console

GENERATED_DIR = BASE_DIR / "configs" / "generated"

console = Console()
app = typer.Typer(help="设计模板：列出（含是否已生成）、查看、生成（每个模板只生成一次）、批量。")


def _preset_files() -> list[Path]:
    """用户模板目录 + 内置模板目录（同名以用户的为准），与 Web 同一出处。"""
    return vlib.preset_files(BASE_DIR, PROJECT_DIR)


def _find_preset(name: str, as_json: bool = False) -> Path:
    files = _preset_files()
    exact = [f for f in files if f.stem == name]
    matches = exact or [f for f in files if name.lower() in f.stem.lower()]
    if not matches:
        fail(f"未找到预设：{name}", as_json, 404)
    if len(matches) > 1:
        fail("多个匹配，请更精确：" + "、".join(m.stem for m in matches), as_json)
    return matches[0]


def _list_presets():
    status = {p["config_file"]: p for p in vlib.scan_design_presets(BASE_DIR, PROJECT_DIR)}
    items = []
    for fp in _preset_files():
        try:
            data = json.loads(fp.read_text(encoding="utf-8"))
        except Exception:
            continue
        is_batch = data.get("type") == "design_batch"
        st = status.get(fp.name, {})
        items.append({
            "name": fp.stem,
            "display_name": data.get("voice_name") or data.get("title") or fp.stem,
            "type": "batch" if is_batch else ("design" if data.get("model_type") == "VoiceDesign" else "clone"),
            "model": data.get("model_type", "—"),
            "items": len(data.get("items", [])) if is_batch else 0,
            "has_generated": bool(st.get("has_generated")),
            "audio_file": st.get("audio_file"),
            "path": str(fp),
        })
    return items


@app.command("list")
def preset_list(
    filter: Optional[str] = typer.Option(None, "--filter", "-f", help="按名称过滤（模糊匹配）"),
    pending: bool = typer.Option(False, "--pending", help="只看还没生成过的设计模板"),
    as_json: bool = JSON_OPTION,
):
    """列出全部模板及生成状态"""
    items = _list_presets()
    if filter:
        items = [i for i in items if filter.lower() in i["name"].lower() or filter.lower() in i["display_name"].lower()]
    if pending:
        items = [i for i in items if i["type"] == "design" and not i["has_generated"]]

    def human():
        table = Table(title=f"[bold gold1]设计模板[/bold gold1]  共 {len(items)} 个")
        table.add_column("类型", justify="center")
        table.add_column("名称", style="cyan")
        table.add_column("音色名")
        table.add_column("状态", justify="center")
        for it in items:
            type_tag = f"[yellow]批量({it['items']})[/yellow]" if it["type"] == "batch" else it["type"]
            state = "[green]已生成[/green]" if it["has_generated"] else ("—" if it["type"] != "design" else "未生成")
            table.add_row(type_tag, it["name"], it["display_name"], state)
        console.print(table)

    emit({"presets": items, "total": len(items)}, as_json, human)


@app.command("show")
def preset_show(
    name: str = typer.Argument(..., help="预设名称（不含 .json，支持模糊匹配）"),
    as_json: bool = JSON_OPTION,
):
    """查看预设 JSON 详情"""
    fp = _find_preset(name, as_json)
    raw = fp.read_text(encoding="utf-8")
    if as_json:
        emit({"name": fp.stem, "path": str(fp), "config": json.loads(raw)}, True)
        return

    syntax = Syntax(raw, "json", theme="monokai", line_numbers=True)
    console.print(
        Panel(f"[cyan]{fp.name}[/cyan]", title=f"[gold1]预设详情[/gold1]", expand=False)
    )
    console.print(syntax)


@app.command("run")
def preset_run(
    name: str = typer.Argument(..., help="预设名称（不含 .json，支持模糊匹配）"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅校验配置，不生成"),
    as_json: bool = JSON_OPTION,
):
    """生成单个模板。已生成或正在生成的模板会被拒绝（退出码 4）。"""
    fp = _find_preset(name, as_json)
    cfg = json.loads(fp.read_text(encoding="utf-8"))
    if cfg.get("type") == "design_batch":
        fail(f"{fp.name} 是批量配置，请使用 voice preset batch", as_json)
    try:
        result = _run_single_preset(cfg, fp.name, dry_run, out=progress_console(as_json))
    except vlib.VoiceLibraryError as exc:
        fail_from(exc, as_json)
    emit(result, as_json)


def _run_single_preset(cfg: dict, config_ref: str, dry_run: bool = False, out=console) -> dict:
    from contextlib import nullcontext
    from core.engine import TTSBaseEngine
    from core.processor import AudioProcessor
    from core.modes.designer import DesignMode
    from core.modes.cloner import CloneMode
    from core.utils import generate_output_path
    import soundfile as sf

    model_type = cfg.get("model_type", "Base")
    model_size = cfg.get("model_size", "1.7B")
    voice_name = cfg.get("voice_name", "未命名角色")
    is_design = model_type == "VoiceDesign"

    out.print(f"[gold1]⏳ 执行预设：{config_ref}[/gold1]  模式：{model_type} | 音色：{voice_name}")
    if is_design and vlib.find_preset_audio(voice_name, BASE_DIR):
        raise vlib.Conflict("该模板已经生成，请在生成库中查看（voice library list --kind design）")
    if dry_run:
        out.print("[yellow]  [dry-run] 跳过实际生成[/yellow]")
        return {"preset": config_ref, "dry_run": True}

    result = {"preset": config_ref, "voice_name": voice_name}
    guard = vlib.preset_generation_lock(voice_name, BASE_DIR) if is_design else nullcontext()
    with guard:
        engine = TTSBaseEngine(model_type, model_size)
        processor = AudioProcessor(str(BASE_DIR))
        if is_design:
            text = cfg.get("text") or "这是一段用于音色建模的短句，请保持自然呼吸。"
            instruct = " ".join(p.strip() for p in [cfg.get("tone", ""), cfg.get("emotion", "")] if p.strip())
            wavs, sr = DesignMode(engine, processor).run(text=text, lang="Chinese", instruct=instruct)
            # 与 Web 同一命名规则 + 原文旁注，模板状态才认得出、之后才能直接收藏。
            final_path = BASE_DIR / "out" / vlib.design_filename(voice_name)
            final_path.parent.mkdir(parents=True, exist_ok=True)
            sf.write(str(final_path), wavs[0], sr)
            processor.apply_design_cleanup(str(final_path))
            vlib.write_design_sidecar(final_path, text)
        else:
            instruct = " ".join(p.strip() for p in [cfg.get("tone", ""), cfg.get("emotion", "")] if p.strip())
            wavs, sr = CloneMode(engine, processor).run(
                persona=cfg.get("persona", ""), text=cfg.get("text", ""), lang="Chinese",
                instruct=instruct, emotion_priority=bool(cfg.get("emotion_priority", False)),
                allow_ref_fallback=True, reference_audio=cfg.get("reference_audio") or None,
            )
            final_path = Path(generate_output_path(cfg, str(BASE_DIR)))
            sf.write(str(final_path), wavs[0], sr)
            processor.apply_post_tuning(str(final_path))
    result.update(filename=final_path.name, path=str(final_path))

    if is_design and cfg.get("commit_to_temp"):
        try:
            saved = vlib.save_design(final_path.name, voice_name, instruct, text, processor=processor)
            result["persona_key"] = saved["persona_key"]
            out.print(f"  [green]✓ 已收藏到音色库 → {saved['persona_key']}[/green]")
        except vlib.VoiceLibraryError as exc:
            # 生成结果保留在生成库，之后可 voice library save 换个名字收藏。
            result["commit_error"] = str(exc)
            out.print(f"  [yellow]⚠ 未收藏：{exc}[/yellow]")
    out.print(f"[green]✓ 完成 → {final_path}[/green]")
    return result


@app.command("batch")
def preset_batch(
    name: Optional[str] = typer.Argument(
        None, help="批量配置文件名（不含 .json），留空执行默认 AI女友_批量设计.json"
    ),
    dry_run: bool = typer.Option(
        False, "--dry-run", help="仅打印将执行的命令，不实际生成"
    ),
    filter: Optional[str] = typer.Option(
        None, "--filter", "-f", help="glob 过滤，如 小烛_*"
    ),
):
    """执行批量预设任务"""
    files = _preset_files()
    if name:
        matches = [f for f in files if name.lower() in f.stem.lower()]
    else:
        default = [f for f in files if f.name == "AI女友_批量设计.json"]
        matches = default or files

    batch_files = []
    for fp in matches:
        with open(fp, "r", encoding="utf-8") as f:
            cfg = json.load(f)
        if cfg.get("type") == "design_batch":
            batch_files.append(fp)

    if not batch_files:
        console.print("[red]✗ 未找到批量配置文件[/red]")
        raise typer.Exit(1)

    total_success = 0
    total_failed = 0

    for bp in batch_files:
        with open(bp, "r", encoding="utf-8") as f:
            batch_cfg = json.load(f)

        items = batch_cfg.get("items", [])
        if filter:
            items = [it for it in items if _glob_match(it.get("name", ""), filter)]

        console.print(
            f"\n[bold gold1]━━━━ {bp.name} ({len(items)} 项) ━━━━[/bold gold1]"
        )

        for i, item in enumerate(items, 1):
            if not isinstance(item, dict):
                continue
            if item.get("enabled") is False:
                console.print(f"  [dim][{i}] 跳过（disabled）[/dim]")
                continue

            item_name = item.get("name", f"任务{i}")
            cfg_rel = item.get("config", "")
            cfg_path = next((root / cfg_rel for root in (BASE_DIR, PROJECT_DIR)
                             if cfg_rel and (root / cfg_rel).exists()), None)

            if not cfg_path or not cfg_path.exists():
                console.print(f"  [red][{i}] ✗ 配置不存在：{cfg_rel}[/red]")
                total_failed += 1
                continue

            with open(cfg_path, "r", encoding="utf-8") as f:
                task_cfg = json.load(f)

            console.print(f"  [{i}] {item_name} ... ", end="")
            if dry_run:
                console.print("[yellow][dry-run][/yellow]")
                continue

            try:
                _run_single_preset(task_cfg, cfg_path.name, dry_run=False)
                console.print(f"  [green]✓[/green]")
                total_success += 1
            except vlib.Conflict as e:
                console.print(f"  [dim]跳过：{e}[/dim]")
            except Exception as e:
                console.print(f"  [red]✗ {e}[/red]")
                total_failed += 1

    console.print(f"\n[bold]━━━━ 结果 ━━━━[/bold]")
    console.print(
        f"  [green]成功：{total_success}[/green]  [red]失败：{total_failed}[/red]"
    )


def _glob_match(text: str, pattern: str) -> bool:
    import fnmatch

    return fnmatch.fnmatch(text.lower(), f"*{pattern.lower()}*")
