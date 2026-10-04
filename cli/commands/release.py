"""
发行流程的 CLI 入口。

## 为什么要有这个

`submit_release()` / `mark_submitted()` 在 `core/pipeline.py` 里躺了很久，
但**全项目没有一个命令行入口** —— 只有 Web UI 调得到。后果是：

- 手工发布（不走 Web 的人）没法记录「提交了」，`submitted_at` 全空
- 「提交」这个动作在台账里留不下痕迹，事后只能靠公开 API 反推
- 状态机里的 `reviewing` 一格没有任何写入者，审核中永远查不出来

`voice release submitted <歌名> --platform netease` 就是补这个洞：
在平台后台按下提交之后跑一次，台账立刻能回答「什么时候交的、审到哪了」。

## 顺序

    voice release prep      <歌名> --platform netease   # 锁发行身份（备料）
    voice release submitted  <歌名> --platform netease   # 真的交出去了 → reviewing
    voice release status     [歌名]                      # 看现在到哪一步了
"""
import typer

from core import pipeline as P

app = typer.Typer(help="发行流程：备料 / 提交留痕 / 查进度")


def _resolve(ident: str) -> str:
    """
    歌名、完整 ID、**ID 前缀**都收。

    前缀是必须的：整个项目（看板、日志、我自己所有汇报）一律用 8 位前缀
    指代作品，只认完整 UUID 等于让人每次都得先去查一遍。
    """
    t = P.get_track(ident)
    if t:
        return t["id"]
    tracks = P.list_tracks()
    # 前缀匹配：命中唯一一条就用，命中多条让���给更长的前缀
    by_prefix = [x for x in tracks if (x.get("id") or "").startswith(ident)]
    if len(by_prefix) == 1:
        return by_prefix[0]["id"]
    if len(by_prefix) > 1:
        raise typer.BadParameter(
            f"前缀「{ident}」匹配到 {len(by_prefix)} 首，请给更长的 ID 前缀")
    hits = [x for x in tracks
            if (x.get("title") or "") == ident
            or (x.get("release_title") or "") == ident]
    if len(hits) == 1:
        return hits[0]["id"]
    if len(hits) > 1:
        names = "、".join(f"{h['title']}({h['id'][:8]})" for h in hits[:5])
        raise typer.BadParameter(f"「{ident}」匹配到多首，请给 ID：{names}")
    raise typer.BadParameter(f"找不到作品：{ident}")


@app.command("prep")
def prep(
    ident: str = typer.Argument(..., help="歌名或曲目 ID"),
    platform: str = typer.Option(..., "--platform", "-p", help="目标平台 netease/qishui/tencent"),
    title: str = typer.Option("", "--title", "-t", help="发行歌名，不填沿用台账里的"),
):
    """锁定发行身份（独家授权 + 歌名唯一）。**这不等于已经提交。**"""
    tid = _resolve(ident)
    track = P.get_track(tid) or {}
    release_title = (title or track.get("release_title") or track.get("title") or "").strip()
    try:
        res = P.submit_release(tid, platform, release_title)
    except ValueError as e:
        raise typer.BadParameter(str(e))
    # 返回的是整首 track，平台状态嵌在 platforms[platform]
    st = ((res.get("platforms") or {}).get(platform) or {}).get("status", "")
    typer.secho(f"✓ 已备料：{release_title} → {platform}（状态 {st}）", fg=typer.colors.GREEN)
    typer.echo("  还没提交。平台上按下提交之后，跑：")
    typer.echo(f"    voice release submitted {track.get('title')} --platform {platform}")


@app.command("submitted")
def submitted(
    ident: str = typer.Argument(..., help="歌名或曲目 ID"),
    platform: str = typer.Option(..., "--platform", "-p", help="目标平台 netease/qishui/tencent"),
    note: str = typer.Option("", "--note", help="备注，例如提交单号"),
):
    """
    **在平台后台按下提交之后跑这个。** 状态转 reviewing 并记下提交时刻。

    重复跑安全：已在审且已有提交时间时原样返回，不覆盖首次提交时刻。
    """
    tid = _resolve(ident)
    try:
        res = P.mark_submitted(tid, platform, note=note)
    except ValueError as e:
        raise typer.BadParameter(str(e))
    st = ((res.get("platforms") or {}).get(platform) or {})
    typer.secho(f"✓ 已记录提交：{st.get('platform_title') or ''}（{platform}）", fg=typer.colors.GREEN)
    typer.echo(f"  状态 {st.get('status')} · 提交于 {st.get('submitted_at') or '—'}")
    typer.echo("  审核通过/驳回由 sync 脚本回读平台实况自动更新。")


@app.command("status")
def status(
    ident: str = typer.Argument("", help="歌名或 ID；不填列全部在途的"),
):
    """看发行到哪一步了。重点看 submitted_at —— 空的就是没留痕的。"""
    if ident:
        tid = _resolve(ident)
        track = P.get_track(tid) or {}
        rows = track.get("listings") or []
        if not rows:
            typer.echo(f"《{track.get('title')}》还没有任何平台记录。")
            return
        typer.secho(f"《{track.get('title')}》", bold=True)
        for r in rows:
            typer.echo(f"  {r.get('platform',''):<9} {r.get('status',''):<10} "
                       f"提交于 {r.get('submitted_at') or '⚠️ 未记录'}")
        return

    inflight = [t for t in P.list_tracks() if t.get("listings")]
    typer.secho(f"有平台记录的作品 {len(inflight)} 首：", bold=True)
    for t in inflight:
        for r in t["listings"]:
            if r.get("status") in ("online", "published"):
                continue
            flag = "  " if r.get("submitted_at") else "⚠️"
            typer.echo(f"  {flag} {t.get('title','')[:18]:<20} {r.get('platform',''):<9} "
                       f"{r.get('status',''):<10} 提交于 {r.get('submitted_at') or '未记录'}")
    typer.echo("\n⚠️ = 状态不是上架，但没记下提交时刻 —— 这些是流程漏了「submitted」这一步。")
