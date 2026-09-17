"""P2: phenopackets, cohorts, model monitoring, evidence timeline."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GENOGUIDE_CLINICAL_DB", str(tmp_path / "clinical.db"))
    monkeypatch.setenv("GENOGUIDE_SECRET_KEY", "test-secret")
    monkeypatch.setenv("ENABLE_COHORT_MODE", "true")
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_phenopacket_import_export(client):
    pkt = {
        "id": "PPK-1",
        "subject": {"id": "PAT-TEST"},
        "phenotypicFeatures": [
            {"type": {"id": "HP:0001250", "label": "Seizure"}, "excluded": False},
        ],
        "interpretations": [],
    }
    r = client.post("/api/v1/phenopackets/import", json={"phenopacket": pkt, "case_id": "PPK-1"})
    assert r.status_code == 200
    assert r.json()["imported"] is True
    out = client.get("/api/v1/cases/PPK-1/phenopacket")
    assert out.status_code == 200
    assert out.json()["id"] == "PPK-1"


def test_cohort_hides_identity(client):
    c = client.post("/api/v1/cohorts", json={"name": "demo"})
    cid = c.json()["cohort_id"]
    client.post(f"/api/v1/cohorts/{cid}/cases", json={"case_id": "CASE-A", "patient_id": 1})
    body = client.get(f"/api/v1/cohorts/{cid}", headers={"X-Role": "RESEARCHER"}).json()
    blob = str(body)
    assert "full_name" not in blob
    assert "email" not in blob
    assert body["identity_fields_present"] is False
    assert "case_alias" in body["cases"][0]


def test_model_drift_and_ood(client):
    r = client.post("/api/v1/model-monitoring/snapshot", json={
        "predictions": [
            {"top_class": "vus", "probabilities": {"vus": 0.9, "pathogenic": 0.1}, "gene": "BRCA1"},
            {"top_class": "vus", "probabilities": {"vus": 0.8, "pathogenic": 0.2}, "gene": "TP53"},
        ],
        "training_prior": {"benign": 0.2, "likely_benign": 0.2, "vus": 0.2,
                           "likely_pathogenic": 0.2, "pathogenic": 0.2},
    })
    assert r.status_code == 200
    assert r.json()["retrained"] is False
    assert r.json()["drift_level"] in {"LOW", "MODERATE", "HIGH"}
    ood = client.post("/api/v1/model-monitoring/ood", json={
        "ml": {"top_class": "pathogenic", "probabilities": {"pathogenic": 0.9, "vus": 0.1},
               "calibrated_probabilities": {"pathogenic": 0.9, "vus": 0.1}, "model_version": "m"},
        "acmg_classification": "BENIGN",
    })
    assert ood.json()["human_review_required"] is True


def test_evidence_timeline(client):
    client.post("/api/v1/evidence/graph/edge", json={
        "source_key": "variant:TL",
        "target_key": "clinvar:TL",
        "edge_type": "VARIANT_HAS_CLINVAR_ASSERTION",
        "source": "ClinVar",
        "source_id": "VCV1",
        "source_version": "2018",
        "retrieved_at": "2018-01-01T00:00:00+00:00",
        "direction": "SUPPORTS_PATHOGENIC",
        "source_node": {"type": "Variant", "label": "TL"},
        "target_node": {"type": "ClinVarAssertion", "label": "P"},
    })
    tl = client.get("/api/v1/evidence/timeline/TL")
    assert tl.status_code == 200
    assert tl.json()["events"]
