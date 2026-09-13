"""找外部可执行文件 —— **不要直接用 `shutil.which`**。

## 为什么

voxflow 依赖一串装在各处的命令行工具：

| 工具 | 装在哪 |
|---|---|
| `reel` `museav` `lark-cli` `npm` | mise 管理的 node：`~/.local/share/mise/installs/node/<ver>/bin/` |
| `browser-harness` `ego-browser` | `~/.local/bin/` |
| `ffmpeg` | homebrew：`/opt/homebrew/bin/` |
| `suno` | `~/.cargo/bin/`（如果还在用） |

**这些目录一个都不在最小 PATH 里**。交互式 shell 有 mise 和 homebrew 注入的
PATH，所以手动跑没问题；但后端服务、launchd、cron、`subprocess` 起的子进程
常常只有 `/usr/bin:/bin`，`shutil.which` 全部返回 None。

2026-09-13 实测：最小 PATH 下 9 个工具**一个都找不到**。而 `core/notify.py`
的 lark-cli 通道就因此**从来没生效过** —— 它静默回落到 webhook，等 webhook 的
机器人也停用了才暴露。这类故障的信号是：**某条代码路径从来没出现在日志里。**

## 怎么用

    from core.exe import find_exe
    ffmpeg = find_exe("ffmpeg") or "ffmpeg"     # 找不到就退回裸名字，让报错说人话

找不到时返回空串，**由调用方决定是报错还是降级** —— 这里不抛异常，
因为「工具没装」在不同场景下的严重程度差很多（ffmpeg 没了不能转码是硬伤，
lark-cli 没了只是通知发不出，不该中断主流程）。
"""

from __future__ import annotations

import glob
import os
import shutil
from pathlib import Path

# 按命中概率排序 —— 前面的先试，减少无谓的文件系统访问
_DIRS: tuple[str, ...] = (
    "~/.local/bin",                               # browser-harness / ego-browser / pipx
    "~/.local/share/mise/shims",                  # mise 的稳定入口：node 版本变了它还在
    "/opt/homebrew/bin",                          # Apple Silicon homebrew
    "/usr/local/bin",                             # Intel homebrew / 手装
    "~/.cargo/bin",                               # rust 装的（suno CLI）
    "/usr/bin",
)

# mise 按版本号建目录，写死版本必然随升级失效，所以这层用 glob
_GLOBS: tuple[str, ...] = (
    "~/.local/share/mise/installs/node/*/bin/{name}",
    "~/.local/share/mise/installs/*/*/bin/{name}",
    "~/.nvm/versions/node/*/bin/{name}",
)


def find_exe(name: str, extra: "tuple[str, ...] | list[str]" = ()) -> str:
    """定位一个外部命令，返回绝对路径；找不到返回空串。

    `extra` 给调用方塞自己知道的特殊位置（例如项目内的脚本），优先级仅次于 PATH。
    """
    hit = shutil.which(name)
    if hit:
        return hit

    for cand in extra:
        p = Path(cand).expanduser()
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)

    for d in _DIRS:
        p = Path(d).expanduser() / name
        if p.is_file() and os.access(p, os.X_OK):
            return str(p)

    for pattern in _GLOBS:
        hits = sorted(glob.glob(str(Path(pattern.format(name=name)).expanduser())))
        # 同一工具可能在多个 node 版本下都有，取排序最后的（通常是最新版本目录）
        for h in reversed(hits):
            if os.access(h, os.X_OK):
                return h
    return ""


def enriched_path() -> str:
    """给 subprocess 用的 PATH —— 把上面那些目录都并进当前 PATH。

    有些工具**自己还要调别的工具**（reel 调 ffmpeg、ego-browser 调 node），
    光把主程序的绝对路径传对还不够，子进程的 PATH 也得够用。
    """
    parts = [str(Path(d).expanduser()) for d in _DIRS]
    node_bins = sorted(glob.glob(str(Path("~/.local/share/mise/installs/node/*/bin").expanduser())))
    if node_bins:
        parts.insert(0, node_bins[-1])
    cur = os.environ.get("PATH", "")
    seen, out = set(), []
    for p in parts + cur.split(os.pathsep):
        if p and p not in seen:
            seen.add(p)
            out.append(p)
    return os.pathsep.join(out)


if __name__ == "__main__":
    # 自检：把项目依赖的工具挨个找一遍，顺带当成环境体检用
    for tool in ("ffmpeg", "reel", "museav", "lark-cli", "browser-harness",
                 "ego-browser", "npm", "suno", "voice"):
        p = find_exe(tool)
        print(f"  {tool:18} {p or '—— 没装'}")
