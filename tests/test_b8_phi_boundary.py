"""
Phase B8 — PHI boundary test. The payload sent to the local ranker / remote
engine must never contain patient_id, name, mrn, dob, email, or free text —
only gene/variant/disease. Proven structurally (the payload dict's keys)
rather than by string-matching output, since `disease` legitimately contains
free text describing the condition (e.g. "lung adenocarcinoma") — the
boundary is which *fields* exist, not that no string in the payload is long.
"""
from __future__ import annotations

import json

import pytest

from app.services import drug_recommendation as DR
from app.services import frontend_bridge

PHI_FIELD_NAMES = {
    "patient_id", "patientid", "patient", "subject_id", "name", "full_name",
    "mrn", "ssn", "dob", "date_of_birth", "email", "phone", "address",
}


def test_recommend_payload_only_has_gene_variant_disease(monkeypatch):
    captured = {}

    def fake_post(url, payload, timeout):
        captured.update(payload)
        return {"recommendations": []}

    monkeypatch.setattr(DR, "_post_json", fake_post)
    monkeypatch.setenv("GENOGUIDE_DRUG_API_ENABLED", "true")
    monkeypatch.setenv("GENOGUIDE_DRUG_API_URL", "https://example-live-host.test")
    monkeypatch.setattr(DR, "_inprocess_recommend", lambda payload: None)
    DR.reset_runtime_state()

    DR.recommend("EGFR", "p.Leu858Arg", "lung adenocarcinoma")

    assert set(captured.keys()) == {"gene", "variant", "disease"}
    assert not (set(k.lower() for k in captured.keys()) & PHI_FIELD_NAMES)


def test_frontend_bridge_rejects_phi_before_reaching_recommend():
    with pytest.raises(Exception):
        frontend_bridge.assert_no_phi({
            "mutation": {"gene": "EGFR", "variant": "L858R"},
            "clinical": {"disease": "NSCLC"},
            "patient_id": "G-1027",
        })


def test_frontend_bridge_normalized_output_only_has_gene_variant_disease():
    normalized = frontend_bridge.normalize_frontend_payload({
        "mutation": {"gene": "EGFR", "protein_change": "p.Leu858Arg"},
        "clinical": {"indication": "lung adenocarcinoma"},
    })
    assert set(normalized.keys()) == {"gene", "variant", "disease"}
