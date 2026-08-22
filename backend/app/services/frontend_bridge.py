"""
Frontend ↔ local GenoGuide integration layer.

This module does NOT implement ranking, feature extraction, or evidence
evaluation. It only:

    1. accepts a frontend JSON payload (mutation + clinical context)
    2. rejects identifiers / PHI keys (nothing identifiable is forwarded)
    3. normalizes to {gene, variant, disease} for the existing connector
    4. invokes drug_recommendation.recommend() unchanged
    5. returns that response to the caller

The public HTTPS path is an ngrok tunnel in front of this process
(see docs/FRONTEND_TUNNEL.md). Ranking logic stays in the existing pipeline.
"""
from __future__ import annotations

import os
import re
from typing import Any, Optional

from fastapi import Header, HTTPException, Request

from .drug_recommendation import normalize_indication, protein_shorthand, recommend

# Keys that must never be accepted on the public tunnel.
_PHI_KEYS = {
    "patient_id", "patientid", "patient", "subject_id", "name", "full_name",
    "given_name", "family_name", "mrn", "ssn", "national_id", "dob",
    "date_of_birth", "email", "phone", "address", "ssn_last4",
}

_GENE_RE = re.compile(r"^[A-Za-z0-9-]{1,20}$")


def tunnel_key() -> str:
    return os.environ.get("GENOGUIDE_TUNNEL_KEY", "").strip()


def require_frontend_access(
    request: Request,
    x_genoguide_key: Optional[str] = Header(default=None, alias="X-GenoGuide-Key"),
    x_role: Optional[str] = Header(default=None, alias="X-Role"),
) -> str:
    """Shared-secret when tunneled; local dev falls back to the X-Role demo gate."""
    expected = tunnel_key()
    presented = (x_genoguide_key or request.headers.get("x-tunnel-key") or "").strip()
    if expected:
        if presented != expected:
            raise HTTPException(
                401,
                "missing or invalid X-GenoGuide-Key — required when GENOGUIDE_TUNNEL_KEY is set",
            )
        return "tunnel"
    role = (x_role or "RESEARCHER").upper()
    if role == "PATIENT":
        raise HTTPException(403, "role PATIENT cannot call the therapy bridge")
    return role


def _collect_keys(obj: Any, into: set[str]) -> None:
    if isinstance(obj, dict):
        for k, v in obj.items():
            into.add(str(k).lower().replace("-", "_"))
            _collect_keys(v, into)
    elif isinstance(obj, list):
        for item in obj:
            _collect_keys(item, into)


def assert_no_phi(payload: dict[str, Any]) -> None:
    keys: set[str] = set()
    _collect_keys(payload, keys)
    hit = sorted(keys & _PHI_KEYS)
    if hit:
        raise HTTPException(
            400,
            f"refusing identifiable fields on the public therapy bridge: {hit}. "
            "Send only gene / protein change / oncology indication.",
        )


def normalize_frontend_payload(payload: dict[str, Any]) -> dict[str, str]:
    """Map a frontend mutation+clinical object to {gene, variant, disease}."""
    mutation = payload.get("mutation") if isinstance(payload.get("mutation"), dict) else {}
    clinical = payload.get("clinical") if isinstance(payload.get("clinical"), dict) else {}

    gene = (
        mutation.get("gene")
        or payload.get("gene")
        or ""
    )
    gene = str(gene).strip().upper()
    if not gene or not _GENE_RE.match(gene):
        raise HTTPException(422, "mutation.gene is required (HGNC symbol, e.g. EGFR)")

    protein_raw = (
        mutation.get("protein_change")
        or mutation.get("hgvs_p")
        or mutation.get("variant")
        or payload.get("protein_change")
        or payload.get("hgvs_p")
        or payload.get("variant")
        or ""
    )
    variant = protein_shorthand(str(protein_raw).strip()) if protein_raw else None
    if not variant:
        raise HTTPException(
            422,
            "unmappable protein change — send L858R or p.Leu858Arg; "
            "genomic IDs and c. HGVS are not guessed",
        )

    disease_raw = (
        clinical.get("indication")
        or clinical.get("disease")
        or clinical.get("diagnosis")
        or payload.get("indication")
        or payload.get("disease")
        or payload.get("diagnosis")
        or ""
    )
    disease = normalize_indication(str(disease_raw).strip(), passthrough=True) if disease_raw else None
    if not disease:
        raise HTTPException(422, "clinical.indication (or disease) is required, e.g. NSCLC")

    return {"gene": gene, "variant": variant, "disease": disease}


def invoke_existing_pipeline(normalized: dict[str, str]) -> dict[str, Any]:
    """Call the existing recommend() function. Do not reimplement ranking."""
    result = recommend(normalized["gene"], normalized["variant"], normalized["disease"])
    return result.model_dump(mode="json")


def handle_frontend_therapy(payload: dict[str, Any]) -> dict[str, Any]:
    assert_no_phi(payload)
    normalized = normalize_frontend_payload(payload)
    recommendation = invoke_existing_pipeline(normalized)
    return {
        "ok": True,
        "layer": "frontend-bridge",
        "normalized": normalized,
        "recommendation": recommendation,
        "disclaimer": (
            "Integration layer only — ranking is produced by the existing drug "
            "recommendation pipeline. Not a prescription. Does not alter ACMG. "
            "No patient identifiers are accepted or forwarded."
        ),
    }
