"""
可观测性与计量 —— 「刚才发生了什么」和「花了多少钱」。

## 为什么这两件事写在一个模块里

它们是同一条记录的两面。一次 Suno 生成既是一个**事件**（什么时候、成没成功、
花了多久），也是一笔**开销**（10 credits ≈ ¥0.29）。分成两套代码就要在每个
调用点写两遍，写着写着必然有一边漏掉 —— 而漏掉的那边通常是成本，
因为它不影响功能，坏了也没人报错。

## 两条存储通路，各干各的

| | 落在哪 | 回答什么 | 保留 |
|---|---|---|---|
| `log()` | `~/.voxflow/logs/*.jsonl` | 「刚才为什么失败」 | 14 天滚动 |
| `meter()` | SQLite `usage_events` | 「这首歌花了多少」 | 永久 |

日志是**时序排查**用的，按天分文件、过期删掉，不需要查询能力。
计量是**聚合对账**用的，要按作品/provider/月份 group by，必须进库。
一份数据两种用途，就该有两种存法。

## 为什么不上 Prometheus / OpenTelemetry

这是跑在你自己 Mac 上的单用户工具。装一套 exporter + 时序库 + 面板，
是为了解决「几十个实例、指标要跨机器聚合」的问题，而这里只有一个进程。
SQLite 的一句 `GROUP BY` 就是全部需求。真到了要跨机器那天再说。
"""

from __future__ import annotations

import json
import os
import threading
import time
from collections import deque
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from core.paths import DATA_DIR, find_config

LOG_DIR = DATA_DIR / "logs"

# 日志保留几天。
#
# 原来是 14 天 —— 那是「万一要翻旧账」的思路，但实际用途只有一个：
# **刚才出了问题，看看日志**。两周前的日志从来没人翻过，它只是在占地方。
#
# 定在 3 天而不是 1 天：出问题往往是隔天才发现（「昨天生成的那首怎么没了」），
# 只留当天的话，等你想起来查的时候它已经没了。3 天覆盖「昨天 + 前天」，
# 再往前确实没用过。
#
# 真要长期留的东西不在这里 —— 成本和用量在 usage_events 里，那是永久的。
LOG_RETENTION_DAYS = 3

# 请求耗时的内存环形缓冲 —— 算 P50/P95 用。
# 只留最近 1000 条：分位数是「现在快不快」的问题，不是「历史上快不快」，
# 拿三个月前的数据拉平当前的 P95 反而看不出刚刚变慢了。
_LAT_MAX = 1000
_latencies: dict[str, deque] = {}
_counters: dict[str, int] = {}
_lock = threading.Lock()
_started_at = time.time()

_pricing_cache: dict[str, Any] = {"at": 0.0, "data": None}
_PRICING_TTL = 60


# ── 单价表 ────────────────────────────────────────────────

def pricing() -> dict:
    """
    读单价表。60 秒缓存 —— 改了价不用重启，但也不至于每次调用都读盘。

    读不到就返回全 0 的骨架而不是抛异常：计量失败绝不能让业务调用失败，
    「记不了账」比「出不了歌」轻得多。
    """
    now = time.time()
    if _pricing_cache["data"] is not None and now - _pricing_cache["at"] < _PRICING_TTL:
        return _pricing_cache["data"]
    try:
        data = json.loads(find_config("pricing.json").read_text(encoding="utf-8"))
    except Exception:
        data = {"currency": "CNY", "providers": {}, "revenue": {}}
    _pricing_cache.update(at=now, data=data)
    return data


def unit_price(provider: str) -> float:
    return float((pricing().get("providers", {}).get(provider) or {}).get("cny_per_unit", 0.0))


# ── 结构化日志 ────────────────────────────────────────────

def _log_path(day: str | None = None) -> Path:
    day = day or datetime.now().strftime("%Y-%m-%d")
    return LOG_DIR / f"voxflow-{day}.jsonl"


def log(event: str, level: str = "info", **fields: Any) -> None:
    """
    记一条结构化事件。**永不抛异常** —— 日志写失败不该把业务带下水。

    用 JSONL 而不是文本行：字段名固定的话，`jq` 和前端都能直接查，
    不用为每种日志格式写一个正则。
    """
    try:
        LOG_DIR.mkdir(parents=True, exist_ok=True)
        rec = {
            "ts": datetime.now().isoformat(timespec="seconds"),
            "level": level,
            "event": event,
            **fields,
        }
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec, ensure_ascii=False) + "\n")
    except Exception:
        pass


def read_logs(limit: int = 200, level: str = "", event: str = "", days: int = 3) -> list[dict]:
    """
    倒序读最近的日志。跨天读，因为「最近 200 条」不该在零点被截断。

    从文件尾往前读（而不是全读进来再切）：日志文件一天能到几 MB，
    要的只是最后几百行。
    """
    out: list[dict] = []
    for i in range(days):
        day = (datetime.now() - timedelta(days=i)).strftime("%Y-%m-%d")
        p = _log_path(day)
        if not p.exists():
            continue
        try:
            lines = p.read_text(encoding="utf-8").splitlines()
        except Exception:
            continue
        for line in reversed(lines):
            if not line.strip():
                continue
            try:
                rec = json.loads(line)
            except Exception:
                continue
            if level and rec.get("level") != level:
                continue
            if event and event not in rec.get("event", ""):
                continue
            out.append(rec)
            if len(out) >= limit:
                return out
    return out


def prune_logs() -> int:
    """删掉过期日志。启动时跑一次即可 —— 不值得为它起定时器。"""
    n = 0
    cutoff = datetime.now() - timedelta(days=LOG_RETENTION_DAYS)
    try:
        for p in LOG_DIR.glob("voxflow-*.jsonl"):
            try:
                day = datetime.strptime(p.stem.replace("voxflow-", ""), "%Y-%m-%d")
            except ValueError:
                continue
            if day < cutoff:
                p.unlink()
                n += 1
    except Exception:
        pass
    return n


# ── 计量 ──────────────────────────────────────────────────

def meter(provider: str, action: str, *, qty: float = 1, credits: float = 0.0,
          track_id: str = "", duration_ms: int = 0, ok: bool = True,
          estimated: bool = False, **meta: Any) -> None:
    """
    记一笔开销。同样**永不抛异常**。

    `credits` 是上游积分，`cost_cny` 由当前单价换算后落盘定格 —— 见
    configs/pricing.json 里对「为什么不查询时算」的说明。

    失败的调用照样要记（`ok=False`）：Suno 生成失败一样扣积分，
    只记成功的话账永远对不上，而且「失败率 × 单价」正是最该被看见的浪费。
    """
    try:
        from core import db  # 延迟导入：obs 被 CLI 早期导入，不该拖起 sqlite
        cost = round(credits * unit_price(provider), 6) if credits else 0.0
        with db.connect() as c:
            c.execute(
                "INSERT INTO usage_events (ts, provider, action, qty, credits, cost_cny,"
                " track_id, duration_ms, ok, estimated, meta)"
                " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
                (datetime.now().isoformat(timespec="seconds"), provider, action,
                 qty, credits, cost, track_id, duration_ms, 1 if ok else 0,
                 1 if estimated else 0, json.dumps(meta, ensure_ascii=False)),
            )
        # 失败的上游调用记 error 级别 —— 它既是故障也是浪费（照样扣费），
        # 是筛 error 时最该第一个看到的东西。记成 info 的话，
        # 过滤器一开就把它藏起来了，而故障恰恰只在过滤后才有人看。
        log("usage", level="info" if ok else "error",
            provider=provider, action=action, credits=credits,
            cost_cny=cost, track_id=track_id, ok=ok, duration_ms=duration_ms,
            **({"error": str(meta.get("error", ""))[:200]} if not ok and meta.get("error") else {}))
    except Exception:
        pass


def usage_summary(days: int = 30) -> dict:
    """
    按 provider 和按天聚合最近 N 天的开销。成本看板的数据源。
    """
    from core import db
    since = (datetime.now() - timedelta(days=days)).isoformat(timespec="seconds")
    try:
        with db.connect() as c:
            by_provider = [dict(r) for r in c.execute(
                "SELECT provider, COUNT(*) n, SUM(qty) qty, SUM(credits) credits,"
                " SUM(cost_cny) cost_cny,"
                # 「省下多少」只能按**成功**的量算：失败的调用没产出任何东西，
                # 拿它去抵商业 API 的价，等于把故障算成收益。
                " SUM(CASE WHEN ok=1 THEN qty ELSE 0 END) qty_ok,"
                " SUM(CASE WHEN estimated=1 THEN cost_cny ELSE 0 END) estimated_cny,"
                " SUM(CASE WHEN ok=0 THEN 1 ELSE 0 END) failed"
                " FROM usage_events WHERE ts >= ? GROUP BY provider ORDER BY cost_cny DESC",
                (since,))]
            by_day = [dict(r) for r in c.execute(
                "SELECT substr(ts,1,10) day, SUM(cost_cny) cost_cny, COUNT(*) n"
                " FROM usage_events WHERE ts >= ? GROUP BY day ORDER BY day",
                (since,))]
            by_action = [dict(r) for r in c.execute(
                "SELECT provider, action, COUNT(*) n, SUM(cost_cny) cost_cny"
                " FROM usage_events WHERE ts >= ? GROUP BY provider, action"
                " ORDER BY cost_cny DESC LIMIT 20", (since,))]
    except Exception as e:
        return {"ok": False, "error": str(e), "total_cny": 0.0, "saved_cny": 0.0,
                "estimated_cny": 0.0,
                "currency": "CNY", "days": days,
                "by_provider": [], "by_day": [], "by_action": []}
    # 「省下了多少」—— 本地跑的量 × 对标商业 API 的单价 − 实付。
    #
    # 这个数不是营销话术，是这个工具存在的理由：本地 TTS 那一栏实付永远是 0，
    # 不把等价市场价算出来，用户对「省了钱」这件事没有任何感知 ——
    # 免费的东西最容易被当成不值钱。
    prov_cfg = pricing().get("providers", {})
    saved = 0.0
    for r in by_provider:
        mkt = float((prov_cfg.get(r["provider"]) or {}).get("market_cny_per_unit", 0))
        if mkt > 0:
            r["market_cny"] = round((r["qty_ok"] or 0) * mkt, 2)
            r["saved_cny"] = round(max(0.0, r["market_cny"] - (r["cost_cny"] or 0)), 2)
            saved += r["saved_cny"]
        else:
            r["market_cny"] = 0.0
            r["saved_cny"] = 0.0
    total = round(sum(r["cost_cny"] or 0 for r in by_provider), 2)
    est_total = round(sum(r.get("estimated_cny") or 0 for r in by_provider), 2)
    return {"ok": True, "days": days, "total_cny": total, "currency": "CNY",
            "saved_cny": round(saved, 2),
            # 总额里有多少是估算出来的。界面要能说「¥X 中有 ¥Y 是估的」——
            # 不区分的话，回填一次历史数据就再也分不清哪些数字可信。
            "estimated_cny": est_total,
            "by_provider": by_provider, "by_day": by_day, "by_action": by_action}


def track_costs(track_ids: list[str] | None = None) -> dict[str, dict]:
    """
    每首歌的成本明细。**单位经济学的核心** —— 没有它就只知道总共烧了多少，
    不知道哪首歌贵、贵在哪一步。
    """
    from core import db
    try:
        with db.connect() as c:
            if track_ids:
                ph = ",".join("?" * len(track_ids))
                rows = c.execute(
                    f"SELECT track_id, provider, SUM(credits) credits, SUM(cost_cny) cost_cny,"
                    f" COUNT(*) n FROM usage_events WHERE track_id IN ({ph})"
                    f" GROUP BY track_id, provider", track_ids).fetchall()
            else:
                rows = c.execute(
                    "SELECT track_id, provider, SUM(credits) credits, SUM(cost_cny) cost_cny,"
                    " COUNT(*) n FROM usage_events WHERE track_id != ''"
                    " GROUP BY track_id, provider").fetchall()
    except Exception:
        return {}
    out: dict[str, dict] = {}
    for r in rows:
        t = out.setdefault(r["track_id"], {"total_cny": 0.0, "by_provider": {}})
        t["by_provider"][r["provider"]] = {
            "credits": r["credits"] or 0, "cost_cny": round(r["cost_cny"] or 0, 4), "n": r["n"]}
        t["total_cny"] = round(t["total_cny"] + (r["cost_cny"] or 0), 4)
    return out


# ── 收入侧 ────────────────────────────────────────────────

def _parse_cn_number(v: object) -> float:
    """
    解析平台后台那种中文缩写数字：'3.4w' → 34000、'1.2万' → 12000、'567' → 567。

    平台自己就是这么显示的，抓下来是什么样就存什么样（原样存是对的 ——
    改写会让「台账和后台对不上」变得无法排查）。转换放在读取侧。
    """
    if isinstance(v, (int, float)):
        return float(v)
    t = str(v or "").strip().replace(",", "")
    if not t:
        return 0.0
    mult = 1.0
    for suf, m in (("亿", 1e8), ("万", 1e4), ("w", 1e4), ("W", 1e4), ("k", 1e3), ("K", 1e3)):
        if t.endswith(suf):
            t, mult = t[: -len(suf)], m
            break
    try:
        return float(t) * mult
    except ValueError:
        return 0.0


def platform_revenue() -> dict:
    """
    各平台的真实收益与播放量，并**用实测数据反推真实千播单价**。

    为什么这一步很重要：`configs/pricing.json` 里的分成率是从公开资料抄的
    区间中位数（网易云「0.2–0.4 元/千播」取 0.3）。而后台同时给了累计播放量
    和可提现金额 —— 两个数一除就是**这个账号实际拿到的单价**，
    比任何公开资料都准，因为它已经包含了这个账号的实际权益档位。

    实测值只在两个数都有时才给，并标明 measured；否则退回配置里的估算值
    并标明 configured。**哪来的数一定要写清楚**，否则过一阵子没人分得清
    看到的是实测还是猜测，而这两者的决策价值完全不同。
    """
    from core import db
    rev_cfg = pricing().get("revenue", {})
    out: dict[str, dict] = {}
    try:
        with db.connect() as c:
            rows = c.execute(
                "SELECT platform, artist_name, song_count, stats FROM platform_accounts"
            ).fetchall()
    except Exception:
        return out

    for r in rows:
        try:
            st = json.loads(r["stats"] or "{}")
        except Exception:
            st = {}
        plays = _parse_cn_number(st.get("play_count"))
        earned = _parse_cn_number(st.get("withdrawable_cny"))
        cfg = rev_cfg.get(r["platform"]) or {}

        if plays > 0 and earned > 0:
            rate, source = round(earned / plays * 1000, 4), "measured"
        else:
            rate, source = float(cfg.get("cny_per_1k_plays", 0)), "configured"

        out[r["platform"]] = {
            "label": cfg.get("label", r["platform"]),
            "artist": r["artist_name"],
            "songs": r["song_count"],
            "plays": int(plays),
            "earned_cny": round(earned, 2),
            "cny_per_1k_plays": rate,
            "rate_source": source,
            "plays_7d": int(_parse_cn_number(st.get("play_7d"))),
            "fans": int(_parse_cn_number(st.get("fans"))),
            "synced_at": st.get("synced_at", ""),
        }
    return out


def track_revenue() -> dict[str, dict]:
    """
    每首歌**实际**赚了多少、被播了多少次。

    数据来自音乐人后台（`scripts/ncm_track_stats.py` 写进 track_platforms），
    公开 API 给不了 —— 网易云的 `playedNum` 恒为 0（2026-09-05 实测两个端点）。

    **没有数据就返回空，不做按比例分摊。** 用账号总收益按播放占比摊到单曲，
    算出来的数字看着很合理，但它其实只是「总收益 ÷ 首数」的变体，
    完全无法回答「哪首歌值得再做一首同风格的」—— 而那正是要它的唯一理由。
    一个能误导选题的数字，比没有数字糟得多。
    """
    from core import db
    out: dict[str, dict] = {}
    try:
        with db.connect() as c:
            rows = c.execute(
                "SELECT track_id, platform, plays, earned_cny, stats_at"
                " FROM track_platforms WHERE plays > 0 OR earned_cny > 0"
            ).fetchall()
    except Exception:
        return out
    for r in rows:
        t = out.setdefault(r["track_id"], {"plays": 0, "earned_cny": 0.0, "by_platform": {}})
        t["by_platform"][r["platform"]] = {
            "plays": r["plays"] or 0,
            "earned_cny": round(r["earned_cny"] or 0, 4),
            "stats_at": r["stats_at"] or "",
        }
        t["plays"] += r["plays"] or 0
        t["earned_cny"] = round(t["earned_cny"] + (r["earned_cny"] or 0), 4)
    return out


def breakeven_plays(cost_cny: float, platform: str = "qishui",
                    rate_override: float | None = None) -> int:
    """
    回本需要多少播放量。成本 ÷ 千播分成 × 1000。

    分成率未证实的平台（配置里 cny_per_1k_plays = 0）返回 0 表示「算不了」，
    而不是拿一个猜的数算出个像模像样的结果 —— 那种数字会被当真。

    `rate_override` 用来传实测单价（见 platform_revenue）：后台的累计播放量
    和可提现金额一除就是这个账号真拿到的单价，比公开资料的区间中位数准。
    """
    rate = float((pricing().get("revenue", {}).get(platform) or {}).get("cny_per_1k_plays", 0))
    if rate_override is not None:
        rate = rate_override
    if rate <= 0 or cost_cny <= 0:
        return 0
    return int(cost_cny / rate * 1000)


# ── 运行时指标 ────────────────────────────────────────────

def record_latency(key: str, ms: float, ok: bool = True) -> None:
    with _lock:
        d = _latencies.setdefault(key, deque(maxlen=_LAT_MAX))
        d.append(ms)
        _counters[f"{key}.n"] = _counters.get(f"{key}.n", 0) + 1
        if not ok:
            _counters[f"{key}.err"] = _counters.get(f"{key}.err", 0) + 1


def _pct(vals: list[float], p: float) -> float:
    if not vals:
        return 0.0
    s = sorted(vals)
    return round(s[min(len(s) - 1, int(len(s) * p))], 1)


def metrics() -> dict:
    """进程级指标快照：正常运行时长、各端点的量/错误率/分位耗时。"""
    with _lock:
        keys = list(_latencies.keys())
        snap = {k: list(v) for k, v in _latencies.items()}
        counters = dict(_counters)
    routes = []
    for k in keys:
        vals = snap[k]
        n = counters.get(f"{k}.n", len(vals))
        err = counters.get(f"{k}.err", 0)
        routes.append({
            "key": k, "n": n, "errors": err,
            "error_rate": round(err / n, 4) if n else 0.0,
            "p50_ms": _pct(vals, 0.5), "p95_ms": _pct(vals, 0.95),
            "max_ms": round(max(vals), 1) if vals else 0.0,
        })
    routes.sort(key=lambda r: -r["n"])
    return {
        "uptime_s": int(time.time() - _started_at),
        "started_at": datetime.fromtimestamp(_started_at).isoformat(timespec="seconds"),
        "pid": os.getpid(),
        "routes": routes[:40],
    }
