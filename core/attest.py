"""作品存证 —— 把「这首歌是我设计的」变成可验证的证据。

## 为什么需要它

AI 音乐能不能受著作权保护，法律上的关键是有没有**独创性智力投入**。
「一键随机生成」不受保护，「我设定风格、挑选版本、反复调整」才受保护。

而这份投入的证据，voxflow 本来就攒着：每首歌的 prompt、tags、生成时间、
clip_id、两个版本里选了哪个、LLM 调用流水。**别人临时补做不出来，
你已经有三百多首的留痕。** 这里做的事就是把它导成可验证的形式。

## 三层，成本依次递增（前两层为零）

1. **内容哈希**（本地，零成本）：sha256(音频) —— 证明文件此后未被篡改
2. **创作留痕**（本地，零成本）：prompt / 时间线 / 版本选择，规范化成 JSON 再哈希
3. **链上锚定**（一笔交易）：把一批作品的 Merkle root 写上链

## 为什么用 Merkle root 而不是逐首上链

逐首上链 = N 笔交易 = N 份 gas。**Merkle 树只上链一个 root，
一笔交易锚定整批**，单首成本摊到接近零；日后要证明某一首，
出示它的 Merkle proof 即可，不需要重新上链。

## 上链这步不碰私钥

`anchor_payload()` 只负责把 root 打包成一笔标准交易的 data 字段，
签名和发送由调用方拿自己的钱包做（或走 kyvault 注入）。
**这个模块里不出现任何私钥**。
"""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from core import db
from core.paths import DATA_DIR

# 留痕 JSON 的版本号。字段变了要升，否则同一首歌在不同版本下算出的哈希
# 对不上，历史存证就没法复验。
SCHEMA = "voxflow-attest/1"


def _sha256_file(path: Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(chunk):
            h.update(block)
    return h.hexdigest()


def _canonical(obj: Any) -> str:
    """规范化 JSON —— 键排序、无多余空白、非 ASCII 不转义。

    哈希必须对「同样的内容」永远得出同样的值，所以序列化方式要固定死。
    默认的 json.dumps 会因为键序或空格不同而算出不同哈希。
    """
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False)


def provenance(track_id: str) -> dict[str, Any]:
    """导出一首作品的完整创作留痕。

    这是「独创性智力投入」的证据：用了什么提示词、什么时候生成的、
    一次出的两个版本里选了哪个、后来改过什么名字。
    """
    db.init()
    with db.connect() as c:
        t = c.execute("SELECT * FROM tracks WHERE id=?", (track_id,)).fetchone()
        if not t:
            raise ValueError(f"没有这首作品: {track_id}")
        events = c.execute(
            "SELECT from_status, to_status, actor, note, ts FROM publish_events "
            "WHERE track_id=? ORDER BY ts", (track_id,)).fetchall()
        usage = c.execute(
            "SELECT ts, provider, action, credits, meta FROM usage_events "
            "WHERE track_id=? ORDER BY ts", (track_id,)).fetchall()
        # 同一次生成出的其它版本 —— 「我从两版里挑了这版」本身就是创作选择
        siblings = c.execute(
            "SELECT id, duration FROM tracks WHERE title=? AND id!=? AND date(created_at)=date(?)",
            (t["title"], track_id, t["created_at"])).fetchall()

    audio_rel = t["audio_file"] or ""
    audio_path = Path(audio_rel)
    if audio_rel and not audio_path.is_absolute():
        audio_path = DATA_DIR / audio_rel

    doc: dict[str, Any] = {
        "schema": SCHEMA,
        "track_id": track_id,
        "title": t["title"],
        "release_title": t["release_title"] or "",
        "created_at": t["created_at"],
        # —— 独创性投入的核心：提示词与风格设定 ——
        "design": {
            "prompt": t["prompt"] or "",
            "tags": t["tags"] or "",
            "lyrics": t["lyrics"] or "",
            "voice": t["voice"] or "",
        },
        # —— 生成溯源 ——
        "generation": {
            "clip_id": t["clip_id"] or "",
            "clip_ids": json.loads(t["clip_ids"] or "[]"),
            "duration_sec": t["duration"],
            "alternates_not_chosen": [
                {"clip_id": s["id"], "duration_sec": s["duration"]} for s in siblings],
        },
        # —— 内容指纹 ——
        "content": {
            "audio_file": audio_rel,
            "audio_sha256": _sha256_file(audio_path) if audio_path.is_file() else "",
            "audio_bytes": audio_path.stat().st_size if audio_path.is_file() else 0,
            "cover_file": t["cover_file"] or "",
        },
        # —— 时间线：什么时候做了什么 ——
        "timeline": [
            {"ts": e["ts"], "from": e["from_status"], "to": e["to_status"],
             "actor": e["actor"], "note": e["note"]} for e in events],
        "tooling": [
            {"ts": u["ts"], "provider": u["provider"], "action": u["action"],
             "credits": u["credits"], "meta": json.loads(u["meta"] or "{}")} for u in usage],
    }
    doc["digest"] = hashlib.sha256(_canonical(
        {k: v for k, v in doc.items() if k != "digest"}).encode()).hexdigest()
    return doc


def merkle_root(leaves: "list[str]") -> str:
    """由一组叶子哈希算 Merkle root。

    奇数个时复制最后一个凑对 —— 这是比特币用的做法，简单且确定。
    """
    if not leaves:
        raise ValueError("没有叶子节点")
    level = [bytes.fromhex(x) for x in leaves]
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        level = [hashlib.sha256(level[i] + level[i + 1]).digest()
                 for i in range(0, len(level), 2)]
    return level[0].hex()


def merkle_proof(leaves: "list[str]", index: int) -> "list[dict[str, str]]":
    """某个叶子的存在性证明 —— 日后单独验证这一首时用，不必重新上链。"""
    if not 0 <= index < len(leaves):
        raise ValueError(f"下标越界: {index}")
    level = [bytes.fromhex(x) for x in leaves]
    path: list[dict[str, str]] = []
    idx = index
    while len(level) > 1:
        if len(level) % 2:
            level.append(level[-1])
        sibling = idx ^ 1
        path.append({"side": "right" if sibling > idx else "left",
                     "hash": level[sibling].hex()})
        level = [hashlib.sha256(level[i] + level[i + 1]).digest()
                 for i in range(0, len(level), 2)]
        idx //= 2
    return path


def verify_proof(leaf: str, proof: "list[dict[str, str]]", root: str) -> bool:
    cur = bytes.fromhex(leaf)
    for step in proof:
        sib = bytes.fromhex(step["hash"])
        cur = hashlib.sha256(sib + cur if step["side"] == "left" else cur + sib).digest()
    return cur.hex() == root


def build_batch(track_ids: "list[str]") -> dict[str, Any]:
    """把一批作品打成一个可锚定的存证包。**全程本地，零成本。**"""
    docs = [provenance(t) for t in track_ids]
    leaves = [d["digest"] for d in docs]
    root = merkle_root(leaves)
    return {
        "schema": SCHEMA,
        "built_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "count": len(docs),
        "merkle_root": root,
        "items": [
            {"track_id": d["track_id"], "title": d["title"], "digest": d["digest"],
             "proof": merkle_proof(leaves, i)}
            for i, d in enumerate(docs)],
        "documents": docs,
    }


def anchor_payload(root: str, note: str = "voxflow") -> dict[str, str]:
    """把 Merkle root 打包成一笔链上交易的 data 字段。

    **这里不碰私钥、不发交易** —— 只产出 data。签名和发送由调用方用自己的
    钱包做（私钥走 kyvault 注入，别落盘）。发到哪条链也由调用方决定：
    锚定只需要一笔最便宜的转账（转给自己、金额 0），gas 在 L2 上不到一分钱，
    而这一笔锚定的是整批作品。

    典型用法（用任意 JSON-RPC 节点）：
        eth_sendRawTransaction  ← 交易里带上这段 data
    验证时任何人都能读回 data，比对 Merkle root。
    """
    payload = f"{SCHEMA}|{note}|{root}".encode()
    return {
        "merkle_root": root,
        "data_hex": "0x" + payload.hex(),
        "data_text": payload.decode(),
        "hint": "把 data_hex 放进一笔 value=0 的自转账交易；签名与发送用你自己的钱包",
    }


def save_batch(batch: dict[str, Any], out_dir: "str | Path | None" = None) -> Path:
    """存证包落盘。默认放 ~/.voxflow/attest/，文件名带 root 前缀便于对账。"""
    d = Path(out_dir) if out_dir else (DATA_DIR / "attest")
    d.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    path = d / f"attest-{stamp}-{batch['merkle_root'][:12]}.json"
    path.write_text(_canonical(batch), encoding="utf-8")
    return path


if __name__ == "__main__":
    # 自检：只用内存数据验证 Merkle 的正确性，不读库、不碰文件。
    leaves = [hashlib.sha256(f"leaf{i}".encode()).hexdigest() for i in range(5)]
    root = merkle_root(leaves)
    for i, leaf in enumerate(leaves):
        assert verify_proof(leaf, merkle_proof(leaves, i), root), f"第 {i} 个证明没过"
    assert merkle_root(leaves[:1]) == leaves[0], "单叶子时 root 就是它自己"
    assert _canonical({"b": 1, "a": 2}) == '{"a":2,"b":1}', "规范化必须键排序"
    print(f"✓ Merkle 自检通过（{len(leaves)} 个叶子，root={root[:16]}…）")
