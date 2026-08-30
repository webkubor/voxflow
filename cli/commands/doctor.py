"""voice doctor — 环境自检命令

检查 Python 版本、虚拟环境、依赖完整性、模型就绪状态、硬件加速、
FFmpeg、目录结构、音色库等，输出清晰的 PASS / WARN / FAIL 报告。
"""

import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table
from rich.panel import Panel

BASE_DIR = Path(__file__).resolve().parent.parent.parent

console = Console()

# ── 检查项定义 ──────────────────────────────────────────────

CHECKS = []


def register(func):
    CHECKS.append(func)
    return func


def _ok(msg: str, detail: str = "") -> tuple:
    return ("PASS", msg, detail)


def _warn(msg: str, detail: str = "") -> tuple:
    return ("WARN", msg, detail)


def _fail(msg: str, detail: str = "") -> tuple:
    return ("FAIL", msg, detail)


# ── 1. Python 版本 ──────────────────────────────────────────

@register
def check_python_version():
    v = sys.version_info
    ver_str = f"{v.major}.{v.minor}.{v.micro}"
    if v >= (3, 10):
        return _ok(f"Python {ver_str}", f"路径: {sys.executable}")
    return _fail(f"Python {ver_str} 版本过低", "需要 >= 3.10")


# ── 2. 虚拟环境 ─────────────────────────────────────────────

@register
def check_venv():
    venv_dir = BASE_DIR / ".venv"
    in_venv = hasattr(sys, "real_prefix") or (
        hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
    )
    if in_venv:
        return _ok("虚拟环境已激活", f"{sys.prefix}")
    if venv_dir.exists():
        return _warn(
            ".venv 存在但未激活",
            "运行 source .venv/bin/activate 激活",
        )
    return _fail("未找到 .venv", "运行 ./install.sh 创建虚拟环境")


# ── 3. 核心依赖 ─────────────────────────────────────────────

CORE_PACKAGES = [
    "transformers",
    "torch",
    "torchaudio",
    "fastapi",
    "uvicorn",
    "typer",
    "rich",
    "librosa",
    "soundfile",
    "pydub",
    "einops",
    "accelerate",
]


@register
def check_dependencies():
    import importlib

    missing = []
    versions = {}
    for pkg in CORE_PACKAGES:
        try:
            mod = importlib.import_module(pkg)
            ver = getattr(mod, "__version__", "?")
            versions[pkg] = ver
        except ImportError:
            missing.append(pkg)

    if not missing:
        detail = ", ".join(f"{k}=={v}" for k, v in list(versions.items())[:5])
        return _ok(f"核心依赖完整（{len(CORE_PACKAGES)} 个）", detail + " ...")
    return _fail(
        f"缺失 {len(missing)} 个依赖: {', '.join(missing)}",
        "运行 pip install -e . && pip install pydub modelscope",
    )


# ── 4. PyTorch 硬件加速 ─────────────────────────────────────

@register
def check_torch_device():
    try:
        import torch

        if torch.backends.mps.is_available():
            return _ok("MPS 加速可用（Apple Silicon GPU）")
        if torch.cuda.is_available():
            gpu = torch.cuda.get_device_name(0)
            return _ok(f"CUDA 加速可用（{gpu}）")
        return _warn("仅 CPU 模式", "推理速度较慢，建议 Apple Silicon 设备")
    except ImportError:
        return _fail("torch 未安装", "运行 pip install torch torchaudio")


# ── 5. Qwen3-TTS SDK ────────────────────────────────────────

@register
def check_qwen_tts():
    try:
        from qwen_tts import Qwen3TTSModel

        return _ok("qwen_tts SDK 可用")
    except ImportError:
        return _fail("qwen_tts 未安装", "项目包未正确安装，运行 pip install -e .")
    except Exception as e:
        return _warn(f"qwen_tts 导入异常: {e}", "可能缺少依赖")


# ── 6. 模型就绪状态 ─────────────────────────────────────────

@register
def check_models():
    models_dir = BASE_DIR / "models"
    if not models_dir.exists():
        return _fail("models/ 目录不存在", "运行 ./install.sh 下载模型")

    results = []
    all_ok = True
    for name, min_size_mb in [("Base-1.7B", 3000), ("VoiceDesign-1.7B", 3000)]:
        model_path = models_dir / name
        if not model_path.exists():
            results.append(f"{name}: 缺失")
            all_ok = False
            continue

        # 计算目录大小
        total_size = 0
        for f in model_path.rglob("*"):
            if f.is_file():
                total_size += f.stat().st_size
        size_mb = total_size / (1024 * 1024)

        if size_mb < min_size_mb:
            results.append(f"{name}: 不完整 ({size_mb:.0f}MB)")
            all_ok = False
        else:
            results.append(f"{name}: 就绪 ({size_mb:.0f}MB)")

    detail = " | ".join(results)
    if all_ok:
        return _ok("模型已就绪", detail)
    return _fail("模型不完整", detail + " | 运行 ./install.sh 下载")


# ── 7. FFmpeg ───────────────────────────────────────────────

@register
def check_ffmpeg():
    path = shutil.which("ffmpeg")
    if path:
        try:
            result = subprocess.run(
                [path, "-version"], capture_output=True, text=True, timeout=5
            )
            first_line = result.stdout.split("\n")[0] if result.stdout else ""
            return _ok("FFmpeg 已安装", first_line)
        except Exception:
            return _ok("FFmpeg 已安装", path)
    return _warn("FFmpeg 未安装", "brew install ffmpeg (macOS)")


# ── 8. 目录结构 ─────────────────────────────────────────────

REQUIRED_DIRS = [
    "cli",
    "core",
    "core/modes",
    "web",
    "web/static",
    "configs",
    "configs/presets",
    "assets",
    "assets/temp",
    "out",
]


@register
def check_directories():
    missing = []
    for d in REQUIRED_DIRS:
        if not (BASE_DIR / d).exists():
            missing.append(d)

    if not missing:
        return _ok(f"目录结构完整（{len(REQUIRED_DIRS)} 个）")
    return _warn(
        f"缺失 {len(missing)} 个目录: {', '.join(missing)}",
        "部分功能可能不可用",
    )


# ── 9. 音色库 ───────────────────────────────────────────────

@register
def check_personas():
    persona_file = BASE_DIR / "configs" / "personas.json"
    if not persona_file.exists():
        return _warn("personas.json 不存在", "尚未注册任何音色")

    try:
        with open(persona_file, "r", encoding="utf-8") as f:
            data = json.load(f)
    except Exception as e:
        return _fail(f"personas.json 解析失败: {e}")

    if not isinstance(data, dict):
        return _fail("personas.json 格式错误", "应为 JSON 对象")

    count = len(data)
    if count == 0:
        return _warn("音色库为空", "使用 voice voice add 注册音色")

    # 检查参考音频
    missing_ref = []
    for key, val in data.items():
        if isinstance(val, dict):
            ref = val.get("ref", "")
            if ref and not (BASE_DIR / ref).exists():
                missing_ref.append(key)

    if missing_ref:
        return _warn(
            f"音色库 {count} 个音色，{len(missing_ref)} 个缺参考音频",
            f"缺失: {', '.join(missing_ref[:5])}",
        )
    return _ok(f"音色库就绪（{count} 个音色）")


# ── 10. CLI 入口 ────────────────────────────────────────────

@register
def check_cli_entry():
    voice_path = shutil.which("voice")
    if voice_path:
        return _ok("voice 命令可用", voice_path)

    venv_voice = BASE_DIR / ".venv" / "bin" / "voice"
    if venv_voice.exists():
        return _warn(
            "voice 在 .venv 中但未加入 PATH",
            "运行 source .venv/bin/activate",
        )
    return _fail("voice 命令未安装", "运行 pip install -e .")


# ── 11. Web UI 依赖 ─────────────────────────────────────────

@register
def check_web_ui():
    try:
        import uvicorn
        import fastapi
        import multipart  # python-multipart

        return _ok("Web UI 依赖就绪", "运行 voice web 启动")
    except ImportError as e:
        return _warn(f"Web UI 依赖缺失: {e}", "pip install fastapi uvicorn python-multipart")


# ── 12. presets 配方 ────────────────────────────────────────

@register
def check_presets():
    presets_dir = BASE_DIR / "configs" / "presets"
    if not presets_dir.exists():
        return _warn("configs/presets/ 不存在", "音色设计预设配方缺失")
    files = list(presets_dir.glob("*.json"))
    if not files:
        return _warn("预设配方为空", "configs/presets/ 下无 JSON 文件")
    return _ok(f"预设配方就绪（{len(files)} 个）")


# ── 13. AI 文案助手（任何 OpenAI 兼容后端）─────────────────────────────

@register
def check_freellmapi():
    try:
        from core.llm_client import check_status
        status = check_status()
        if status["available"]:
            models = status.get("models", [])
            model_str = ", ".join(models[:3]) if models else "auto"
            return _ok("AI 文案助手已连接", f"模型: {model_str}{' ...' if len(models) > 3 else ''}")
        return _warn(
            "AI 文案助手未连接",
            "AI 文案助手不可用 | 配好 VOXCRAFT_LLM_BASE_URL/API_KEY/MODEL，或用项目根目录的 ./run.sh",
        )
    except ImportError:
        return _warn("openai SDK 未安装", "pip install openai")
    except Exception as e:
        return _warn(f"AI 文案助手检测异常: {e}", "检查 VOXCRAFT_LLM_BASE_URL 指向的服务是否可达")


# ── 主命令 ──────────────────────────────────────────────────


def doctor(
    fix: bool = typer.Option(False, "--fix", help="尝试自动修复可修复的问题"),
    json_output: bool = typer.Option(False, "--json", help="输出 JSON 格式（适合 agent 解析）"),
):
    """环境自检：全面检查运行环境，输出 PASS / WARN / FAIL 报告。"""

    results = []
    for check_fn in CHECKS:
        try:
            status, msg, detail = check_fn()
        except Exception as e:
            status, msg, detail = "FAIL", f"{check_fn.__name__} 异常: {e}", ""
        results.append((status, msg, detail))

    if json_output:
        output = [
            {"status": s, "message": m, "detail": d} for s, m, d in results
        ]
        typer.echo(json.dumps(output, ensure_ascii=False, indent=2))
        # 非零退出码如果有 FAIL
        if any(s == "FAIL" for s, _, _ in results):
            raise typer.Exit(1)
        return

    # ── Rich 表格输出 ──
    table = Table(title="[bold gold1]voice doctor — 环境自检报告[/bold gold1]")
    table.add_column("状态", justify="center", width=6)
    table.add_column("检查项", style="white")
    table.add_column("详情", style="dim")

    pass_count = 0
    warn_count = 0
    fail_count = 0

    for status, msg, detail in results:
        if status == "PASS":
            icon = "[green]PASS[/green]"
            pass_count += 1
        elif status == "WARN":
            icon = "[yellow]WARN[/yellow]"
            warn_count += 1
        else:
            icon = "[red]FAIL[/red]"
            fail_count += 1

        table.add_row(icon, msg, detail)

    console.print(table)

    # ── 汇总 ──
    total = len(results)
    summary_parts = [
        f"[green]{pass_count} PASS[/green]",
        f"[yellow]{warn_count} WARN[/yellow]",
        f"[red]{fail_count} FAIL[/red]",
    ]
    summary = f"  |  ".join(summary_parts)

    if fail_count > 0:
        banner = f"[red]FAIL[/red]  {fail_count} 项未通过，{total} 项检查  |  {summary}"
        color = "red"
    elif warn_count > 0:
        banner = f"[yellow]WARN[/yellow]  {warn_count} 项需注意，{total} 项检查  |  {summary}"
        color = "yellow"
    else:
        banner = f"[green]ALL PASS[/green]  {total} 项检查全部通过  |  {summary}"
        color = "green"

    console.print()
    console.print(Panel(banner, border_style=color, expand=False))

    # ── 修复建议 ──
    if fail_count > 0:
        console.print("\n[bold red]修复建议：[/bold red]")
        for status, msg, detail in results:
            if status == "FAIL" and detail:
                console.print(f"  [red]*[/red] {msg}")
                console.print(f"    [dim]→ {detail}[/dim]")

    if fix:
        console.print("\n[cyan]--fix 模式：尝试自动修复...[/cyan]")
        _try_fix(results)

    # 非零退出码如果有 FAIL
    if fail_count > 0:
        raise typer.Exit(1)


def _try_fix(results):
    """尝试自动修复可修复的问题"""
    fixed = 0
    for status, msg, detail in results:
        if status != "FAIL":
            continue

        # 创建缺失目录
        if "目录" in msg:
            for d in REQUIRED_DIRS:
                dir_path = BASE_DIR / d
                if not dir_path.exists():
                    dir_path.mkdir(parents=True, exist_ok=True)
                    console.print(f"  [green]✓[/green] 创建目录: {d}")
                    fixed += 1

        # 重新安装依赖
        if "依赖" in msg or "torch" in msg or "qwen_tts" in msg:
            console.print(f"  [cyan]→[/cyan] 重新安装依赖...")
            subprocess.run(
                [sys.executable, "-m", "pip", "install", "-e", "."],
                cwd=str(BASE_DIR),
            )
            fixed += 1
            break

    if fixed:
        console.print(f"\n[green]✓ 自动修复了 {fixed} 项，请重新运行 voice doctor 验证[/green]")
    else:
        console.print(f"  [yellow]没有可自动修复的项目[/yellow]")
