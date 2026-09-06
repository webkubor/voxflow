#!/usr/bin/env python3
"""
计量与可观测性的自检 —— `.venv/bin/python tests/test_obs.py`

## 为什么偏偏是这个模块要测

其它模块出 bug 会报错、会白屏，有人管。**算钱的模块出 bug 不报错**：
单价乘错一位、失败的调用被算成收益、改价把历史账目一起改掉 ——
每一个都会安安静静地输出一个看起来很合理的数字，然后被拿去做决策。

所以这里断言的不是「函数能跑」，是**五条不能被后来的改动破坏的性质**：

1. 成本按写入时的单价定格，改价不回溯历史
2. 失败的调用要计数，但不能算进「省下的钱」
3. 分成率未证实的平台不给回本估算（不拿猜的数充数）
4. 日志级别过滤真的过滤
5. 运营台每首歌必须带发布平台（有上架记录就算没成本也要出现）

## 为什么不用 pytest

项目没有测试依赖，为跑四个断言装一套框架不划算。裸 assert + 一个
`main()` 就够了，`python tests/test_obs.py` 直接跑，CI 里也是这一行。
真到了要参数化、要 fixture 的规模再换。
"""

from __future__ import annotations

import json
import os
import sys
import tempfile
from pathlib import Path

# 必须在 import core.* 之前设置 —— core/paths.py 在导入时就读这个变量决定数据根。
# 不隔离的话，跑一次测试就往真实的 ~/.voxflow/voxflow.db 里塞假账目，
# 而假账目和真账目混在一起之后是分不开的。
_TMP = tempfile.mkdtemp(prefix="voxflow_test_")
os.environ["VOXFLOW_HOME"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import db, obs  # noqa: E402

PASSED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        raise AssertionError(f"✗ {name}" + (f" —— {detail}" if detail else ""))
    PASSED.append(name)


def _reset() -> None:
    db.init()
    with db.connect() as c:
        c.execute("DELETE FROM usage_events")
    obs._pricing_cache.update(at=0.0, data=None)   # 强制重读单价


def _write_pricing(suno_rate: float) -> None:
    """写一份测试用单价表到数据目录（find_config 优先读它）。"""
    cfg = Path(_TMP) / "configs"
    cfg.mkdir(parents=True, exist_ok=True)
    (cfg / "pricing.json").write_text(json.dumps({
        "currency": "CNY",
        "providers": {
            "suno": {"label": "Suno", "unit": "credits", "cny_per_unit": suno_rate},
            "tts": {"label": "本地 TTS", "unit": "seconds", "cny_per_unit": 0.0,
                    "market_cny_per_unit": 0.002},
        },
        "revenue": {
            "qishui": {"label": "汽水", "cny_per_1k_plays": 1.0, "confidence": "range"},
            "tencent": {"label": "腾讯系", "cny_per_1k_plays": 0.0, "confidence": "unknown"},
        },
    }, ensure_ascii=False), encoding="utf-8")
    obs._pricing_cache.update(at=0.0, data=None)


def test_cost_is_frozen_at_write_time() -> None:
    """改单价不能回溯改写历史成本 —— 否则调一次价，过去半年的账全变了。"""
    _reset()
    _write_pricing(0.03)
    obs.meter("suno", "generate", credits=10, track_id="t1")

    _write_pricing(0.30)                       # 单价涨十倍
    obs.meter("suno", "generate", credits=10, track_id="t2")

    costs = obs.track_costs(["t1", "t2"])
    check("旧成本按当时单价定格",
          abs(costs["t1"]["total_cny"] - 0.30) < 1e-6,
          f"期望 0.30，实得 {costs['t1']['total_cny']}")
    check("新成本按新单价计算",
          abs(costs["t2"]["total_cny"] - 3.00) < 1e-6,
          f"期望 3.00，实得 {costs['t2']['total_cny']}")


def test_failed_calls_counted_but_not_credited() -> None:
    """失败要计数（它确实发生了、可能扣了费），但不能算成「省下的钱」。"""
    _reset()
    _write_pricing(0.03)
    obs.meter("tts", "clone", qty=100, credits=0, ok=True)
    obs.meter("tts", "clone", qty=100, credits=0, ok=False)

    s = obs.usage_summary(30)
    row = next(r for r in s["by_provider"] if r["provider"] == "tts")
    check("失败次数被记录", row["failed"] == 1, f"failed={row['failed']}")
    check("总调用数含失败", row["n"] == 2, f"n={row['n']}")
    check("省下的钱只按成功的量算",
          abs(row["market_cny"] - 0.20) < 1e-6,
          f"期望 0.20（只算成功那 100 秒），实得 {row['market_cny']}")


def test_unknown_revenue_rate_returns_zero() -> None:
    """分成率没证实的平台，宁可算不出，也不拿一个猜的数糊弄过去。"""
    _write_pricing(0.03)
    check("已知分成率能算回本", obs.breakeven_plays(1.0, "qishui") == 1000)
    check("未知分成率返回 0（表示算不了）", obs.breakeven_plays(1.0, "tencent") == 0)
    check("零成本不产生回本估算", obs.breakeven_plays(0.0, "qishui") == 0)


def test_log_level_filter() -> None:
    """筛 error 时必须真的只剩 error —— 否则故障会被淹在 info 里。"""
    obs.log("t_ok", level="info", note="fine")
    obs.log("t_bad", level="error", note="broken")
    errs = obs.read_logs(limit=50, level="error", days=1)
    check("error 过滤有结果", any(r["event"] == "t_bad" for r in errs))
    check("error 过滤排除了 info", all(r["level"] == "error" for r in errs))


def test_meter_never_raises() -> None:
    """
    计量失败绝不能把业务带下水 —— 「记不了账」比「出不了歌」轻得多。
    这里故意喂一个不可序列化的对象，meter 必须自己吞掉。
    """
    obs.meter("suno", "generate", credits=1, meta_obj=object())   # 不可 JSON 序列化
    check("meter 遇到坏数据不抛异常", True)


def test_economics_exposes_release_platform() -> None:
    """
    运营台每首歌必须带发布平台。

    以前 /api/economics 只拼成本和收入，表上只有作品名，看不出投到哪。
    有上架记录的歌就算没记过成本，也得出现在这本账里。
    """
    _reset()
    from core import pipeline as P
    P.upsert("clip-snow", title="落雪", stage="selected", clip_id="c1")
    P.submit_release("clip-snow", "qishui", "落雪")
    P.set_platform_status("clip-snow", "qishui", "online",
                          song_id="qs1", platform_title="落雪")
    P.set_platform_status("clip-snow", "netease", "online",
                          song_id="ne1", platform_title="落雪")
    obs.meter("suno", "generate", credits=10, track_id="clip-snow")

    P.upsert("clip-unreleased", title="未发出", stage="generated", clip_id="c2")
    obs.meter("suno", "generate", credits=10, track_id="clip-unreleased")

    # 没记过成本、但已经在平台上的历史作品 —— 旧口径会从账上消失。
    P.upsert("hist-1", title="旧曲", stage="published")
    P.submit_release("hist-1", "netease", "旧曲")
    P.set_platform_status("hist-1", "netease", "online",
                          song_id="ne-old", platform_title="旧曲")

    from web.app import economics
    by_id = {t["track_id"]: t for t in economics(30)["tracks"]}

    snow = by_id["clip-snow"]
    check("已发行的歌带独家平台", snow["release_platform"] == "qishui")
    check("已发行的歌带回发行歌名", snow["release_title"] == "落雪")
    plats = {p["platform"] for p in snow["platforms"]}
    check("已发行的歌带全部上架平台", plats == {"qishui", "netease"}, str(plats))

    unrel = by_id["clip-unreleased"]
    check("未发行的歌平台列表为空", unrel["platforms"] == [])
    check("未发行的歌没有独家平台", unrel["release_platform"] == "")

    hist = by_id["hist-1"]
    check("没成本的已上架作品也在账上", hist["release_platform"] == "netease")
    hist_plats = {p["platform"] for p in hist["platforms"]}
    check("没成本的已上架作品带平台", hist_plats == {"netease"}, str(hist["platforms"]))


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
