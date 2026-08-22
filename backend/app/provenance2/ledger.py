"""
Provenance ledger v2 (section 45).

Extends the v1 hash-chain mechanics with full reproducibility metadata per
interpretation:

    input_hash, annotation_version, model_version, model_hash,
    acmg_rule_version, knowledge_graph_version, phenotype_version,
    evidence_snapshot_hash, output_hash, timestamp, operator

Chain integrity: block_hash = SHA256(index|prev_hash|payload_hash|timestamp)
over a canonical-JSON payload; verification recomputes the entire chain.
Sensitive genomic data never enters the ledger — only hashes and versions.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import time
import uuid
from pathlib import Path
from typing import Any, Optional

DB_PATH = Path(__file__).resolve().parents[1] / "genoguide.db"
TABLE = "ledger_v2"


def _canonical(payload: dict[str, Any]) -> str:
    return json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str)


def sha256(data: str | bytes) -> str:
    if isinstance(data, str):
        data = data.encode()
    return hashlib.sha256(data).hexdigest()


def _conn() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.execute(f"""
        CREATE TABLE IF NOT EXISTS {TABLE} (
            idx INTEGER PRIMARY KEY,
            interpretation_id TEXT UNIQUE,
            payload TEXT NOT NULL,
            payload_hash TEXT NOT NULL,
            prev_hash TEXT NOT NULL,
            block_hash TEXT NOT NULL,
            timestamp REAL NOT NULL
        )""")
    return con


def record_interpretation(
    *,
    input_hash: str,
    output_hash: str,
    annotation_version: Optional[str],
    model_version: Optional[str],
    model_hash: Optional[str],
    acmg_rule_version: str,
    knowledge_graph_version: Optional[str],
    phenotype_version: Optional[str],
    evidence_snapshot: dict[str, Any],
    operator: str = "genoguide-engine",
) -> dict[str, Any]:
    interpretation_id = f"INT-{uuid.uuid4().hex[:12].upper()}"
    payload = {
        "interpretation_id": interpretation_id,
        "input_hash": input_hash,
        "output_hash": output_hash,
        "annotation_version": annotation_version,
        "model_version": model_version,
        "model_hash": model_hash,
        "acmg_rule_version": acmg_rule_version,
        "knowledge_graph_version": knowledge_graph_version,
        "phenotype_version": phenotype_version,
        "evidence_snapshot_hash": sha256(_canonical(evidence_snapshot)),
        "operator": operator,
    }
    ts = time.time()
    con = _conn()
    try:
        row = con.execute(
            f"SELECT idx, block_hash FROM {TABLE} ORDER BY idx DESC LIMIT 1").fetchone()
        idx = (row[0] + 1) if row else 0
        prev = row[1] if row else "0" * 64
        payload_hash = sha256(_canonical(payload))
        block_hash = sha256(f"{idx}|{prev}|{payload_hash}|{ts}")
        con.execute(
            f"INSERT INTO {TABLE} VALUES (?,?,?,?,?,?,?)",
            (idx, interpretation_id, _canonical(payload), payload_hash, prev, block_hash, ts))
        con.commit()
    finally:
        con.close()
    return {**payload, "tx_id": f"0x{block_hash[:24]}", "block_index": idx,
            "timestamp": ts}


def get_record(interpretation_id: str) -> Optional[dict[str, Any]]:
    con = _conn()
    try:
        row = con.execute(
            f"SELECT payload, block_hash, prev_hash, idx, timestamp FROM {TABLE} "
            "WHERE interpretation_id = ?", (interpretation_id,)).fetchone()
    finally:
        con.close()
    if not row:
        return None
    return {**json.loads(row[0]), "tx_id": f"0x{row[1][:24]}",
            "block_index": row[3], "timestamp": row[4]}


def verify_chain() -> dict[str, Any]:
    con = _conn()
    try:
        rows = con.execute(
            f"SELECT idx, payload, payload_hash, prev_hash, block_hash, timestamp "
            f"FROM {TABLE} ORDER BY idx").fetchall()
    finally:
        con.close()
    prev = "0" * 64
    for idx, payload, payload_hash, prev_hash, block_hash, ts in rows:
        if prev_hash != prev:
            return {"valid": False, "failed_at": idx, "reason": "prev_hash mismatch"}
        if sha256(_canonical(json.loads(payload))) != payload_hash:
            return {"valid": False, "failed_at": idx, "reason": "payload tampered"}
        if sha256(f"{idx}|{prev_hash}|{payload_hash}|{ts}") != block_hash:
            return {"valid": False, "failed_at": idx, "reason": "block hash mismatch"}
        prev = block_hash
    return {"valid": True, "blocks": len(rows)}


def verify_interpretation(interpretation_id: str) -> dict[str, Any]:
    rec = get_record(interpretation_id)
    if rec is None:
        return {"verified": False, "reason": "interpretation not found on ledger"}
    chain = verify_chain()
    return {"verified": chain["valid"], "chain": chain, "record": rec}


def audit_trail(limit: int = 100) -> list[dict[str, Any]]:
    con = _conn()
    try:
        rows = con.execute(
            f"SELECT idx, payload, block_hash, timestamp FROM {TABLE} "
            "ORDER BY idx DESC LIMIT ?", (limit,)).fetchall()
    finally:
        con.close()
    return [{**json.loads(p), "block_index": i, "tx_id": f"0x{h[:24]}", "timestamp": t}
            for i, p, h, t in rows]
