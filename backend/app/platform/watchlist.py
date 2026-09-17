"""Watchlist. Triggers require human review; never auto-alter finalized interpretations."""
from __future__ import annotations

from typing import Any, Optional

from . import store


def add(*, patient_id: Optional[int], case_id: Optional[str], variant_id: Optional[str],
        created_by: Optional[int], evidence_version: Optional[str] = None) -> dict[str, Any]:
    wid = store.execute(
        """INSERT INTO watchlist
           (patient_id, case_id, variant_id, created_by, created_at, last_checked,
            last_evidence_version, status)
           VALUES (?,?,?,?,?,?,?, 'active')""",
        (patient_id, case_id, variant_id, created_by, store.now(), store.now(), evidence_version),
    )
    return get(int(wid))


def get(watch_id: int) -> Optional[dict[str, Any]]:
    row = store.execute(
        """SELECT id, patient_id, case_id, variant_id, created_by, created_at, last_checked,
                  last_evidence_version, status FROM watchlist WHERE id=?""",
        (watch_id,), fetch="one",
    )
    if not row:
        return None
    return {
        "id": row[0], "patient_id": row[1], "case_id": row[2], "variant_id": row[3],
        "created_by": row[4], "created_at": row[5], "last_checked": row[6],
        "last_evidence_version": row[7], "status": row[8],
    }


def list_all(patient_id: Optional[int] = None) -> list[dict[str, Any]]:
    if patient_id is None:
        rows = store.execute(
            """SELECT id, patient_id, case_id, variant_id, created_by, created_at, last_checked,
                      last_evidence_version, status FROM watchlist ORDER BY id DESC""",
            fetch="all",
        ) or []
    else:
        rows = store.execute(
            """SELECT id, patient_id, case_id, variant_id, created_by, created_at, last_checked,
                      last_evidence_version, status FROM watchlist WHERE patient_id=? ORDER BY id DESC""",
            (patient_id,), fetch="all",
        ) or []
    return [{
        "id": r[0], "patient_id": r[1], "case_id": r[2], "variant_id": r[3],
        "created_by": r[4], "created_at": r[5], "last_checked": r[6],
        "last_evidence_version": r[7], "status": r[8],
    } for r in rows]


def mark_triggered(variant_id: str, *, reason: str, evidence_change: str,
                   classification_before: Optional[str], classification_after: Optional[str]) -> list[dict[str, Any]]:
    rows = store.execute(
        "SELECT id FROM watchlist WHERE variant_id=? AND status='active'",
        (variant_id,), fetch="all",
    ) or []
    out = []
    for (wid,) in rows:
        store.execute(
            """INSERT INTO watchlist_triggers
               (watchlist_id, reason, evidence_change, classification_before, classification_after,
                review_required, created_at)
               VALUES (?,?,?,?,?,1,?)""",
            (wid, reason, evidence_change, classification_before, classification_after, store.now()),
        )
        store.execute(
            "UPDATE watchlist SET last_checked=?, status='WATCH_TRIGGERED' WHERE id=?",
            (store.now(), wid),
        )
        out.append({
            "watchlist_id": wid,
            "reason": reason,
            "evidence_change": evidence_change,
            "classification_before": classification_before,
            "classification_after": classification_after,
            "review_required": True,
            "auto_altered_final": False,
        })
    return out


def triggers(watch_id: Optional[int] = None) -> list[dict[str, Any]]:
    if watch_id is None:
        rows = store.execute(
            """SELECT id, watchlist_id, reason, evidence_change, classification_before,
                      classification_after, review_required, created_at
               FROM watchlist_triggers ORDER BY id DESC LIMIT 100""",
            fetch="all",
        ) or []
    else:
        rows = store.execute(
            """SELECT id, watchlist_id, reason, evidence_change, classification_before,
                      classification_after, review_required, created_at
               FROM watchlist_triggers WHERE watchlist_id=? ORDER BY id DESC""",
            (watch_id,), fetch="all",
        ) or []
    return [{
        "id": r[0], "watchlist_id": r[1], "reason": r[2], "evidence_change": r[3],
        "classification_before": r[4], "classification_after": r[5],
        "review_required": bool(r[6]), "created_at": r[7],
    } for r in rows]
