"""P1: phenotype, inheritance, ACMG simulator, explanation, provenance object."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GENOGUIDE_CLINICAL_DB", str(tmp_path / "clinical.db"))
    monkeypatch.setenv("GENOGUIDE_SECRET_KEY", "test-secret")
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_phenotype_normalize_id_and_negation(client):
    r = client.post("/api/v1/phenotypes/normalize", json={
        "terms": ["HP:0001250", "NOT HP:0001250", {"id": "HP:0001250", "excluded": True}],
    })
    assert r.status_code == 200
    body = r.json()
    assert "HP:0001250" in body["positive_hpo"] or body["terms"][0]["hpo_id"] == "HP:0001250"
    assert body["terms"][1]["negated"] is True
    assert body["note"]


def test_phenotype_does_not_claim_acmg(client):
    r = client.post("/api/v1/phenotypes/match", json={"terms": ["HP:0001250"], "gene": "SCN1A"})
    assert r.status_code == 200
    body = r.json()
    assert body.get("acmg_altered") is not True
    assert "classification" not in body or body.get("classification") is None


def test_inheritance_does_not_infer_phase(client):
    r = client.post("/api/v1/inheritance/solve", json={
        "child": [{"variant_id": "GRCh38:7:1:A>T", "gene": "CFTR", "chromosome": "7"},
                  {"variant_id": "GRCh38:7:2:C>G", "gene": "CFTR", "chromosome": "7"}],
    })
    body = r.json()
    assert body["phase_status"] == "UNKNOWN"
    assert body["human_review_required"] is True


def test_inheritance_trans_when_parents_split(client):
    r = client.post("/api/v1/inheritance/solve", json={
        "child": [{"variant_id": "v1", "gene": "CFTR"}, {"variant_id": "v2", "gene": "CFTR"}],
        "mother": [{"variant_id": "v1", "gene": "CFTR"}],
        "father": [{"variant_id": "v2", "gene": "CFTR"}],
        "gene_inheritance": "AUTOSOMAL_RECESSIVE",
    })
    body = r.json()
    assert body["phase_status"] == "TRANS"
    assert body["inheritance_model"] == "AUTOSOMAL_RECESSIVE"


def test_acmg_simulator_does_not_persist_official(client):
    official = {
        "classification": "PATHOGENIC",
        "interpretation_id": "INT-SIM",
        "met_criteria": ["PVS1", "PS1", "PM2"],
        "criteria": [
            {"id": "PVS1", "status": "MET", "applied_strength": "VERY_STRONG", "category": "pathogenic"},
            {"id": "PS1", "status": "MET", "applied_strength": "STRONG", "category": "pathogenic"},
            {"id": "PM2", "status": "MET", "applied_strength": "MODERATE", "category": "pathogenic"},
        ],
    }
    r = client.post("/api/v1/acmg/simulate", json={
        "official": official,
        "modifications": [{"op": "remove", "criterion": "PM2"}],
    })
    assert r.status_code == 200
    body = r.json()
    assert body["simulation_only"] is True
    assert body["persisted_as_official"] is False
    assert body["official_classification"] == "PATHOGENIC"
    from app.platform.interpretations import get
    assert get("INT-SIM") is None  # never created an official version


def test_explanation_insufficient_and_grounded(client):
    empty = client.post("/api/v1/evidence/explain", json={})
    assert empty.json()["summary"] == "INSUFFICIENT EVIDENCE FOR AUTOMATED EXPLANATION"
    r = client.post("/api/v1/evidence/explain", json={
        "acmg": {
            "classification": "PATHOGENIC",
            "confidence": "high",
            "met_criteria": ["PVS1"],
            "criteria": [{"id": "PVS1", "status": "MET", "reason": "null variant in LoF gene",
                          "sources": ["ClinVar"], "applied_strength": "VERY_STRONG"}],
            "not_evaluable": [],
        }
    })
    body = r.json()
    assert body["llm_used"] is False
    assert body["prescribes_treatment"] is False
    assert body["sets_acmg"] is False
    assert body["claims"]
    assert all(c.get("evidence_ids") for c in body["claims"])


def test_provenance_object_on_version(client):
    from app.platform import interpretations as I
    I.record(
        interpretation_id="INT-PROV", classification="VUS",
        acmg_criteria={}, ml_prediction={}, model_version="m",
        phenotype_score=None, evidence_ids=[], kg_version="k", guideline_version="g",
        provenance={"input_hash": "abc", "output_hash": "def", "ACMG_rule_version": "acmg",
                    "model_version": "m", "operator": "test"},
    )
    rec = I.get("INT-PROV")
    assert rec["provenance"]["input_hash"] == "abc"
    assert rec["provenance"]["output_hash"] == "def"
