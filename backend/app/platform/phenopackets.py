"""Minimal GA4GH Phenopacket v2-shaped adapter. Does not replace internal patient schema."""
from __future__ import annotations

from typing import Any, Optional
import uuid

from . import store
from .phenotype_engine import normalize_one, profile


def to_phenopacket(patient: dict[str, Any], *, case_id: Optional[str] = None,
                   phenotypes: Optional[list[dict[str, Any]]] = None,
                   variants: Optional[list[dict[str, Any]]] = None) -> dict[str, Any]:
    feats = []
    for p in phenotypes or []:
        hid = p.get("hpo_id") or p.get("type_id")
        feats.append({
            "type": {"id": hid, "label": p.get("phenotype") or p.get("label")},
            "excluded": bool(p.get("negated") or p.get("excluded")),
            "onset": {"label": p.get("onset")} if p.get("onset") else None,
            "severity": {"label": p.get("severity")} if p.get("severity") else None,
        })
    interpretations = []
    for v in variants or []:
        interpretations.append({
            "id": v.get("id") or v.get("variant_id"),
            "progressStatus": "IN_PROGRESS",
            "diagnosis": {
                "gene": v.get("gene"),
                "variant": v.get("normalized_variant") or v.get("hgvs_c"),
            },
        })
    pkt = {
        "id": case_id or f"PPK-{uuid.uuid4().hex[:8]}",
        "subject": {
            "id": patient.get("identifier") or str(patient.get("id")),
            "sex": patient.get("sex"),
            "timeAtLastEncounter": {"age": {"iso8601duration": f"P{patient.get('age')}Y"} if patient.get("age") else None},
        },
        "phenotypicFeatures": [f for f in feats if f["type"]["id"]],
        "interpretations": interpretations,
        "metaData": {
            "createdBy": "GenoGuide PhenopacketAdapter",
            "phenopacketSchemaVersion": "2.0",
            "resources": [{"id": "hp", "name": "Human Phenotype Ontology", "namespacePrefix": "HP",
                           "url": "http://purl.obolibrary.org/obo/hp.owl"}],
        },
    }
    return pkt


def from_phenopacket(pkt: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(pkt, dict) or "subject" not in pkt:
        raise ValueError("not a Phenopacket: missing subject")
    feats = []
    for f in pkt.get("phenotypicFeatures") or []:
        typ = f.get("type") or {}
        n = normalize_one(typ.get("id") or typ.get("label") or "", negated=bool(f.get("excluded")))
        onset = (f.get("onset") or {}).get("label") if isinstance(f.get("onset"), dict) else f.get("onset")
        n["onset"] = onset
        feats.append(n)
    return {
        "subject_id": (pkt.get("subject") or {}).get("id"),
        "phenotypes": feats,
        "interpretations": pkt.get("interpretations") or [],
        "phenopacket_id": pkt.get("id"),
        "valid": True,
    }


def save(pkt: dict[str, Any], *, case_id: Optional[str], patient_id: Optional[int]) -> int:
    return int(store.execute(
        "INSERT INTO phenopacket_records (case_id, patient_id, payload_json, created_at) VALUES (?,?,?,?)",
        (case_id or pkt.get("id"), patient_id, store.dumps(pkt), store.now()),
    ))


def load_for_case(case_id: str) -> Optional[dict[str, Any]]:
    row = store.execute(
        "SELECT payload_json FROM phenopacket_records WHERE case_id=? ORDER BY id DESC LIMIT 1",
        (case_id,), fetch="one",
    )
    return store.loads(row[0], None) if row else None
