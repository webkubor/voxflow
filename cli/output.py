"""CLI 输出约定 —— 给人看的表格和给 agent 读的 JSON 共用一个出口。

## 约定（agent 依赖这些，改动要同步 AGENTS.md）

- 加 `--json` 时，stdout 只输出**一个** JSON 对象：
  成功 `{"ok": true, ...}`；失败 `{"ok": false, "error": "...", "status": 409}`。
  进度、提示一律走 stderr，不污染 stdout。
- 退出码：0 成功 / 1 一般错误或参数无效 / 3 不存在 / 4 冲突（已收藏不可删、
  重名、模板已生成或正在生成）。typer 自身的用法错误仍是 2。
"""
from __future__ import annotations

import json
import sys
from typing import Any, Callable, NoReturn, Optional

import typer
from rich.console import Console

console = Console()
err_console = Console(stderr=True)

EXIT_ERROR, EXIT_NOT_FOUND, EXIT_CONFLICT = 1, 3, 4
_EXIT_BY_STATUS = {404: EXIT_NOT_FOUND, 409: EXIT_CONFLICT}

JSON_OPTION = typer.Option(False, "--json", help="输出单个 JSON 对象（供脚本 / agent 解析）")


def emit(data: dict, as_json: bool, human: Optional[Callable[[], None]] = None) -> None:
    if as_json:
        sys.stdout.write(json.dumps({"ok": True, **data}, ensure_ascii=False, default=str) + "\n")
        sys.stdout.flush()
    elif human:
        human()


def fail(message: str, as_json: bool, status: int = 400) -> NoReturn:
    if as_json:
        sys.stdout.write(json.dumps({"ok": False, "error": message, "status": status},
                                    ensure_ascii=False) + "\n")
        sys.stdout.flush()
    else:
        err_console.print(f"[red]✗[/red] {message}")
    raise typer.Exit(_EXIT_BY_STATUS.get(status, EXIT_ERROR))


def fail_from(exc: Exception, as_json: bool) -> NoReturn:
    fail(str(exc), as_json, getattr(exc, "status", 400))


def progress_console(as_json: bool) -> Console:
    """JSON 模式下进度走 stderr，保证 stdout 可直接解析。"""
    return err_console if as_json else console


def confirm_or_fail(question: str, yes: bool, as_json: bool) -> None:
    """破坏性操作的确认。非交互环境（agent / 管道）必须显式 --yes，不会卡在提示上。"""
    if yes:
        return
    if as_json or not sys.stdin.isatty():
        fail("非交互模式下删除需要显式加 --yes", as_json, 400)
    if not typer.confirm(question, default=False):
        raise typer.Exit(0)


def jsonable(value: Any) -> Any:
    return json.loads(json.dumps(value, ensure_ascii=False, default=str))
