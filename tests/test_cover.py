#!/usr/bin/env python3
"""
封面出图的纯逻辑自检 —— `.venv/bin/python tests/test_cover.py`

只测不碰网络的两件事：比例校验、和出图后的画幅核对。
真正出图要花积分、要等几十秒、还依赖上游可用性，那不该进自动化检查。

## 为什么这两件事值得测

**比例校验**：写死枚举会把上游的能力阉掉一半 —— 中台支持任意 `W:H`
（含小数比例如 1:2.1），CLI 帮助里那个五选一只是常用值提示。这里断言的是
「常用值之外的照样放行、写错的挡住」，防的是有人图省事改回白名单。

**画幅核对**：上游**不一定按请求的比例出图**。实测过一次请求 1:2.1 却拿到方图
（同参数复测多次都是遵守的，所以是偶发 —— 也正因为偶发，人工抽查抽不到）。
拿到比例不对的图而不知情，比直接报错糟糕得多。

难点在容差：太严会把 1~2px 的正常取整报成不符，太松会放过「把长图出成方图」
那种。下面用两组真实实测数据把这条线钉住。
"""

from __future__ import annotations

import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="voxflow_cover_test_")
os.environ["VOXFLOW_HOME"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.cover import CoverError, _ratio_matches, normalize_ratio  # noqa: E402

PASSED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        raise AssertionError(f"✗ {name}" + (f" —— {detail}" if detail else ""))
    PASSED.append(name)


def test_ratio_not_a_whitelist() -> None:
    """常用值之外的比例必须放行 —— 白名单等于阉掉上游能力。"""
    for r in ("1:1", "3:4", "16:9", "1:2.1", "21:9", "5:7"):
        check(f"放行 {r}", normalize_ratio(r) == r.replace("：", ":"))
    check("全角冒号归一化", normalize_ratio("3：4") == "3:4")
    check("留空回落方图", normalize_ratio("") == "1:1")
    check("两头空格不算错", normalize_ratio("  16:9  ") == "16:9")


def test_ratio_rejects_garbage() -> None:
    """写错的要在提交时就挡住，别丢进任务队列再失败。"""
    for bad in ("方形", "16/9", "16:", ":9", "abc", "16:9:1", "-1:2"):
        try:
            normalize_ratio(bad)
        except CoverError:
            PASSED.append(f"挡住 {bad!r}")
        else:
            raise AssertionError(f"✗ 没挡住非法比例 {bad!r}")


def test_ratio_match_tolerates_rounding() -> None:
    """
    上游返回的像素常有 1~2px 偏差，那是正常取整，不该报成不符。
    这两组是真实实测值。
    """
    check("1791x1007 算 16:9", _ratio_matches("16:9", (1791, 1007)) is True)
    check("1792x1009 算 16:9", _ratio_matches("16:9", (1792, 1009)) is True)
    check("1254x1254 算 1:1", _ratio_matches("1:1", (1254, 1254)) is True)


def test_ratio_match_catches_silent_squaring() -> None:
    """
    实测过 1:2.1 被出成 1680x1680 方图。这种必须抓住 ——
    图是好图，但画幅不对，拿去当封面会被平台裁掉或留白。
    """
    check("1:2.1 出成方图算不符", _ratio_matches("1:2.1", (1680, 1680)) is False)
    check("16:9 出成方图算不符", _ratio_matches("16:9", (1024, 1024)) is False)
    check("3:4 出成 4:3 算不符", _ratio_matches("3:4", (1472, 1104)) is False)


def test_unknown_is_not_mismatch() -> None:
    """
    量不出来返回 None，不是 False。

    「不知道」和「确认不符」要采取的行动完全不同：前者是补个 Pillow，
    后者是换上游重出。混成一个布尔值，界面就只能二选一地猜。
    """
    check("量不到尺寸返回 None", _ratio_matches("1:1", None) is None)
    check("比例看不懂返回 None", _ratio_matches("方形", (100, 100)) is None)
    check("高为 0 不炸也不误判", _ratio_matches("1:1", (100, 0)) is None)


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failures = []
    for fn in tests:
        try:
            fn()
        except AssertionError as e:
            failures.append(str(e))
        except Exception as e:                                    # noqa: BLE001
            failures.append(f"✗ {fn.__name__} 抛异常: {type(e).__name__}: {e}")

    for name in PASSED:
        print(f"  ✓ {name}")
    if failures:
        print()
        for f in failures:
            print(f"  {f}")
        print(f"\n{len(PASSED)} 条通过，{len(failures)} 条失败")
        return 1
    print(f"\n全部通过（{len(PASSED)} 条断言）")
    return 0


if __name__ == "__main__":
    import shutil
    try:
        code = main()
    finally:
        shutil.rmtree(_TMP, ignore_errors=True)
    sys.exit(code)
