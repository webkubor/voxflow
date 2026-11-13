#!/usr/bin/env python3
"""
cut_bgm_30s.py — 从 Suno 完整歌曲自动切 30 秒「抓耳 BGM 候选」

## 为什么这样写

**为什么按能量结构切，而不是随机切或人工听**：BGM 候选的交付标准是
「开口即抓耳」，这件事唯一可计算的代理指标就是音频能量结构 —— 哪里有
drop、哪里节奏最稳、哪里最早进入高潮，全部写在能量包络里。随机切出来的
片段十次有九次落在前奏或间奏上，人工听一遍的成本比跑一遍分析还高。

**为什么 ffprobe/ffmpeg + numpy，而不是 librosa**：分析口径（窗长、
分辨率、dB 基准）要自己可控，而且整条链就是一次 ffmpeg 管道 + 一维数组
运算，单首 3 分钟的歌内存 ~18MB、秒级完成；拉起 librosa 整套栈只为了
一个 RMS 没有必要。numpy 在项目依赖里本来就有（librosa 带进来的）。

**为什么用单声道 22.05kHz 分析**：能量结构不在乎声场，单声道砍一半
数据；22.05kHz 的奈奎斯特上限 11kHz，对 RMS 能量完全够用（人耳对
BGM「响不响」的判断主要由中低频能量决定）。

**为什么起点对齐拍点**：mp3 是硬切，切在弱拍半途听感上「绊一下」；
切在强拍起点，听感像「音乐本来就是从这里开始的」。拍周期与相位用
短时能量自相关估计，不引入任何模型。

**为什么跳过前 8 秒**：Suno 歌曲前奏常见静默或渐入，抓耳段几乎不会
在开头；同时要求起点 ≤ 时长-30-0.3s，保证后面够切满 30 秒。

**为什么结尾做渐弱检查**：30 秒候选最后 2.5 秒若能量明显低于段均值，
说明切在了乐句收尾/渐出上，试听体验是「越来越小声然后戛然而止」。
检测到就整体前移整数拍重试。

**积分纪律**：本脚本唯一花钱的路径是 --generate（一次生成 = 2 首 =
2 首额度），只有显式传 --generate 才会调 suno_api.generate()；
--clip 只走 get_clips + download（纯只读），--input 纯本地。

**为什么交付 mp3 而不是 wav**：候选是给人试听挑选的，192k mp3 足够；
mp3 帧粒度 26ms，ffprobe 实测时长与 30s 的偏差 < 0.1s，验收以实测为准。

用法:
  ./scripts/cut_bgm_30s.py --clip <clip_id>            # 处理已有 clip（不花积分）
  ./scripts/cut_bgm_30s.py --generate --tags "..."     # 生成新歌并切（花 2 首额度）
                       [--title "..."]
  ./scripts/cut_bgm_30s.py --input /path/to/song.mp3   # 直接切本地音频（不花积分）

输出: ~/.voxflow/bgm_candidates/<clip_id>/
  candidate-1.mp3  最早能量峰 —— 开场即高潮
  candidate-2.mp3  最强 drop —— 能量跃升最大处起切
  candidate-3.mp3  最稳节奏型 —— 拍点对齐、能量最平稳
  candidates.json  起点秒 / 峰值位置 / BPM / 能量均值 / 风格判断与理由
"""
from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core.exe import find_exe  # noqa: E402
from core.paths import DATA_DIR  # noqa: E402

try:
    import numpy as np
except ImportError:
    print("❌ 需要 numpy —— 用项目 venv 跑：.venv/bin/python scripts/cut_bgm_30s.py ...",
          file=sys.stderr)
    sys.exit(2)

# ── 分析参数 ──────────────────────────────────────────────
SR = 22050        # 分析采样率（单声道）。见模块头「为什么用单声道 22.05kHz」
WIN = 4096        # 能量窗 ~186ms：盖过一两个音符时值，又不至于抹平 drop
HOP = 1024        # 步进 ~46ms：drop 定位与拍相位对齐都需要这个精度
CAND_LEN = 30.0   # 候选时长（秒）
SKIP_HEAD = 8.0   # 跳过开头秒数（前奏太长）。见模块头
MIN_GAP = 8.0     # 三个候选起点之间的最小间隔（秒），保证「起点与风格各异」
TAIL_GUARD = 2.5  # 结尾渐弱检查的窗口长度（秒）

OUT_ROOT = DATA_DIR / "bgm_candidates"


def ffmpeg() -> str:
    """ffmpeg 绝对路径。裸名字在非交互式 shell 里找不到（homebrew 不在最小 PATH）。"""
    return find_exe("ffmpeg") or "ffmpeg"


# ── 第一步：真实音频能量分析 ──────────────────────────────────
def probe_duration(path: Path) -> float:
    """ffprobe 取容器时长（秒）。ffprobe 与 ffmpeg 同装，直接用裸名回落。"""
    ffprobe = find_exe("ffprobe") or "ffprobe"
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(path)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffprobe 失败：{r.stderr.strip()[:200]}")
    return float(r.stdout.strip())


def energy_envelope(path: Path) -> tuple[np.ndarray, np.ndarray]:
    """ffmpeg 提取单声道 PCM → 滑动窗 RMS → dB 能量包络。

    返回 (t, db)：t 是每帧中心时刻（秒），db 是帧能量（10*log10 均方功率，
    相对值 —— 和 volumedetect 的 dBFS 绝对值不是一个基准，两者都存进 JSON）。
    """
    ff = ffmpeg()
    r = subprocess.run([ff, "-v", "error", "-i", str(path), "-vn", "-ac", "1",
                        "-ar", str(SR), "-f", "f32le", "pipe:1"],
                       capture_output=True)
    if r.returncode != 0:
        raise RuntimeError(f"ffmpeg 提取 PCM 失败：{r.stderr.decode()[:300]}")
    x = np.frombuffer(r.stdout, dtype="<f4").astype(np.float64)
    n = (len(x) - WIN) // HOP + 1
    if n < 10:
        raise RuntimeError(f"音频太短（{len(x)/SR:.1f}s），不够切 30 秒候选")
    frames = np.lib.stride_tricks.sliding_window_view(x, WIN)[::HOP][:n]
    # einsum 直接在视图上算平方和，不物化 n×WIN 的大临时数组
    power = np.einsum("ij,ij->i", frames, frames) / WIN
    db = 10.0 * np.log10(power + 1e-12)   # +1e-12 防 log(0)：数字静音段
    t = (np.arange(n) * HOP + WIN / 2) / SR
    return t, db


def moving_avg(x: np.ndarray, seconds: float) -> np.ndarray:
    """按秒数取整成帧数的滑动均值。边缘用卷积的 'same' 收缩 —— 我们只在
    轨道中段选点，边缘值不会被采到。"""
    k = max(1, int(round(seconds * SR / HOP)))
    if k == 1:
        return x.copy()
    return np.convolve(x, np.ones(k) / k, mode="same")


# ── 第二步：BPM 与拍相位（短时能量自相关）──────────────────────
def estimate_beat(t: np.ndarray, db: np.ndarray, lo: float, hi: float) -> tuple[float, float, float]:
    """在 [lo, hi] 区域上用能量自相关估拍周期。返回 (拍周期秒, BPM, 相关系数)。

    搜索窗 0.33~1.02s 对应 59~182 BPM，覆盖主流 BGM 节奏。自相关天然有
    半频/倍频歧义：估出来慢于 72 BPM 且半周期处相关性也够时，取半周期
    （宁可把慢歌的「乐句呼吸」折成拍，也不把 140 的舞曲对到半拍上）。
    """
    seg = (t >= lo) & (t <= hi)
    y = db[seg]
    y = y - y.mean()
    ht = HOP / SR
    lo_lag, hi_lag = int(0.33 / ht), int(1.02 / ht)
    best_lag, best_r = 0, -2.0
    for lag in range(lo_lag, min(hi_lag, len(y) - 2) + 1):
        r = float(np.corrcoef(y[:-lag], y[lag:])[0, 1])
        if r > best_r:
            best_r, best_lag = r, lag
    period = best_lag * ht
    # 半频歧义修正：相关性损失不超过 45% 才折半，否则宁可信慢的那个
    if 60.0 / period < 72.0 and best_lag // 2 >= lo_lag:
        half = best_lag // 2
        r2 = float(np.corrcoef(y[:-half], y[half:])[0, 1])
        if r2 >= 0.55 * max(best_r, 1e-9):
            period = half * ht
    return period, 60.0 / period, best_r


def beat_phase(t: np.ndarray, db: np.ndarray, period: float, lo: float, hi: float) -> float:
    """在 [lo, hi] 上找最强拍相位：phi 取遍一个拍周期内的网格，
    能量在 phi + k*period 上的总和高者为强拍相位。"""
    grid = np.arange(0.0, period, HOP / SR)
    best_phi, best_score = 0.0, -1e18
    for phi in grid:
        beats = np.arange(lo + phi % period, hi, period)
        idx = np.clip(((beats - WIN / 2 / SR) / (HOP / SR)).astype(int), 0, len(db) - 1)
        score = float(db[idx].sum())
        if score > best_score:
            best_score, best_phi = score, float(phi)
    return best_phi


def snap_to_beat(raw: float, period: float, phase: float, lo: float, hi: float) -> float:
    """把期望起点吸附到最近的强拍格点上，并夹回 [lo, hi]。"""
    s = phase + period * round((raw - phase) / period)
    if s < lo:
        s = phase + period * math.ceil((lo - phase) / period)
    if s > hi:
        s = phase + period * math.floor((hi - phase) / period)
    return min(max(s, lo), hi)


# ── 第三步：选起点 ────────────────────────────────────────
def tail_ok(t: np.ndarray, db: np.ndarray, start: float) -> bool:
    """结尾检查：候选最后 TAIL_GUARD 秒的能量不得比段均值低 4.5dB 以上
    （低太多 = 切在渐弱/收尾里）。见模块头「为什么结尾做渐弱检查」。"""
    w = db[(t >= start) & (t < start + CAND_LEN)]
    tail = db[(t >= start + CAND_LEN - TAIL_GUARD) & (t < start + CAND_LEN)]
    if len(w) < 10 or len(tail) < 3:
        return True
    return tail.mean() >= w.mean() - 4.5


def distinct(s: float, chosen: list[float]) -> bool:
    return all(abs(s - c) >= MIN_GAP for c in chosen)


def pick_candidate_1(t, db, period, phase, lo, hi):
    """候选 1「最早能量峰」：第一处持续进入高能量区（平滑能量 ≥ 全曲 P85
    且维持 1.5s 以上）的上升沿。起点回退 1 秒，让上升过程完整进入候选，
    而不是从半山腰开始。"""
    smooth = moving_avg(db, 0.35)
    thr = float(np.percentile(db, 85))
    hot = smooth >= thr
    sustain = max(1, int(round(1.5 * SR / HOP)))
    onset_i = -1
    run = 0
    for i in range(len(hot)):
        run = run + 1 if hot[i] else 0
        if run >= sustain and t[i] >= lo:
            onset_i = i - sustain + 1
            break
    if onset_i < 0:   # 整首都不够「响」的点（极端动态的歌），退而求其次取 P70
        thr = float(np.percentile(db, 70))
        hot = smooth >= thr
        run = 0
        for i in range(len(hot)):
            run = run + 1 if hot[i] else 0
            if run >= sustain and t[i] >= lo:
                onset_i = i - sustain + 1
                break
    if onset_i < 0:
        onset_i = int(np.searchsorted(t, lo))
    onset_t = float(t[onset_i])
    raw = onset_t - 1.0
    # 渐弱重试：不合格就整体前移整数拍（最多 6 次）
    for k in range(7):
        s = snap_to_beat(raw - k * period, period, phase, lo, hi)
        if tail_ok(t, db, s):
            return s, {"onset_s": onset_t, "thr_db": thr}
    return snap_to_beat(raw, period, phase, lo, hi), {"onset_s": onset_t, "thr_db": thr}


def pick_candidate_2(t, db, period, phase, lo, hi, chosen: list[float]):
    """候选 2「最强 drop」：能量包络的一阶差分（以 ±0.35s 平滑均值的差实现，
    比逐帧差分抗毛刺）在允许区间内的最大跃升处。起点压在跃升沿起跳点，
    让候选一开口就是 drop。起点与已选候选相距过近时顺延到次强的 drop。"""
    ma = moving_avg(db, 0.35)
    k = int(round(0.35 * SR / HOP))
    rise = np.full_like(db, -1e9)
    rise[k:-k] = ma[2 * k:] - ma[:-2 * k]
    order = np.argsort(rise[k:-k])[::-1] + k
    drop_i = -1
    for i in order[:60]:
        s_raw = float(t[i]) - 0.35
        if not (lo <= s_raw <= hi):
            continue
        s = snap_to_beat(s_raw, period, phase, lo, hi)
        if tail_ok(t, db, s) and distinct(s, chosen):
            drop_i = int(i)
            return s, {"drop_s": float(t[i]), "rise_db": float(rise[i])}
    # 全曲只有一处大跳变且和别的候选撞了：放宽间隔要求，取最强的那个
    i = int(order[0])
    s = snap_to_beat(float(t[i]) - 0.35, period, phase, lo, hi)
    return s, {"drop_s": float(t[i]), "rise_db": float(rise[i])}


def pick_candidate_3(t, db, period, phase, lo, hi, chosen: list[float]):
    """候选 3「最稳节奏型」：在所有强拍对齐的起点里，选 30 秒内能量
    「均值高且方差小」的（score = mean / std）—— 律动均匀、适合循环铺底。"""
    best = None
    grid = np.arange(lo, hi + 1e-6, period)
    starts = sorted({snap_to_beat(float(s), period, phase, lo, hi) for s in grid})
    for s in starts:
        if not distinct(s, chosen):
            continue
        w = db[(t >= s) & (t < s + CAND_LEN)]
        if len(w) < 10:
            continue
        score = float(w.mean()) / (float(w.std()) + 1e-6)
        if not tail_ok(t, db, s):
            score -= 5.0   # 惩罚但不一票否决：稳定段比「不渐弱」更稀缺
        if best is None or score > best[0]:
            best = (score, s, float(w.mean()), float(w.std()))
    if best is None:   # 区间太窄被 distinct 挤没了：退回中点拍
        return snap_to_beat((lo + hi) / 2, period, phase, lo, hi), {}
    return best[1], {"score": round(best[0], 1), "mean_db": round(best[2], 1),
                     "std_db": round(best[3], 1)}


# ── 第四步：切割 + 验证 ─────────────────────────────────────
def cut_clip(src: Path, start: float, dest: Path) -> None:
    """-ss 放在 -i 前：m4a/mp3 的 demuxer 级 seek 对音频是帧级精确的，
    比放 -i 后（整段解码）快一个量级，误差 < AAC/mp3 帧粒度（~26ms）。"""
    ff = ffmpeg()
    r = subprocess.run([ff, "-y", "-v", "error", "-ss", f"{start:.3f}", "-t", f"{CAND_LEN:.0f}",
                        "-i", str(src), "-vn", "-codec:a", "libmp3lame", "-b:a", "192k",
                        str(dest)], capture_output=True, text=True)
    if r.returncode != 0 or not dest.exists():
        raise RuntimeError(f"切割失败：{r.stderr.strip()[:300]}")


def verify_file(dest: Path) -> tuple[float, float, float]:
    """ffprobe 验时长 + volumedetect 验响度。返回 (实测时长, mean dBFS, max dBFS)。"""
    ffprobe = find_exe("ffprobe") or "ffprobe"
    r = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration",
                        "-of", "default=nw=1:nk=1", str(dest)], capture_output=True, text=True)
    dur = float(r.stdout.strip())
    ff = ffmpeg()
    r = subprocess.run([ff, "-v", "info", "-i", str(dest), "-af", "volumedetect",
                        "-f", "null", "-"], capture_output=True, text=True)
    mean_v = max_v = None
    for line in r.stderr.splitlines():
        if "mean_volume:" in line:
            mean_v = float(line.split("mean_volume:")[1].split("dB")[0].strip())
        elif "max_volume:" in line:
            max_v = float(line.split("max_volume:")[1].split("dB")[0].strip())
    return dur, (mean_v if mean_v is not None else -99.0), (max_v if max_v is not None else -99.0)


# ── 主流程 ────────────────────────────────────────────────
def process_source(key: str, src: Path, meta: dict) -> dict:
    """分析 → 选 3 个起点 → 切 → 逐个验证 → 写 candidates.json。"""
    out_dir = OUT_ROOT / key
    out_dir.mkdir(parents=True, exist_ok=True)

    dur = probe_duration(src)
    if dur < CAND_LEN + 1:
        raise RuntimeError(f"音频只有 {dur:.1f}s，不够 30 秒候选")
    print(f"⏱  时长 {dur:.1f}s，正在提取能量包络…")
    t, db = energy_envelope(src)

    lo = min(SKIP_HEAD, max(0.0, dur - CAND_LEN - 0.3))
    hi = max(lo, dur - CAND_LEN - 0.3)
    period, bpm, beat_r = estimate_beat(t, db, lo, min(hi, dur - 1))
    phase = beat_phase(t, db, period, lo, hi)
    peak_i = int(np.argmax(db))
    print(f"🎵 BPM≈{bpm:.1f}（拍周期 {period:.3f}s，自相关 r={beat_r:.2f}）"
          f"· 全曲能量峰值在 {t[peak_i]:.1f}s")

    chosen: list[float] = []
    s1, info1 = pick_candidate_1(t, db, period, phase, lo, hi)
    chosen.append(s1)
    s2, info2 = pick_candidate_2(t, db, period, phase, lo, hi, chosen)
    chosen.append(s2)
    s3, info3 = pick_candidate_3(t, db, period, phase, lo, hi, chosen)
    chosen.append(s3)

    starts = [s1, s2, s3]
    styles = ["早峰型 · 开场即高潮", "强 Drop 型 · 能量跃升最大处", "稳态律动型 · 拍点对齐铺底"]
    reasons = [
        f"全曲最早在 {info1['onset_s']:.1f}s 持续进入高能量区（≥P85={info1['thr_db']:.1f}dB），"
        f"起点回退 1s 对齐拍点，上升沿完整入曲；BPM≈{bpm:.0f}",
        f"{info2['drop_s']:.1f}s 处能量在 0.7s 内跃升 {info2['rise_db']:.1f}dB（全曲最大一阶差分），"
        f"起点压在跃升沿上，一开口就是爆点；BPM≈{bpm:.0f}",
        f"强拍对齐（拍周期 {period:.3f}s）且段内能量均值/方差比最高"
        f"（均值 {info3.get('mean_db', 0):.1f}dB / 标准差 {info3.get('std_db', 0):.1f}dB），"
        f"适合无缝循环铺底" + ("" if beat_r >= 0.3 else f"；⚠ 节奏自相关弱（r={beat_r:.2f}），拍点置信度低"),
    ]

    candidates = []
    print()
    for i, (s, style) in enumerate(zip(starts, styles), 1):
        dest = out_dir / f"candidate-{i}.mp3"
        cut_clip(src, s, dest)
        fdur, mean_v, max_v = verify_file(dest)
        seg = db[(t >= s) & (t < s + CAND_LEN)]
        # 段内峰值位置 = 段在全局轨道里的起始帧 + 段内 argmax（seg 可能为空，防越界）
        base_i = int(np.searchsorted(t, s))
        peak_s = float(t[min(base_i + int(np.argmax(seg)), len(t) - 1)]) if len(seg) else 0.0
        ok_dur = abs(fdur - CAND_LEN) <= 0.25
        ok_vol = mean_v > -35.0 and max_v > -20.0
        flag = "✅" if (ok_dur and ok_vol) else "❌"
        print(f"{flag} candidate-{i}.mp3  起点 {s:6.2f}s  实测 {fdur:6.2f}s  "
              f"mean {mean_v:6.1f}dBFS  max {max_v:6.1f}dBFS  · {style}")
        candidates.append({
            "file": dest.name,
            "style": style,
            "start_s": round(s, 2),
            "peak_s": round(peak_s, 2),
            "duration_s": round(fdur, 3),
            "energy_mean_db": round(float(seg.mean()), 2) if len(seg) else None,
            "energy_std_db": round(float(seg.std()), 2) if len(seg) else None,
            "mean_volume_dbfs": round(mean_v, 1),
            "max_volume_dbfs": round(max_v, 1),
            "duration_ok": ok_dur,
            "non_silent_ok": ok_vol,
            "reason": reasons[i - 1],
        })

    report = {
        "clip_key": key,
        "source_file": str(src),
        "title": meta.get("title"),
        "tags": meta.get("tags"),
        "duration_s": round(dur, 2),
        "bpm": round(bpm, 1),
        "beat_period_s": round(period, 4),
        "beat_autocorr_r": round(beat_r, 3),
        "global_peak_s": round(float(t[peak_i]), 2),
        "energy_mean_db": round(float(db.mean()), 2),
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "candidates": candidates,
    }
    (out_dir / "candidates.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(f"\n📁 输出：{out_dir}/（3 个候选 + candidates.json）")
    return report


def fetch_clip_source(clip_id: str) -> tuple[Path, dict]:
    """已有 clip：get_clips 拿元数据 + CDN 下载源音频。全程只读，不花积分。"""
    from core import suno_api
    clips = suno_api.get_clips([clip_id])
    if not clips:
        raise RuntimeError(f"Suno 库里查不到 clip {clip_id}")
    c = clips[0]
    if str(c.get("status", "")).lower() != "complete":
        raise RuntimeError(f"clip {clip_id} 状态是 {c.get('status')}（未完成），"
                           f"要等它生成完请用 --generate 流程")
    out_dir = OUT_ROOT / clip_id
    src = out_dir / "source.m4a"
    if not (src.exists() and src.stat().st_size > 0):
        print(f"⬇️  下载源音频（CDN 直链，只读）→ {src}")
        suno_api.download(clip_id, src)
    else:
        print(f"♻️  复用已下载的源音频 {src}")
    meta = {"title": c.get("title"), "tags": (c.get("metadata") or {}).get("tags")}
    return src, meta


def generate_and_cut(tags: str, title: str) -> list[dict]:
    """--generate：唯一花钱路径。一次 generate = 2 首 = 2 首额度（积分纪律上限）。"""
    from core import suno_api
    before = suno_api.credits()
    print(f"💳 生成前余额 {before['left']} · {before['plan']}")
    print(f"🚀 生成中：title={title!r} tags={tags!r}（instrumental，一次生成 2 首）…")
    clips = suno_api.generate(title, tags, instrumental=True)
    ids = [c["id"] for c in clips]
    print(f"⏳ 轮询生成完成：{ids}")
    done = suno_api.poll(ids, timeout_s=900)
    after = suno_api.credits()
    print(f"💳 生成后余额 {after['left']}（本次消耗 {before['left'] - after['left']}）")
    reports = []
    for c in done:
        if str(c.get("status", "")).lower() != "complete":
            print(f"⚠️  clip {c.get('id')} 状态 {c.get('status')}，跳过切割")
            continue
        cid = c["id"]
        src = OUT_ROOT / cid / "source.m4a"
        print(f"\n⬇️  下载 {cid} → {src}")
        suno_api.download(cid, src)
        meta = {"title": c.get("title"), "tags": (c.get("metadata") or {}).get("tags")}
        reports.append(process_source(cid, src, meta))
    return reports


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(
        description="从 Suno 完整歌曲自动切 3 个 30 秒抓耳 BGM 候选",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="示例:\n"
               "  ./scripts/cut_bgm_30s.py --clip <clip_id>\n"
               "  ./scripts/cut_bgm_30s.py --generate --tags \"lo-fi hip hop, chill, 90 BPM\" --title 午后\n"
               "  ./scripts/cut_bgm_30s.py --input ~/music/song.mp3\n")
    src = p.add_mutually_exclusive_group(required=True)
    src.add_argument("--clip", metavar="CLIP_ID", help="处理 Suno 已有的 clip（只读，不花积分）")
    src.add_argument("--generate", action="store_true",
                     help="生成一首新歌再切（唯一花积分的路径，一次 = 2 首额度）")
    src.add_argument("--input", metavar="FILE", help="直接切本地音频文件（不花积分）")
    p.add_argument("--tags", default="", help="--generate 必填：风格标签")
    p.add_argument("--title", default="", help="--generate 可选：歌名")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if args.generate and not args.tags.strip():
        print("❌ --generate 需要 --tags，例如 --tags \"lo-fi hip hop, chill, 90 BPM\"", file=sys.stderr)
        return 2

    try:
        if args.generate:
            reports = generate_and_cut(args.tags.strip(), args.title.strip() or "BGM 候选")
            if not reports:
                print("❌ 没有任何 clip 切割成功", file=sys.stderr)
                return 1
        elif args.clip:
            src, meta = fetch_clip_source(args.clip.strip())
            print(f"🎵 {(meta.get('title') or args.clip)} · tags={meta.get('tags') or '—'}")
            process_source(args.clip.strip(), src, meta)
        else:
            path = Path(args.input).expanduser()
            if not path.exists():
                print(f"❌ 文件不存在：{path}", file=sys.stderr)
                return 2
            process_source(path.stem, path, {"title": path.stem, "tags": None})
    except Exception as e:
        msg = str(e)
        # suno_api.SunoError 的 message 本来就写给人看，不要再包一层
        print(f"\n❌ {type(e).__name__}: {msg}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
