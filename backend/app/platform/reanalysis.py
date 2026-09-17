"""Pluggable reanalysis. Official APIs/downloads only. Never auto-finalizes."""
from __future__ import annotations

import hashlib
import uuid
from pathlib import Path
from typing import Any, Optional

from . import store
from .watchlist import mark_triggered

REPO = Path(__file__).resolve().parents[3]
RECEIPT_DIRS = {
    "ClinVar": REPO / "research/data/raw/clinvar/DATASET_INFO.json",
    "ClinGen": REPO / "research/data/raw/clingen/DATASET_INFO.json",
    "gnomAD": REPO / "research/data/raw/gnomad_constraint/DATASET_INFO.json",
    "HPO": REPO / "research/data/raw/hpo/DATASET_INFO.json",
    "MONDO": None,  # not bundled; connector only
    "literature": None,
    "guidelines": REPO / "configs/clingen",
}


def _fingerprint(path: Optional[Path]) -> Optional[dict[str, Any]]:
    if path is None:
        return {"status": "SOURCE_NOT_CONFIGURED"}
    if path.is_dir():
        parts = []
        for p in sorted(path.glob("*"))[:50]:
            if p.is_file():
                parts.append(f"{p.name}:{p.stat().st_mtime_ns}:{p.stat().st_size}")
        raw = "|".join(parts).encode()
        return {"status": "AVAILABLE", "fingerprint": hashlib.sha256(raw).hexdigest()[:32],
                "path": str(path)}
    if not path.exists():
        return {"status": "SOURCE_NOT_CONFIGURED"}
    st = path.stat()
    digest = hashlib.sha256(f"{path}:{st.st_mtime_ns}:{st.st_size}".encode()).hexdigest()[:32]
    version = None
    if path.suffix == ".json":
        try:
            import json
            data = json.loads(path.read_text())
            version = data.get("version") or data.get("dataset") or data.get("download_date")
        except (OSError, ValueError):
            version = None
    return {"status": "AVAILABLE", "fingerprint": digest, "version": version, "path": str(path)}


def current_sources() -> dict[str, Any]:
    out = {}
    for name, path in RECEIPT_DIRS.items():
        out[name] = _fingerprint(path)
    return out


def check() -> dict[str, Any]:
    current = current_sources()
    changes = []
    for name, meta in current.items():
        fp = (meta or {}).get("fingerprint")
        row = store.execute(
            "SELECT version, fingerprint FROM evidence_source_versions WHERE source=?",
            (name,), fetch="one",
        )
        prev = row[1] if row else None
        if fp and fp != prev:
            changes.append({
                "source": name,
                "previous_fingerprint": prev,
                "current_fingerprint": fp,
                "version": (meta or {}).get("version"),
            })
    return {"sources": current, "changes": changes, "changed": bool(changes)}


def run(operator: str = "reanalysis-engine") -> dict[str, Any]:
    job_id = f"RA-{uuid.uuid4().hex[:10].upper()}"
    store.execute(
        "INSERT INTO reanalysis_jobs (job_id, status, created_at, payload_json) VALUES (?,?,?,?)",
        (job_id, "RUNNING", store.now(), store.dumps({"operator": operator})),
    )
    report = check()
    current = report["sources"]
    for name, meta in current.items():
        store.execute(
            """INSERT INTO evidence_source_versions (source, version, fingerprint, metadata_json, checked_at)
               VALUES (?,?,?,?,?)
               ON CONFLICT(source) DO UPDATE SET
                 version=excluded.version, fingerprint=excluded.fingerprint,
                 metadata_json=excluded.metadata_json, checked_at=excluded.checked_at""",
            (name, (meta or {}).get("version"), (meta or {}).get("fingerprint"),
             store.dumps(meta), store.now()),
        )
    rows = store.execute(
        "SELECT DISTINCT interpretation_id, variant_id, classification FROM interpretation_versions",
        fetch="all",
    ) or []
    change_records = []
    for iid, vid, classification in rows:
        payload = {
            "interpretation_id": iid,
            "variant_id": vid,
            "classification_before": classification,
            "classification_after": classification,  # never auto-change
            "source_changes": report["changes"],
            "review_required": bool(report["changes"]),
        }
        store.execute(
            """INSERT INTO reanalysis_changes
               (job_id, variant_id, interpretation_id, change_type, payload_json, created_at)
               VALUES (?,?,?,?,?,?)""",
            (job_id, vid, iid, "EVIDENCE_SOURCE_UPDATE" if report["changes"] else "NO_CHANGE",
             store.dumps(payload), store.now()),
        )
        change_records.append(payload)
        if report["changes"] and vid:
            mark_triggered(vid, reason="WATCH TRIGGERED", evidence_change=store.dumps(report["changes"]),
                           classification_before=classification, classification_after=classification)
    store.execute(
        "UPDATE reanalysis_jobs SET status=?, finished_at=?, payload_json=? WHERE job_id=?",
        ("COMPLETED", store.now(), store.dumps({"n_interpretations": len(rows), "changes": report["changes"]}), job_id),
    )
    return {"job_id": job_id, "status": "COMPLETED", "source_changes": report["changes"],
            "affected": change_records, "auto_finalized": False}


def job(job_id: str) -> Optional[dict[str, Any]]:
    row = store.execute(
        "SELECT job_id, status, created_at, finished_at, payload_json FROM reanalysis_jobs WHERE job_id=?",
        (job_id,), fetch="one",
    )
    if not row:
        return None
    return {"job_id": row[0], "status": row[1], "created_at": row[2], "finished_at": row[3],
            "payload": store.loads(row[4], {})}


def changes(limit: int = 100) -> list[dict[str, Any]]:
    rows = store.execute(
        """SELECT job_id, variant_id, interpretation_id, change_type, payload_json, created_at
           FROM reanalysis_changes ORDER BY id DESC LIMIT ?""",
        (limit,), fetch="all",
    ) or []
    return [{"job_id": r[0], "variant_id": r[1], "interpretation_id": r[2],
             "change_type": r[3], "payload": store.loads(r[4], {}), "created_at": r[5]} for r in rows]
