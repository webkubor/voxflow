"""版本与更新检查。

## 为什么需要它

别人 clone 下来跑本地，**不会主动去 git pull**。于是过几天他手里的
就是个旧版本 —— 而这个项目最近每天都在改发布流程和台账字段，
版本落后的直接后果是「他那边的表和你这边对不上」，
然后开始怀疑是数据问题。

所以要在界面上直接告诉他：你落后几个提交了，跑一行命令就能跟上。

## 怎么判断「有新版本」

比 **commit** 不比 tag：这个项目改得频繁但很少打 tag，只看 tag 会
永远显示「已是最新」。用 `git ls-remote` 问远端的默认分支 HEAD，
和本地 HEAD 比 —— 一次网络往返，不需要 token，不需要 clone。

拿不到远端信息（离线、没网、仓库私有）时**不报错也不猜**，
返回 `unknown`：假装「已是最新」比说不知道更糟，人会以为自己是新的。
"""
from __future__ import annotations

import subprocess
import tomllib
from functools import lru_cache
from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent.parent
CHECK_TIMEOUT_S = 6


def _git(*args: str, timeout: int = 5) -> str:
    try:
        r = subprocess.run(["git", "-C", str(PROJECT_DIR), *args],
                           capture_output=True, text=True, timeout=timeout)
        return r.stdout.strip() if r.returncode == 0 else ""
    except (subprocess.SubprocessError, OSError):
        return ""


@lru_cache(maxsize=1)
def declared() -> str:
    """pyproject 里声明的版本号。给人看的门面，不参与新旧判断。"""
    try:
        with open(PROJECT_DIR / "pyproject.toml", "rb") as f:
            return tomllib.load(f).get("project", {}).get("version", "")
    except (OSError, ValueError):
        return ""


def local() -> dict:
    """本地版本：声明号 + commit + 描述 + 是否有未提交改动。"""
    return {
        "version": declared(),
        "commit": _git("rev-parse", "--short", "HEAD"),
        "describe": _git("describe", "--tags", "--always"),
        "date": _git("log", "-1", "--format=%cI"),
        "branch": _git("rev-parse", "--abbrev-ref", "HEAD"),
        # 有本地改动时不该提示更新 —— 一 pull 可能冲突，得他自己决定
        "dirty": bool(_git("status", "--porcelain")),
    }


def check() -> dict:
    """和远端比一比。返回 {status, behind, local, remote, hint}。

    status: latest | outdated | dirty | unknown
    """
    loc = local()
    head = _git("rev-parse", "HEAD")
    branch = loc["branch"] or "main"
    remote_line = _git("ls-remote", "origin", branch, timeout=CHECK_TIMEOUT_S)
    remote = remote_line.split()[0] if remote_line else ""

    if not remote or not head:
        return {"status": "unknown", "local": loc, "remote": "",
                "hint": "连不上远端，无法判断是不是最新（离线或仓库不可达）"}
    if remote == head:
        return {"status": "latest", "local": loc, "remote": remote[:7],
                "hint": "已是最新"}

    # 落后几个提交。本地没有远端那个对象时（没 fetch 过）算不出来，
    # 返回 0 表示「有更新但不知道差多少」，不要瞎猜一个数字。
    behind = 0
    if _git("cat-file", "-e", f"{remote}^{{commit}}") == "":
        cnt = _git("rev-list", "--count", f"HEAD..{remote}")
        behind = int(cnt) if cnt.isdigit() else 0

    if loc["dirty"]:
        return {"status": "dirty", "behind": behind, "local": loc, "remote": remote[:7],
                "hint": "有新版本，但你本地有未提交的改动 —— 先处理掉再 git pull"}
    return {"status": "outdated", "behind": behind, "local": loc, "remote": remote[:7],
            "hint": "有新版本，跑 `git pull && ./install.sh` 更新",
            "command": "git pull --ff-only && ./install.sh"}
