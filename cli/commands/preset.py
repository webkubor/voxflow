import json
import re
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.syntax import Syntax
from rich.panel import Panel

from core.paths import DATA_DIR as BASE_DIR  # 数据根，不是代码目录
PRESETS_DIR = BASE_DIR / "configs" / "presets"
GENERATED_DIR = BASE_DIR / "configs" / "generated"

console = Console()
app = typer.Typer(help="预设管理：列出、查看、执行 configs/presets/ 下的任务。")


def _list_presets():
    items = []
    for fp in sorted(PRESETS_DIR.glob("*.json")):
        try:
            with open(fp, "r", encoding="utf-8") as f:
                data = json.load(f)
            is_batch = data.get("type") == "design_batch"
            item_count = len(data.get("items", [])) if is_batch else 0
            name = data.get("voice_name") or data.get("title") or fp.stem
            model_type = data.get("model_type", "—")
            commit = data.get("commit_to_temp", False)
            items.append(
                {
                    "name": fp.stem,
                    "display_name": name,
                    "type": "批量" if is_batch else "设计",
                    "model": model_type,
                    "commit": "✓" if commit else "—",
                    "items": item_count,
                    "path": fp,
                }
            )
        except Exception:
            pass
    return items


@app.command("list")
def preset_list(
    filter: Optional[str] = typer.Option(
        None, "--filter", "-f", help="按名称过滤（模糊匹配）"
    ),
):
    """列出所有预设任务"""
    items = _list_presets()
    if not items:
        console.print("[yellow]预设目录为空：configs/presets/[/yellow]")
        return

    if filter:
        items = [i for i in items if filter.lower() in i["name"].lower()]

    table = Table(
        title=f"[bold gold1]预设任务库[/bold gold1]  configs/presets/  共 {len(items)} 个"
    )
    table.add_column("类型", justify="center")
    table.add_column("名称", style="cyan")
    table.add_column("音色名", style="white")
    table.add_column("模型", justify="center", style="dim")
    table.add_column("落库", justify="center")
    table.add_column("文件", style="dim", max_width=35)

    for it in items:
        type_tag = (
            f"[yellow]批量({it['items']}项)[/yellow]"
            if it["type"] == "批量"
            else "设计"
        )
        commit = (
            f"[green]{it['commit']}[/green]" if it["commit"] == "✓" else it["commit"]
        )
        table.add_row(
            type_tag,
            it["name"],
            it["display_name"],
            it["model"],
            commit,
            it["path"].name,
        )

    console.print(table)


@app.command("show")
def preset_show(
    name: str = typer.Argument(..., help="预设名称（不含 .json，支持模糊匹配）"),
):
    """查看预设 JSON 详情（语法高亮）"""
    matches = list(PRESETS_DIR.glob(f"*{name}*.json"))
    if not matches:
        console.print(f"[red]✗[/red] 未找到预设：{name}")
        raise typer.Exit(1)
    if len(matches) > 1:
        console.print(f"[yellow]多个匹配，请更精确：[/yellow]")
        for m in matches:
            console.print(f"  - {m.stem}")
        raise typer.Exit(1)

    fp = matches[0]
    with open(fp, "r", encoding="utf-8") as f:
        raw = f.read()

    syntax = Syntax(raw, "json", theme="monokai", line_numbers=True)
    console.print(
        Panel(f"[cyan]{fp.name}[/cyan]", title=f"[gold1]预设详情[/gold1]", expand=False)
    )
    console.print(syntax)


@app.command("run")
def preset_run(
    name: str = typer.Argument(..., help="预设名称（不含 .json，支持模糊匹配）"),
    dry_run: bool = typer.Option(False, "--dry-run", help="仅校验配置，不生成"),
):
    """执行单个预设任务（设计或对话模式）"""
    matches = list(PRESETS_DIR.glob(f"*{name}*.json"))
    if not matches:
        console.print(f"[red]✗[/red] 未找到预设：{name}")
        raise typer.Exit(1)
    if len(matches) > 1:
        console.print(f"[yellow]多个匹配：[/yellow]")
        for m in matches:
            console.print(f"  - {m.stem}")
        raise typer.Exit(1)

    fp = matches[0]
    with open(fp, "r", encoding="utf-8") as f:
        cfg = json.load(f)

    if cfg.get("type") == "design_batch":
        console.print(
            f"[red]✗[/red] {fp.name} 是批量配置，请使用 [cyan]tts preset batch[/cyan] 执行"
        )
        raise typer.Exit(1)

    _run_single_preset(cfg, fp.name, dry_run)


def _run_single_preset(cfg: dict, config_ref: str, dry_run: bool = False):
    from core.engine import TTSBaseEngine
    from core.processor import AudioProcessor
    from core.modes.designer import DesignMode
    from core.modes.cloner import CloneMode
    from core.utils import (
        generate_output_path,
        resolve_design_voice_key,
        resolve_design_voice_label,
        upsert_persona_mapping,
        write_generation_json,
    )
    import soundfile as sf
    import torch

    model_type = cfg.get("model_type", "Base")
    model_size = cfg.get("model_size", "1.7B")
    voice_name = cfg.get("voice_name", "未命名角色")

    console.print(f"[gold1]⏳ 执行预设：{config_ref}[/gold1]")
    console.print(f"  模式：{model_type} | 模型：{model_size} | 音色：{voice_name}")

    if dry_run:
        console.print(f"[yellow]  [dry-run] 跳过实际生成[/yellow]")
        return

    engine = TTSBaseEngine(model_type, model_size)
    processor = AudioProcessor(str(BASE_DIR))

    if model_type == "VoiceDesign":
        designer = DesignMode(engine, processor)
        text = cfg.get("text", "这是一段用于音色建模的短句，请保持自然呼吸。")
        instruct = f"{cfg.get('tone', '')}, {cfg.get('emotion', '')}".strip(", ")
        wavs, sr = designer.run(text=text, lang="Chinese", instruct=instruct)
        final_path = generate_output_path(cfg, str(BASE_DIR))
        sf.write(final_path, wavs[0], sr)
        processor.apply_design_cleanup(final_path)

        if cfg.get("commit_to_temp"):
            voice_key = resolve_design_voice_key(cfg)
            temp_seed_path = processor.extract_voice_seed(
                final_path, voice_name, max_sec=10, skip_start_ms=0
            )
            ref_rel = str(Path(temp_seed_path).relative_to(BASE_DIR)).replace("\\", "/")
            design_rel = f"voice_designs/{voice_name}.json"
            persona_file = upsert_persona_mapping(
                str(BASE_DIR),
                persona_key=voice_key,
                persona_name=voice_name,
                ref_rel=ref_rel,
                design_rel=design_rel,
                instruction=instruct,
            )
            gen_json_path = write_generation_json(
                str(BASE_DIR), voice_key, source="voice_design"
            )
            console.print(f"  [green]✓ 标准样音 → {ref_rel}[/green]")
            console.print(f"  [green]✓ 角色映射 → {persona_file}[/green]")

    else:
        persona = cfg.get("persona", "")
        text = cfg.get("text", "")
        instruct = f"{cfg.get('tone', '')}, {cfg.get('emotion', '')}".strip(", ")
        emotion_priority = bool(cfg.get("emotion_priority", False))
        reference_audio = cfg.get("reference_audio", "")

        cloner = CloneMode(engine, processor)
        wavs, sr = cloner.run(
            persona=persona,
            text=text,
            lang="Chinese",
            instruct=instruct,
            emotion_priority=emotion_priority,
            allow_ref_fallback=True,
            reference_audio=reference_audio or None,
        )
        final_path = generate_output_path(cfg, str(BASE_DIR))
        sf.write(final_path, wavs[0], sr)
        processor.apply_post_tuning(final_path)

    console.print(f"[green]✓ 完成 → {final_path}[/green]")


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
    if name:
        matches = list(PRESETS_DIR.glob(f"*{name}*.json"))
    else:
        default = PRESETS_DIR / "AI女友_批量设计.json"
        if default.exists():
            matches = [default]
        else:
            matches = list(PRESETS_DIR.glob("*.json"))

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
            cfg_path = BASE_DIR / cfg_rel if cfg_rel else None

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
