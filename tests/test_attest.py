#!/usr/bin/env python3
"""
作品存证 —— `.venv/bin/python tests/test_attest.py`

验的是 Merkle 的正确性和留痕哈希的确定性：同样的内容必须永远算出同样的哈希，
否则历史存证没法复验。
"""

from __future__ import annotations

import hashlib
import os
import sys
import tempfile
from pathlib import Path

_TMP = tempfile.mkdtemp(prefix="voxflow_test_")
os.environ["VOXFLOW_HOME"] = _TMP
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from core import attest, db, pipeline as P  # noqa: E402

PASSED: list[str] = []


def check(name: str, cond: bool, detail: str = "") -> None:
    if not cond:
        raise AssertionError(f"✗ {name}" + (f" —— {detail}" if detail else ""))
    PASSED.append(name)


def main() -> int:
    # ── Merkle ──
    leaves = [hashlib.sha256(f"L{i}".encode()).hexdigest() for i in range(7)]  # 奇数个
    root = leaves and attest.merkle_root(leaves)
    check("奇数叶子也能算 root", bool(root))
    check("每个叶子的证明都成立",
          all(attest.verify_proof(l, attest.merkle_proof(leaves, i), root)
              for i, l in enumerate(leaves)))
    check("单叶子时 root 即自身", attest.merkle_root(leaves[:1]) == leaves[0])
    check("篡改叶子后证明失效",
          not attest.verify_proof(hashlib.sha256(b"fake").hexdigest(),
                                  attest.merkle_proof(leaves, 0), root))
    try:
        attest.merkle_root([])
        raise AssertionError("✗ 空列表本该报错")
    except ValueError:
        PASSED.append("空列表被挡")

    # ── 规范化：哈希必须与键序无关 ──
    check("规范化与键序无关",
          attest._canonical({"b": 1, "a": {"d": 4, "c": 3}})
          == attest._canonical({"a": {"c": 3, "d": 4}, "b": 1}))

    # ── 留痕 ──
    db.init()
    P.upsert("t1", title="测试曲", tags="guzheng, calm", prompt="安静的古筝",
             stage="selected", clip_id="clip-aaa")
    doc = attest.provenance("t1")
    check("留痕含设计意图", doc["design"]["tags"] == "guzheng, calm" and doc["design"]["prompt"] == "安静的古筝")
    check("留痕带 digest", len(doc["digest"]) == 64)
    check("同内容两次算出同一 digest", attest.provenance("t1")["digest"] == doc["digest"])

    # 改了设计意图，digest 必须跟着变 —— 否则留痕不可信
    P.upsert("t1", tags="guzheng, calm, rain")
    check("内容变则 digest 变", attest.provenance("t1")["digest"] != doc["digest"])

    try:
        attest.provenance("不存在")
        raise AssertionError("✗ 不存在的作品本该报错")
    except ValueError:
        PASSED.append("不存在的作品被挡")

    # ── 批次 ──
    P.upsert("t2", title="测试曲2", tags="erhu", stage="selected")
    batch = attest.build_batch(["t1", "t2"])
    check("批次数量对", batch["count"] == 2)
    check("批次内每首的证明都成立",
          all(attest.verify_proof(it["digest"], it["proof"], batch["merkle_root"])
              for it in batch["items"]))
    payload = attest.anchor_payload(batch["merkle_root"])
    check("上链 payload 带 root", batch["merkle_root"] in payload["data_text"])
    check("payload 是合法 hex", payload["data_hex"].startswith("0x")
          and bytes.fromhex(payload["data_hex"][2:]).decode() == payload["data_text"])

    for n in PASSED:
        print(f"✓ {n}")
    print(f"\n{len(PASSED)} 项通过")
    return 0


if __name__ == "__main__":
    sys.exit(main())
