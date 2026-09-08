import typer
from core import promo

app = typer.Typer(help="宣推短视频管理（基于 reel-kit 合成 1080x1920 竖版推歌视频）")


@app.command("make")
def make_video(
    track_id: str = typer.Argument(..., help="曲目 ID 或唯一标识"),
    template: str = typer.Option("music-card", "--template", "-t", help="reel 模板名称"),
    per_shot: float = typer.Option(2.8, "--per-shot", "-s", help="每镜时长（秒）"),
    accent1: str = typer.Option("#ec4899", "--accent1", help="主渐变色 (十六进制)"),
    accent2: str = typer.Option("#6366f1", "--accent2", help="次渐变色 (十六进制)"),
    footer: str = typer.Option("", "--footer", "-f", help="底部收听引导语"),
):
    """为指定曲目一键合成 1080x1920 竖版宣推短视频。"""
    typer.echo(f"🎬 开始生成宣推短视频 (Track ID: {track_id})...")
    try:
        res = promo.generate_promo_video(
            track_id=track_id,
            template=template,
            per_shot=per_shot,
            accent1=accent1,
            accent2=accent2,
            footer=footer,
        )
        typer.secho("✅ 宣推短视频合成成功！", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"   标题: {res['title']}")
        typer.echo(f"   时长: {res['duration']}s ({res['shots_count']} 镜)")
        typer.echo(f"   文件: {res['video_path']}")
        typer.echo(f"   大小: {round(res['file_size'] / (1024*1024), 2)} MB")
    except Exception as e:
        typer.secho(f"❌ 合成失败: {e}", fg=typer.colors.RED, bold=True)
        raise typer.Exit(1)


@app.command("list")
def list_videos():
    """查看已生成的宣推短视频清单。"""
    videos = promo.list_promo_videos()
    if not videos:
        typer.echo("当前还没有生成任何宣推短视频。使用 `voice promo make [track_id]` 开始生成。")
        return

    typer.secho(f"🎬 已生成宣推短视频 ({len(videos)} 个):", bold=True)
    for v in videos:
        typer.echo(f"  • {v['filename']} ({v['size_mb']} MB) - {v['path']}")


@app.command("status")
def show_status():
    """检查 reel-kit 环境与模板状态。"""
    st = promo.check_promo_status()
    if st.get("available"):
        typer.secho("✅ reel-kit CLI 已就绪", fg=typer.colors.GREEN, bold=True)
        typer.echo(f"   可执行路径: {st['binary']}")
        typer.echo(f"   可用模板: {', '.join(st['templates'])}")
    else:
        typer.secho("❌ reel-kit CLI 未就绪", fg=typer.colors.RED, bold=True)
        typer.echo(f"   错误: {st.get('error')}")
