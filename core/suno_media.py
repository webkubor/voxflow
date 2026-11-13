"""Suno 音频解密 —— 2026-11 起 CloudFront 直链返回的是密文。

## 为什么需要这一层

`core/suno_api.py` 的 `download()` 直接拉
`https://d2lwuy8qc234o3.cloudfront.net/1/clip/<id>.m4a`。
2026-11-13 实测：HTTP 200、3.4MB、但**首字节没有文件魔数**，
ffprobe 报 `moov atom not found` —— 因为 Suno 已经把音频改成**加密分发**：

    clip.media_urls[0].encoding == "1.0.0"

带 Authorization / Cookie / Referer / Range 都不影响，返回的永远是密文。
浏览器里能播，是因为 Suno 前端在播放前解密（前端 chunk `_next/static/.../1eqh21rsisf76.js`）。

## 解密链路（逆向自 Suno 前端 bundle，已实测跑通）

    1. POST https://suno.com/a/api/mango/rights
       body: {"content_params": {"content_id": <clip_id>, "content_type": "clip"}}
       → { key: base64, iv: base64, glt: <guest token, JWT> }

    2. gcmKey = SHA-256(glt)                       # 32 字节 → AES-GCM key
       key = AES-GCM-Decrypt(gcmKey, iv=key[0:12], aad=content_id, ct=key[12:])
       iv  = AES-GCM-Decrypt(gcmKey, iv=iv[0:12],  aad=content_id, ct=iv[12:])
       → key 是 16 字节 AES-CTR 内容密钥，iv 是 16 字节初始 counter

    3. media = CloudFront 密文
       plain = AES-CTR-Decrypt(key, counter=iv, media)   # counter 长度 128 位

**最容易踩的坑**：`additionalData` 是 **content_id**（也就是 clip_id 本身），
不是 glt，也不是 content_type。传错就 OperationError，报错信息完全不提示这点。

## 为什么走 ego-browser 而不是直接用 Python 打 API

`/a/api/mango/rights` 要 Suno 的登录态（Cookie）。直接用 Python 请求会 401。
按本项目约定，所有自动化登录态一律走 ego-browser：在已登录的 Suno 页面里
用页面自身的 fetch 调 rights 端点，拿到 key/iv/glt 后在同一个上下文里解密，
再把明文分块 base64 回传给 Python 落盘。

ego 空间本身不需要登录 Suno（注释里写过），但**解密这步需要登录态**
（rights 端点认 Cookie），所以复用「已经打开过 suno.com」的空间。
"""
from __future__ import annotations

import base64
import json
import os
import pathlib
import shutil
import subprocess
from pathlib import Path

_AUDIO_CDN = "https://d2lwuy8qc234o3.cloudfront.net/1/clip/{clip_id}.m4a"
_RIGHTS_URL = "https://suno.com/a/api/mango/rights"


class SunoMediaError(RuntimeError):
    """音频解密失败。"""


def _ego_env() -> dict:
    env = {**os.environ, "PATH": f"{Path.home()}/.local/bin:" + os.environ.get("PATH", "")}
    return env


# ego-browser 的 nodejs 脚本：在已登录的 Suno 页面里调 rights 端点，
# 解密 key/iv，再解 CloudFront 上的媒体密文，明文分块 base64 回传。
#
# 为什么分块而不是整段 base64：一首 3 分钟的歌约 3.4MB，
# 整段 base64 4.5MB 一次性塞进 console.log 会被 ego 的输出缓冲截断；
# 分块后每块 256KB，最后一行只带长度，前面的块逐行输出。
_DECRYPT_SCRIPT = """
// 复用「已经打开过 suno.com」的空间：rights 端点认 Cookie，
// 而全新 ego 空间是干净 profile，没登录就 401。
const spaces = await listTaskSpaces();
const mine = spaces.filter(s => s.ownership !== "user");

let page = null;
for (const s of mine) {
  try {
    const t = await taskSpace(s.spaceId ?? s.id);
    const pg = t.page("p1");
    const url = await pg.url();
    if (!url.includes("suno.com")) continue;
    if (await pg.evaluate(() => document.cookie.length > 0)) { page = pg; break; }
  } catch (e) { /* 空间没了/页面不可用，换下一个 */ }
}

if (!page) {
  const task = await taskSpace("suno media");
  page = task.page("p1");
  if (!(await page.url()).includes("suno.com")) {
    await page.goto("https://suno.com/library");
    await page.waitForLoadState();
  }
  await page.waitForTimeout(3000);
}

const CLIP_ID = "__CLIP_ID__";
const result = await page.evaluate(async (cid) => {
  const enc = (b64) => Uint8Array.from(atob(b64), (c) => c.charCodeAt(0));

  const rr = await fetch("https://suno.com/a/api/mango/rights", {
    method: "POST",
    credentials: "include",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ content_params: { content_id: cid, content_type: "clip" } }),
  });
  if (!rr.ok) {
    return { state: "rights-failed", status: rr.status, body: (await rr.text()).slice(0, 200) };
  }
  const d = await rr.json();
  if (!d.key || !d.iv || !d.glt) return { state: "rights-empty", keys: Object.keys(d) };

  // AES-GCM 解 key / iv。additionalData 是 content_id —— 传错会 OperationError。
  const keyRaw = await crypto.subtle.digest("SHA-256", new TextEncoder().encode(d.glt));
  const gcmKey = await crypto.subtle.importKey("raw", keyRaw, { name: "AES-GCM" }, false, ["decrypt"]);
  const gcmDec = async (b64) => {
    const buf = enc(b64);
    return new Uint8Array(await crypto.subtle.decrypt(
      { name: "AES-GCM", iv: buf.slice(0, 12), additionalData: new TextEncoder().encode(cid) },
      gcmKey, buf.slice(12)));
  };
  const key = await gcmDec(d.key);
  const iv = await gcmDec(d.iv);

  // 下 CloudFront 密文
  const ar = await fetch("https://d2lwuy8qc234o3.cloudfront.net/1/clip/" + cid + ".m4a");
  const ct = new Uint8Array(await ar.arrayBuffer());

  // AES-CTR 解密。counter 是 16 字节大端整数，从 iv 起步、每块 +1。
  // 密文不一定 16 字节对齐，所以只解对齐部分，尾巴留白（Opus 尾块无影响）。
  const blocks = Math.floor(ct.length / 16) * 16;
  const ctrKey = await crypto.subtle.importKey("raw", key, { name: "AES-CTR" }, false, ["decrypt"]);
  let acc = 0n;
  for (let k = 0; k < 16; k++) acc = (acc << 8n) | BigInt(iv[k]);
  const out = new Uint8Array(blocks);
  const BATCH = 16 * 16384;
  for (let i = 0; i < blocks; i += BATCH) {
    const ctr = new Uint8Array(16);
    let a2 = acc + BigInt(i / 16);
    for (let k = 15; k >= 0; k--) { ctr[k] = Number(a2 & 255n); a2 >>= 8n; }
    const part = ct.slice(i, Math.min(i + BATCH, blocks));
    const plain = await crypto.subtle.decrypt({ name: "AES-CTR", counter: ctr, length: 128 }, ctrKey, part);
    out.set(new Uint8Array(plain), i);
  }

  // 明文分块 base64（每块 256KB）
  const CH = 256 * 1024;
  const chunks = [];
  for (let i = 0; i < out.length; i += CH) {
    let s = "";
    const part = out.subarray(i, Math.min(i + CH, out.length));
    for (let j = 0; j < part.length; j += 8192) {
      s += String.fromCharCode.apply(null, part.subarray(j, Math.min(j + 8192, part.length)));
    }
    chunks.push(btoa(s));
  }
  return { state: "ok", len: out.length, ftyp: String.fromCharCode(...out.slice(4, 8)), chunks };
}, CLIP_ID);

if (result.state !== "ok") {
  console.log("VFDEC:" + JSON.stringify(result));
} else {
  console.log("VFDEC:" + JSON.stringify({ state: "ok", len: result.len, ftyp: result.ftyp }));
  for (const c of result.chunks) console.log("VFCHUNK:" + c);
}
"""


def download(clip_id: str, dest: "pathlib.Path | str", timeout_s: int = 300) -> int:
    """把一首歌的音频下到本地，返回字节数。

    2026-11-13 起 CloudFront 直链是密文，必须走 rights 端点换密钥后解密。
    见模块头的「解密链路」。
    """
    dest = pathlib.Path(dest)
    dest.parent.mkdir(parents=True, exist_ok=True)

    script = _DECRYPT_SCRIPT.replace("__CLIP_ID__", clip_id)
    p = subprocess.run(["ego-browser", "nodejs"], input=script, capture_output=True,
                       text=True, timeout=timeout_s, env=_ego_env())
    out = p.stdout + "\n" + p.stderr

    head = next((l for l in out.splitlines() if l.startswith("VFDEC:")), "")
    if not head:
        raise SunoMediaError(
            "ego-browser 没有回话（解密失败）：" + (p.stderr or p.stdout)[-300:])
    meta = json.loads(head[len("VFDEC:"):])
    if meta.get("state") != "ok":
        raise SunoMediaError(f"Suno 解密失败：{meta}")

    chunks = [l[len("VFCHUNK:"):] for l in out.splitlines() if l.startswith("VFCHUNK:")]
    if not chunks:
        raise SunoMediaError(f"Suno 解密没有返回音频块（len={meta.get('len')}）")

    with open(dest, "wb") as f:
        for c in chunks:
            f.write(base64.b64decode(c))
    return dest.stat().st_size


def download_plain(clip_id: str, dest: "pathlib.Path | str") -> int:
    """别名：语义更明确 —— 解出来的就是明文音频。"""
    return download(clip_id, dest)


def fetch_to_file(clip_id: str, dest: "pathlib.Path | str") -> pathlib.Path:
    """下到本地并返回路径。"""
    dest = pathlib.Path(dest)
    download(clip_id, dest)
    return dest


__all__ = ["download", "download_plain", "fetch_to_file", "SunoMediaError"]
