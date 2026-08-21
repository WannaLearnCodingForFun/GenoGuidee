"""
Local smart-contract-compatible provenance ledger.

Design mirrors a Hyperledger Fabric chaincode interface (ConsentContract /
InterpretationContract) but runs as a deterministic, hash-chained SQLite
ledger so the demo works fully offline. Every block commits to the previous
block's hash — tampering with any record breaks verification of all
subsequent blocks.

PRIVACY INVARIANT: no genomic data, no phenotypes, no clinical text is ever
stored on the ledger. Only SHA-256 hashes, consent state, timestamps,
model/evidence versions and provenance metadata.
"""
from __future__ import annotations

import hashlib
import json
import sqlite3
import threading
import time
from typing import Any

from .config import (
    CONTRACT_CONSENT,
    CONTRACT_INTERPRETATION,
    DB_PATH,
    EVIDENCE_VERSION,
    LEDGER_CHANNEL,
    MODEL_VERSION,
)

_lock = threading.Lock()
GENESIS_HASH = "0" * 64


def _sha256(payload: str) -> str:
    return hashlib.sha256(payload.encode()).hexdigest()


def _canonical(obj: dict[str, Any]) -> str:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"))


def _conn() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_ledger() -> None:
    with _lock, _conn() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS ledger (
                block_index INTEGER PRIMARY KEY,
                tx_id TEXT NOT NULL UNIQUE,
                contract TEXT NOT NULL,
                function TEXT NOT NULL,
                subject_id TEXT NOT NULL,
                payload TEXT NOT NULL,
                payload_hash TEXT NOT NULL,
                prev_hash TEXT NOT NULL,
                block_hash TEXT NOT NULL,
                timestamp REAL NOT NULL
            )
        """)


def _append_block(contract: str, function: str, subject_id: str, payload: dict[str, Any]) -> dict[str, Any]:
    with _lock, _conn() as conn:
        row = conn.execute("SELECT block_index, block_hash FROM ledger ORDER BY block_index DESC LIMIT 1").fetchone()
        prev_hash = row["block_hash"] if row else GENESIS_HASH
        index = (row["block_index"] + 1) if row else 0
        ts = time.time()
        payload_json = _canonical(payload)
        payload_hash = _sha256(payload_json)
        block_hash = _sha256(f"{index}|{prev_hash}|{contract}|{function}|{subject_id}|{payload_hash}|{ts:.6f}")
        tx_id = "0x" + _sha256(f"tx|{block_hash}")[:40]
        conn.execute(
            "INSERT INTO ledger VALUES (?,?,?,?,?,?,?,?,?,?)",
            (index, tx_id, contract, function, subject_id, payload_json, payload_hash, prev_hash, block_hash, ts),
        )
        return _block_dict(index, tx_id, contract, function, subject_id, payload, payload_hash, prev_hash, block_hash, ts)


def _block_dict(index, tx_id, contract, function, subject_id, payload, payload_hash, prev_hash, block_hash, ts) -> dict[str, Any]:
    return {
        "block_index": index,
        "tx_id": tx_id,
        "contract": contract,
        "function": function,
        "subject_id": subject_id,
        "payload": payload,
        "payload_hash": payload_hash,
        "prev_hash": prev_hash,
        "block_hash": block_hash,
        "timestamp": ts,
        "channel": LEDGER_CHANNEL,
    }


def _rows_to_blocks(rows) -> list[dict[str, Any]]:
    return [
        _block_dict(
            r["block_index"], r["tx_id"], r["contract"], r["function"], r["subject_id"],
            json.loads(r["payload"]), r["payload_hash"], r["prev_hash"], r["block_hash"], r["timestamp"],
        )
        for r in rows
    ]

# ---------------------------------------------------------------------------
# Contract functions (chaincode-equivalent interface)
# ---------------------------------------------------------------------------

def patient_hash(patient_id: str) -> str:
    return _sha256(f"genoguide-patient|{patient_id}")


def record_consent(patient_id: str, scope: str) -> dict[str, Any]:
    consent_hash = _sha256(f"consent|{patient_id}|{scope}")
    return _append_block(CONTRACT_CONSENT, "recordConsent", patient_id, {
        "patient_hash": patient_hash(patient_id),
        "consent_hash": consent_hash,
        "scope_hash": _sha256(scope),
        "scope_label": scope,  # human-readable scope label only; no clinical data
        "state": "GRANTED",
    })


def verify_consent(patient_id: str) -> dict[str, Any]:
    with _lock, _conn() as conn:
        rows = conn.execute(
            "SELECT * FROM ledger WHERE contract=? AND subject_id=? ORDER BY block_index",
            (CONTRACT_CONSENT, patient_id),
        ).fetchall()
    blocks = _rows_to_blocks(rows)
    state = "NOT_FOUND"
    latest = None
    for b in blocks:
        if b["function"] in ("recordConsent", "revokeConsent"):
            state = b["payload"]["state"]
            latest = b
    return {"patient_id": patient_id, "state": state, "record": latest, "history_length": len(blocks)}


def revoke_consent(patient_id: str) -> dict[str, Any]:
    return _append_block(CONTRACT_CONSENT, "revokeConsent", patient_id, {
        "patient_hash": patient_hash(patient_id),
        "state": "REVOKED",
    })


def record_interpretation(
    patient_id: str, variant_id: str, variant_label: str, classification: str,
    reconciliation_status: str, acmg_criteria: list[str], ml_top_class: str,
) -> dict[str, Any]:
    interpretation_payload = {
        "variant_id": variant_id,
        "variant_label": variant_label,
        "classification": classification,
        "reconciliation_status": reconciliation_status,
        "acmg_criteria": acmg_criteria,
        "ml_top_class": ml_top_class,
        "model_version": MODEL_VERSION,
        "evidence_version": EVIDENCE_VERSION,
    }
    interpretation_hash = _sha256(_canonical(interpretation_payload))
    return _append_block(CONTRACT_INTERPRETATION, "recordInterpretation", patient_id, {
        "patient_hash": patient_hash(patient_id),
        "variant_ref": f"{variant_label}",
        "classification": classification,
        "reconciliation_status": reconciliation_status,
        "interpretation_hash": interpretation_hash,
        "model_version": MODEL_VERSION,
        "evidence_version": EVIDENCE_VERSION,
    })


def verify_interpretation(tx_id: str) -> dict[str, Any]:
    """Recompute the full hash chain up to and including this transaction."""
    with _lock, _conn() as conn:
        rows = conn.execute("SELECT * FROM ledger ORDER BY block_index").fetchall()
    blocks = _rows_to_blocks(rows)
    target = next((b for b in blocks if b["tx_id"] == tx_id), None)
    if target is None:
        return {"verified": False, "status": "NOT_FOUND", "tx_id": tx_id, "checks": []}

    checks = []
    prev_hash = GENESIS_HASH
    verified = True
    for b in blocks:
        recomputed_payload = _sha256(_canonical(b["payload"]))
        recomputed_block = _sha256(
            f"{b['block_index']}|{prev_hash}|{b['contract']}|{b['function']}|{b['subject_id']}|{recomputed_payload}|{b['timestamp']:.6f}"
        )
        ok = (recomputed_payload == b["payload_hash"] and recomputed_block == b["block_hash"] and prev_hash == b["prev_hash"])
        if b["block_index"] <= target["block_index"]:
            checks.append({"block_index": b["block_index"], "tx_id": b["tx_id"], "intact": ok})
            verified = verified and ok
        prev_hash = b["block_hash"]
        if b["block_index"] == target["block_index"]:
            break
    return {
        "verified": verified,
        "status": "VERIFIED" if verified else "TAMPERED",
        "tx_id": tx_id,
        "record": target,
        "checks": checks,
        "chain_depth": len(checks),
    }


def get_audit_trail(patient_id: str | None = None) -> list[dict[str, Any]]:
    with _lock, _conn() as conn:
        if patient_id:
            rows = conn.execute(
                "SELECT * FROM ledger WHERE subject_id=? ORDER BY block_index", (patient_id,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM ledger ORDER BY block_index").fetchall()
    return _rows_to_blocks(rows)


def ledger_stats() -> dict[str, Any]:
    with _lock, _conn() as conn:
        total = conn.execute("SELECT COUNT(*) c FROM ledger").fetchone()["c"]
        interp = conn.execute(
            "SELECT COUNT(*) c FROM ledger WHERE function='recordInterpretation'"
        ).fetchone()["c"]
    return {"total_blocks": total, "interpretations_recorded": interp, "channel": LEDGER_CHANNEL}
