"""MUSE AV 账户连接 —— `voice museav login / status / logout`

替掉原来靠环境变量注入 voxcraft **租户** Key 的做法。租户模型的含义是
「应用方持 Key、花应用方的池子」，对 VoxFlow 是错的：它装在用户自己机器上，
该花用户自己的积分、产出归用户自己，而且租户 Key 只能整把吊销、
事后查不出哪次调用是哪个工具发的。

授权走中台的应用授权（设备码流程），细节见 core/museav_auth.py。
"""

import typer
from rich.console import Console

from core import museav_auth

app = typer.Typer(name="museav", help="连接 MUSE AV 账户（AI 文案与封面出图用你自己的积分）")
console = Console()


@app.command("login")
def login() -> None:
    """浏览器授权，把这台机器连到你的 MUSE AV 账户"""
    if museav_auth.load_key():
        console.print(f"[dim]已连接 {museav_auth.load_account() or '(账户未知)'}，重新授权会替换掉旧凭据[/dim]")

    def on_code(user_code: str, uri: str) -> None:
        console.print()
        console.print(f"  授权码  [bold cyan]{user_code}[/bold cyan]")
        console.print(f"  授权页  [dim]{uri}[/dim]")
        console.print()
        console.print("[dim]浏览器应该已经打开。核对授权码一致后点「同意授权」，这里会自动继续。[/dim]")

    try:
        r = museav_auth.login(on_code=on_code)
    except museav_auth.AuthError as e:
        console.print(f"[red]授权失败：{e}[/red]")
        raise typer.Exit(1)

    console.print(f"[green]已连接[/green] {r['account_email']}")
    console.print(f"[dim]权限：{', '.join(r['scopes']) or '（无）'}[/dim]")
    console.print("[dim]随时可以在 museav.top 的「账户 → 已授权应用」里撤销。[/dim]")


@app.command("status")
def status() -> None:
    """看当前连的是哪个账户、还剩多少积分"""
    if not museav_auth.load_key():
        console.print("[yellow]未连接[/yellow]  跑 `voice museav login` 连一下")
        console.print(f"[dim]凭据会存到 {museav_auth.CONFIG_PATH}[/dim]")
        raise typer.Exit(1)
    try:
        me = museav_auth.whoami()
    except museav_auth.AuthError as e:
        console.print(f"[red]{e}[/red]")
        raise typer.Exit(1)
    console.print(f"[green]已连接[/green] {me['nickname'] or me['email']}（{me['email']}）")
    console.print(f"剩余积分  [bold]{me['credits']}[/bold]")


@app.command("logout")
def logout() -> None:
    """断开本机连接（不等于在 MUSE AV 那边撤销授权）"""
    if not museav_auth.load_key():
        console.print("[dim]本来就没连接[/dim]")
        return
    museav_auth.forget()
    console.print("[green]已断开本机连接[/green]")
    # 说清这一点：本地删文件不会让那把 Key 在中台失效，
    # 用户以为「退出登录就安全了」是危险的误解
    console.print("[dim]注意：这只删了本机凭据。要让它在服务端彻底失效，去 museav.top 的「账户 → 已授权应用」撤销。[/dim]")
