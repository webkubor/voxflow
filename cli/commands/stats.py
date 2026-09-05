"""
成本与运行状况的终端视图 —— `voice stats` / `voice logs`。

## 为什么 Web 上有了还要做 CLI

两类调用方，需求不一样：

- **人**：跑完一批歌，想在终端直接看「这批花了多少」，不想开浏览器。
- **agent**：`--json` 出结构化结果，可以直接拿去判断「还要不要继续跑」。
  这是这个项目一直以来的做法（`voice doctor --json` 就是先例）。

数据源和 Web 完全一致（`core/obs`），不存在两套口径 —— 那是最容易出
「网页说 30 块、终端说 28 块」这种没人说得清的问题的地方。
"""

from __future__ import annotations

import json as _json

import typer
from rich.console import Console
from rich.table import Table

from core import obs

console = Console()


def stats(
    days: int = typer.Option(30, "--days", "-d", help="统计最近多少天"),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON，供 agent 解析"),
    tracks: bool = typer.Option(False, "--tracks", "-t", help="按作品拆分成本"),
):
    """成本与用量统计：钱花在哪、本地跑省下多少、每首歌多少钱。"""
    summary = obs.usage_summary(days)
    if json_out:
        payload = dict(summary)
        if tracks:
            payload["tracks"] = obs.track_costs()
        console.print_json(_json.dumps(payload, ensure_ascii=False))
        raise typer.Exit(0)

    if not summary.get("by_provider"):
        console.print(f"[dim]最近 {days} 天没有计量记录。"
                      f"生成一首歌或合成一段语音之后再来看。[/dim]")
        raise typer.Exit(0)

    prov_cfg = obs.pricing().get("providers", {})
    t = Table(title=f"最近 {days} 天用量与成本", title_style="bold cyan", header_style="dim")
    t.add_column("上游")
    t.add_column("调用", justify="right")
    t.add_column("失败", justify="right")
    t.add_column("用量", justify="right")
    t.add_column("实付", justify="right")
    t.add_column("商业 API 等价", justify="right")

    for r in summary["by_provider"]:
        cfg = prov_cfg.get(r["provider"], {})
        unit = cfg.get("unit", "")
        qty = r.get("qty") or 0
        qty_s = (f"{qty:.0f} 秒" if unit == "seconds"
                 else f"{r['credits']:.0f} 积分" if r["credits"]
                 else f"{qty:.0f} 次")
        cost = r["cost_cny"] or 0
        t.add_row(
            cfg.get("label", r["provider"]),
            str(r["n"]),
            f"[red]{r['failed']}[/red]" if r["failed"] else "0",
            qty_s,
            f"[bold]¥{cost:.2f}[/bold]" if cost else "[green]免费[/green]",
            f"¥{r.get('market_cny', 0):.2f}" if r.get("market_cny") else "—",
        )
    console.print(t)

    total = summary["total_cny"]
    saved = summary.get("saved_cny", 0)
    est = summary.get("estimated_cny", 0)
    line = (f"\n  实付 [bold]¥{total:.2f}[/bold]"
            f"    本地跑省下 [green]¥{saved:.2f}[/green]")
    # 估算部分单独标出来。不标的话，回填过一次之后就再也分不清哪些数字是实测的，
    # 而分不清的数字最终会被当成实测的拿去做决策。
    if est > 0:
        line += f"    [dim](其中 ¥{est:.2f} 是回填的估算值)[/dim]"
    console.print(line)

    # 失败单独点出来 —— 它是最容易被忽略的那笔浪费。
    #
    # 但措辞要看实际：按积分计费的上游（Suno / 中台）失败也扣分，
    # 而 LLM 网关返回 503 时根本没产生消耗。一律说「照样扣费」会把
    # 「上游挂了」误导成「你亏钱了」，两者要采取的行动完全不同。
    failed_n = sum(r["failed"] for r in summary["by_provider"])
    if failed_n:
        burned = sum(r["failed"] for r in summary["by_provider"]
                     if (r["credits"] or 0) > 0)
        tail = ("（其中有按积分计费的上游 —— 失败照样扣分）" if burned
                else "（这些上游本次未产生消耗，多半是上游不可用）")
        console.print(f"  [yellow]其中 {failed_n} 次调用失败{tail}，"
                      f"看 `voice logs --level error`[/yellow]")

    if tracks:
        costs = obs.track_costs()
        if not costs:
            console.print("\n[dim]还没有关联到作品的成本记录。[/dim]")
            raise typer.Exit(0)
        # 标题从台账取。表里只显示 UUID 的话，人得自己去库里查这是哪首歌 ——
        # 一份要靠翻库才能读懂的成本报表，等于没有报表。
        titles = {}
        try:
            from core import db                                   # noqa: PLC0415
            with db.connect() as c_:
                titles = {r["id"]: r["title"] for r in c_.execute("SELECT id, title FROM tracks")}
        except Exception:
            pass
        tt = Table(title="按作品", title_style="bold cyan", header_style="dim")
        tt.add_column("作品")
        tt.add_column("成本", justify="right")
        tt.add_column("回本播放（网易云实测费率）", justify="right")
        rev = obs.platform_revenue().get("netease") or {}
        rate = rev.get("cny_per_1k_plays") if rev.get("rate_source") == "measured" else None
        for tid, c in sorted(costs.items(), key=lambda kv: -kv[1]["total_cny"])[:30]:
            be = obs.breakeven_plays(c["total_cny"], "netease", rate_override=rate)
            tt.add_row(titles.get(tid, tid)[:28], f"¥{c['total_cny']:.2f}",
                       f"{be:,}" if be else "—")
        console.print()
        console.print(tt)


def backfill(
    apply: bool = typer.Option(False, "--apply", help="真的写入。不带这个只做预演"),
    credits_per_track: float = typer.Option(
        10.0, "--credits", help="每首按多少 Suno 积分估算（一次 generate 出两首扣 10）"),
):
    """
    给接入计量之前的老作品补一笔**估算**成本。

    ## 判据：有 clip_id 就是用 Suno 生成过

    `clip_id` 是 Suno 返回的作品 ID，只有真调过 Suno 才会有 —— 这是硬证据，
    不是猜。从平台同步回来的老作品没有 clip_id，不会被回填。

    ## 但金额仍然是估的

    知道「用过 Suno」不等于知道「用了几次」：重生成过几版、试了几个 persona，
    这些历史里没有。所以按「一首一次生成」的下限估，**宁可少算也不多算**——
    多算出来的成本会让 ROI 看起来比实际差，进而做出错误的收缩决定。

    回填的每一条都带 `estimated=1` 标记，看板和 `voice stats` 会单独把估算
    部分标出来。想撤销：`DELETE FROM usage_events WHERE estimated=1`。

    默认只**预演**，看清楚要写什么再加 `--apply`。
    """
    from core import db, obs as _obs

    db.init()
    with db.connect() as c:
        rows = c.execute(
            "SELECT id, title, clip_id FROM tracks"
            " WHERE clip_id != '' AND clip_id IS NOT NULL"
        ).fetchall()
        already = {r["track_id"] for r in c.execute(
            "SELECT DISTINCT track_id FROM usage_events WHERE provider='suno'")}

    todo = [r for r in rows if r["id"] not in already]
    if not todo:
        console.print("[dim]没有需要回填的作品 —— 有 clip_id 的都已经有成本记录了。[/dim]")
        raise typer.Exit(0)

    unit = _obs.unit_price("suno")
    each = round(credits_per_track * unit, 2)
    t = Table(title=f"{'回填' if apply else '预演'}：{len(todo)} 首老作品",
              title_style="bold cyan", header_style="dim")
    t.add_column("作品")
    t.add_column("clip_id", style="dim")
    t.add_column("估算成本", justify="right")
    for r in todo[:40]:
        t.add_row(r["title"][:28], (r["clip_id"] or "")[:12], f"¥{each:.2f}")
    if len(todo) > 40:
        t.add_row(f"[dim]… 另外 {len(todo) - 40} 首[/dim]", "", "")
    console.print(t)
    console.print(f"\n  合计估算 [bold]¥{each * len(todo):.2f}[/bold]"
                  f"  [dim](每首 {credits_per_track:.0f} 积分 × ¥{unit}/积分)[/dim]")

    if not apply:
        console.print("\n[yellow]这是预演，什么都没写。确认无误后加 --apply。[/yellow]")
        raise typer.Exit(0)

    for r in todo:
        _obs.meter("suno", "generate", qty=1, credits=credits_per_track,
                   track_id=r["id"], ok=True, estimated=True,
                   source="backfill", clip_id=r["clip_id"])
    console.print(f"\n[green]✓ 已回填 {len(todo)} 首，全部标记为估算。[/green]")
    console.print("[dim]  撤销：DELETE FROM usage_events WHERE estimated=1[/dim]")


def logs(
    limit: int = typer.Option(40, "--limit", "-n", help="最多显示多少条"),
    level: str = typer.Option("", "--level", "-l", help="只看某个级别：info / warn / error"),
    event: str = typer.Option("", "--event", "-e", help="按事件名过滤（子串匹配）"),
    days: int = typer.Option(3, "--days", "-d", help="往回翻几天"),
    json_out: bool = typer.Option(False, "--json", help="输出 JSON，供 agent 解析"),
):
    """运行日志：失败的调用、慢请求、启动记录。倒序。"""
    records = obs.read_logs(limit=limit, level=level, event=event, days=days)
    if json_out:
        console.print_json(_json.dumps(records, ensure_ascii=False))
        raise typer.Exit(0)

    if not records:
        hint = ("这个级别下没有日志 —— 对 error 来说，空的是好事。"
                if level == "error" else "还没有日志。服务跑起来之后才会有。")
        console.print(f"[dim]{hint}[/dim]")
        raise typer.Exit(0)

    COLOR = {"error": "red", "warn": "yellow", "info": "dim"}
    for r in records:
        lv = r.get("level", "info")
        rest = "  ".join(f"{k}={v}" for k, v in r.items()
                         if k not in ("ts", "level", "event"))
        console.print(f"[{COLOR.get(lv, 'dim')}]{r.get('ts', '')[11:]}[/] "
                      f"[bold]{r.get('event', '')}[/bold]  [dim]{rest}[/dim]")
