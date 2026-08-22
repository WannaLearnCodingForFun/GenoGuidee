"""Frontend bridge — normalize only; existing recommend() is invoked unchanged."""
from __future__ import annotations

import json
from pathlib import Path

import pytest
from fastapi import HTTPException

from app.services import frontend_bridge as FB

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/egfr_l858r_nsclc.json").read_text())


def test_normalize_nested_frontend_payload():
    out = FB.normalize_frontend_payload({
        "mutation": {"gene": "egfr", "protein_change": "p.Leu858Arg"},
        "clinical": {"indication": "lung adenocarcinoma"},
    })
    assert out == {"gene": "EGFR", "variant": "L858R", "disease": "NSCLC"}


def test_normalize_flat_aliases():
    out = FB.normalize_frontend_payload({
        "gene": "BRAF", "variant": "V600E", "disease": "Melanoma",
    })
    assert out == {"gene": "BRAF", "variant": "V600E", "disease": "Melanoma"}


def test_rejects_genomic_only_payload():
    with pytest.raises(HTTPException) as ei:
        FB.normalize_frontend_payload({
            "mutation": {"gene": "EGFR", "protein_change": "GRCh38:7:55191822:T>G"},
            "clinical": {"disease": "NSCLC"},
        })
    assert ei.value.status_code == 422


def test_rejects_phi_keys():
    with pytest.raises(HTTPException) as ei:
        FB.assert_no_phi({
            "mutation": {"gene": "EGFR", "variant": "L858R"},
            "clinical": {"disease": "NSCLC"},
            "patient_id": "G-1027",
        })
    assert ei.value.status_code == 400
    assert "patient_id" in ei.value.detail


def test_handle_invokes_existing_recommend_only(monkeypatch):
    calls = []

    def fake_recommend(gene, variant, disease, **_k):
        calls.append((gene, variant, disease))
        from app.schemas.therapy import SomaticTherapy, TherapyAvailability, TherapyRecommendation
        return SomaticTherapy(
            availability=TherapyAvailability.AVAILABLE,
            request={"gene": gene, "variant": variant, "disease": disease},
            recommendations=[TherapyRecommendation(
                drug="Osimertinib", rank=1, score=0.94,
                response="Sensitivity", evidence_level="A", evidence_count=25,
            )],
        )

    monkeypatch.setattr(FB, "recommend", fake_recommend)
    body = FB.handle_frontend_therapy({
        "mutation": {"gene": "EGFR", "hgvs_p": "p.Leu858Arg"},
        "clinical": {"diagnosis": "NSCLC"},
    })
    assert body["ok"] is True
    assert body["normalized"] == {"gene": "EGFR", "variant": "L858R", "disease": "NSCLC"}
    assert calls == [("EGFR", "L858R", "NSCLC")]
    assert body["recommendation"]["recommendations"][0]["drug"] == "Osimertinib"
    assert "not a prescription" in body["disclaimer"].lower()
