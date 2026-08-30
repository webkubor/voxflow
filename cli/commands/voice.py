import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Optional

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich import print as rprint

from core.paths import DATA_DIR as BASE_DIR  # 数据根，不是代码目录
sys.path.insert(0, str(BASE_DIR))

from core.processor import AudioProcessor
from core.utils import (
    PERSONA_CONFIG,
    get_persona_map,
    get_persona_cn,
    sanitize_path_component,
    upsert_persona_mapping,
)

console = Console()
app = typer.Typer(help="音色素材管理：注册、预听、查看、删除本地音色。")

ALLOWED_AUDIO_EXTS = (".wav", ".mp3", ".m4a", ".flac", ".ogg", ".aac")


def _resolve_audio(path: str) -> Path:
    p = Path(path)
    if not p.is_absolute():
        p = BASE_DIR / path
    if not p.exists():
        raise FileNotFoundError(f"音频文件不存在：{p}")
    if p.suffix.lower() not in ALLOWED_AUDIO_EXTS:
        raise ValueError(
            f"不支持的格式：{p.suffix}，仅支持 {', '.join(ALLOWED_AUDIO_EXTS)}"
        )
    return p


def _new_temp_path(persona_cn: str) -> Path:
    """**新建**样音时的落盘位置。只在写入侧用 —— 读取一律走 ref 字段，
    否则名字就成了路径的一部分，改个名音频就找不到了。"""
    safe = sanitize_path_component(persona_cn, fallback="未命名角色")
    return BASE_DIR / "assets" / "temp" / f"当前参考_{safe}.wav"


def _ref_path(data: dict) -> Path | None:
    """音色的参考音频 —— 路径存在 ref 字段里，不从名字推导。"""
    rel = str((data or {}).get("ref", "")).strip()
    return (BASE_DIR / rel) if rel else None


def _design_path(data: dict) -> Path | None:
    """设计配方 —— 同上，读 design 字段。"""
    rel = str((data or {}).get("design", "")).strip()
    return (BASE_DIR / rel) if rel else None


def _load_personas() -> dict:
    if not os.path.exists(PERSONA_CONFIG):
        return {}
    with open(PERSONA_CONFIG, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_personas(data: dict):
    with open(PERSONA_CONFIG, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


@app.command("list")
def voice_list():
    """列出所有已注册音色（表格形式）"""
    personas = _load_personas()
    if not personas:
        console.print(
            "[yellow]音色库为空，请先使用 voice voice add <key> <audio> 注册音色。[/yellow]"
        )
        return

    table = Table(title="[bold gold1]音色库[/bold gold1]")
    table.add_column("Key", style="cyan", no_wrap=True)
    table.add_column("名称", style="white")
    table.add_column("样音状态", justify="center")
    table.add_column("设计配方", justify="center")
    table.add_column("基础指令", style="dim")

    for key, data in personas.items():
        name = data.get("name", key) if isinstance(data, dict) else data
        data = data if isinstance(data, dict) else {}

        ref_path = _ref_path(data)
        has_temp = "✓" if (ref_path and ref_path.exists()) else "✗"

        design_path = _design_path(data)
        has_design = "✓" if (design_path and design_path.exists()) else "✗"

        instruction = data.get("instruction", "")
        instr_short = instruction[:20] + "..." if len(instruction) > 20 else instruction

        table.add_row(key, name, has_temp, has_design, instr_short)

    console.print(table)
    console.print(f"\n[dim]共 {len(personas)} 个音色[/dim]")


@app.command("add")
def voice_add(
    key: str = typer.Argument(..., help="音色唯一标识（英文/拼音，推荐，如 shui_yan）"),
    audio: str = typer.Argument(..., help="参考音频路径（绝对路径或相对于项目根目录）"),
    name: Optional[str] = typer.Option(
        None, "--name", "-n", help="音色显示名，默认等于 key"
    ),
    instruction: Optional[str] = typer.Option(
        None, "--instruction", "-i", help="音色基础指令/描述"
    ),
):
    """从参考音频注册新音色（提取标准样音并写入 personas.json）"""
    audio_path = _resolve_audio(audio)
    display_name = name or key

    processor = AudioProcessor(str(BASE_DIR))
    temp_path = processor.extract_voice_seed(
        str(audio_path), display_name, max_sec=10, skip_start_ms=1500
    )

    ref_rel = os.path.relpath(temp_path, BASE_DIR).replace("\\", "/")
    upsert_persona_mapping(
        str(BASE_DIR),
        persona_key=key,
        persona_name=display_name,
        ref_rel=ref_rel,
        design_rel="",
        instruction=instruction or "",
    )

    console.print(f"[green]✓[/green] 音色 [bold]{display_name}[/bold]（{key}）已注册")
    console.print(f"  样音 → {ref_rel}")


@app.command("preview")
def voice_preview(
    key: str = typer.Argument(..., help="音色 key"),
    text: str = typer.Option(
        "这是一段简短的测试语音，用来验证音色效果。", "--text", "-t", help="试听文本"
    ),
):
    """用短句预听音色（调用 CloneMode 生成 5 秒音频并播放）"""
    personas = _load_personas()
    if key not in personas:
        console.print(f"[red]✗[/red] 音色 key 不存在：{key}")
        raise typer.Exit(1)

    data = personas[key]
    name = data.get("name", key) if isinstance(data, dict) else key
    data = data if isinstance(data, dict) else {}

    ref_rel = data.get("ref", "")
    if not ref_rel:
        console.print(f"[red]✗[/red] 音色 {key} 缺少 ref 路径")
        raise typer.Exit(1)

    ref_path = BASE_DIR / ref_rel
    if not ref_path.exists():
        console.print(f"[red]✗[/red] 参考音频不存在：{ref_path}")
        raise typer.Exit(1)

    out_dir = BASE_DIR / "out"
    out_dir.mkdir(exist_ok=True)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
    out_path = out_dir / f"[试听]{name}_{ts}.wav"

    console.print(f"[cyan]⏳ 正在生成试听音频...[/cyan]")
    try:
        import soundfile as sf
        import torch
        from core.engine import TTSBaseEngine
        from core.modes.cloner import CloneMode

        engine = TTSBaseEngine("Base", "1.7B")
        processor = AudioProcessor(str(BASE_DIR))
        cloner = CloneMode(engine, processor)

        instruction = data.get("instruction", "")
        full_instruct = (
            f"<|im_start|>user\n{instruction}<|im_end|>\n" if instruction else ""
        )
        input_objs = engine.processor(
            text=full_instruct, return_tensors="pt", padding=True
        )
        instruct_ids = input_objs["input_ids"].to(engine.device)

        torch.manual_seed(42)
        wavs, sr = engine.wrapped_model.generate_voice_clone(
            text=text,
            language="Chinese",
            ref_audio=str(ref_path),
            x_vector_only_mode=True,
            instruct_ids=[instruct_ids],
            do_sample=True,
            temperature=0.7,
            top_p=0.9,
            top_k=50,
        )
        sf.write(str(out_path), wavs[0], sr)
    except Exception as e:
        console.print(f"[red]✗ 生成失败：{e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]✓[/green] 试听音频已生成：{out_path.name}")

    try:
        subprocess.run(["afplay", str(out_path)], check=True)
    except subprocess.CalledProcessError:
        console.print(f"[yellow]⚠ 无法自动播放，请手动打开：{out_path}[/yellow]")


@app.command("show")
def voice_show(
    key: str = typer.Argument(..., help="音色 key"),
):
    """查看音色详细信息（personas.json 条目 + 设计配方内容）"""
    personas = _load_personas()
    if key not in personas:
        console.print(f"[red]✗[/red] 音色 key 不存在：{key}")
        raise typer.Exit(1)

    data = personas[key]
    name = data.get("name", key) if isinstance(data, dict) else key
    data = data if isinstance(data, dict) else {}

    ref_rel = data.get("ref", "")
    ref_path = _ref_path(data)
    design_rel = data.get("design", "")
    design_path = _design_path(data)

    temp_path = ref_path
    design_data = None
    if design_path and design_path.exists():
        with open(design_path, "r", encoding="utf-8") as f:
            design_data = json.load(f)

    lines = [
        f"[bold cyan]Key:[/bold cyan] {key}",
        f"[bold cyan]名称:[/bold cyan] {name}",
        f"[bold cyan]参考音频:[/bold cyan] {ref_rel or '[无]'} {'[green]✓[/green]' if ref_path and ref_path.exists() else '[red]✗ 缺失[/red]'}",
        f"[bold cyan]标准样音:[/bold cyan] {temp_path.name} {'[green]✓[/green]' if temp_path.exists() else '[red]✗ 缺失[/red]'}",
        f"[bold cyan]设计配方:[/bold cyan] {design_rel or '[无]'} {'[green]✓[/green]' if design_data else '[yellow]仅注册未生成配方[/yellow]'}",
    ]

    if data.get("instruction"):
        lines.append(f"[bold cyan]基础指令:[/bold cyan] {data['instruction']}")

    console.print(
        Panel("\n".join(lines), title=f"[gold1]音色详情 — {name}[/gold1]", expand=False)
    )

    if design_data:
        console.print("\n[bold cyan]设计配方内容:[/bold cyan]")
        console.print_json(json.dumps(design_data, ensure_ascii=False, indent=2))


@app.command("rm")
def voice_rm(
    key: str = typer.Argument(..., help="要删除的音色 key"),
    force: bool = typer.Option(False, "--force", "-f", help="跳过确认直接删除"),
):
    """删除音色注册（仅从 personas.json 移除，不删除实际音频文件）"""
    personas = _load_personas()
    if key not in personas:
        console.print(f"[red]✗[/red] 音色 key 不存在：{key}")
        raise typer.Exit(1)

    data = personas[key]
    name = data.get("name", key) if isinstance(data, dict) else key

    if not force:
        confirm = typer.prompt(
            f"确认删除音色 [bold]{name}[/bold]（{key}）？输入 y 确认："
        )
        if confirm.lower() != "y":
            console.print("[yellow]已取消。[/yellow]")
            raise typer.Exit(0)

    del personas[key]
    _save_personas(personas)
    console.print(f"[green]✓[/green] 已从音色库移除：{key}（{name}）")


@app.command("import")
def voice_import(
    path: str = typer.Argument(..., help="要导入的 personas.json 路径"),
):
    """批量导入音色（合并到现有 personas.json）"""
    import_path = Path(path)
    if not import_path.is_absolute():
        import_path = BASE_DIR / path
    if not import_path.exists():
        console.print(f"[red]✗[/red] 文件不存在：{import_path}")
        raise typer.Exit(1)

    with open(import_path, "r", encoding="utf-8") as f:
        imported = json.load(f)

    if not isinstance(imported, dict):
        console.print(f"[red]✗[/red] 导入文件必须是 JSON 对象")
        raise typer.Exit(1)

    existing = _load_personas()
    added = 0
    updated = 0
    for k, v in imported.items():
        if k in existing:
            updated += 1
        else:
            added += 1
        existing[k] = v

    _save_personas(existing)
    console.print(
        f"[green]✓[/green] 导入完成：新增 {added} 个，更新 {updated} 个（总计 {len(existing)} 个音色）"
    )


if __name__ == "__main__":
    app()
