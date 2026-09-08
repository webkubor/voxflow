import typer
from cli.commands.voice import app as voice_app
from cli.commands.tts import tts_clone, tts_design, tts_dialogue
from cli.commands.job import app as job_app
from cli.commands.preset import app as preset_app
from cli.commands.doctor import doctor
from cli.commands.ai import ai_script, ai_polish
from cli.commands.stats import stats, logs, backfill
from cli.commands.promo import app as promo_app

app = typer.Typer(
    name="voice",
    help="[bold cyan]VoxFlow 声流[/bold cyan] — 面向人类、AI 与 agent 的本地语音工作台",
    add_completion=False,
)
app.add_typer(voice_app, name="voice")
app.add_typer(job_app, name="job")
app.add_typer(preset_app, name="preset")
app.add_typer(promo_app, name="promo")
app.command("clone")(tts_clone)
app.command("design")(tts_design)
app.command("dialogue")(tts_dialogue)
app.command("doctor")(doctor)
app.command("ai-script")(ai_script)
app.command("ai-polish")(ai_polish)
app.command("stats")(stats)
app.command("logs")(logs)
app.command("backfill-costs")(backfill)


@app.command("web")
def web(
    port: int = typer.Option(8866, "--port", "-p", help="端口号"),
    host: str = typer.Option("0.0.0.0", "--host", help="监听地址"),
):
    """启动 Web UI（本地浏览器操作）"""
    import uvicorn
    typer.echo(typer.style("=" * 50, fg=typer.colors.BRIGHT_YELLOW))
    typer.echo(typer.style("  VoxFlow 声流 Web UI", fg=typer.colors.BRIGHT_YELLOW, bold=True))
    typer.echo(typer.style(f"  http://localhost:{port}", fg=typer.colors.CYAN))
    typer.echo(typer.style("=" * 50, fg=typer.colors.BRIGHT_YELLOW))
    # **单 worker**。之前开 2 个是为了绕开「一个慢请求堵死整个服务」，
    # 但那是在治症状：真因是 40 多个端点写成 `async def` 却在里面跑同步
    # 阻塞调用（LLM 几十秒、suno CLI 十几秒、SQLite、文件 IO）——
    # 同步代码在 async 端点里会**冻住事件循环**，所有其他请求一起排队。
    #
    # 根因修法是把那些端点改回普通 `def`：FastAPI 会自动把同步端点丢进
    # 线程池，事件循环不受影响。改完之后多 worker 不但没必要，还有害 ——
    # 任务队列和指标都在**进程内存**里，2 个 worker 就是两份互相看不见的
    # 状态：任务提交给 worker A，前端下一次轮询打到 worker B 就查不到，
    # 表现为任务在界面上忽隐忽现。而且 4GB 的模型会被加载两遍。
    uvicorn.run("web.app:app", host=host, port=port, reload=False, workers=1)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context):
    """
    voice — VoxFlow 声流

    子命令组：
      voice      音色素材管理（list / add / preview / show / rm / import）
      clone      从已有音色克隆合成
      design     从文字描述设计新音色
      dialogue   根据剧本批量合成多角色对话
      web        启动 Web UI
      doctor     环境自检（Python / 依赖 / 模型 / 硬件 / 目录 / FreeLLMAPI）
      ai-script  AI 文案生成（需 FreeLLMAPI）
      ai-polish  AI 文案润色（需 FreeLLMAPI）
      preset     预设管理（list / show / run / batch）
      job        任务历史（list / show / clean）
      stats      成本与用量（钱花在哪 / 本地省了多少 / 每首歌多少钱）
      logs       运行日志（失败的调用、慢请求）
      backfill-costs  给接入计量前的老作品补估算成本（默认预演）
    """
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


if __name__ == "__main__":
    app()
