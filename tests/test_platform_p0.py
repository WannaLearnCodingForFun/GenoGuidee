"""P0 platform: flags, evidence graph, radar, versions/diff, reanalysis, watchlist, curation."""
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


def test_legacy_health_with_platform_mounted(client):
    r = client.get("/api/v1/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    r2 = client.get("/api/status")
    assert r2.status_code == 200


def test_flags_off_does_not_break_legacy(tmp_path, monkeypatch):
    monkeypatch.setenv("GENOGUIDE_CLINICAL_DB", str(tmp_path / "off.db"))
    for k in ("ENABLE_REANALYSIS", "ENABLE_EVIDENCE_GRAPH", "ENABLE_HUMAN_REVIEW",
              "ENABLE_PHENOPACKET", "ENABLE_INHERITANCE_SOLVER", "ENABLE_VARIANT_SIMULATOR",
              "ENABLE_COHORT_MODE", "ENABLE_MODEL_MONITORING", "ENABLE_INTERPRETATION_VERSIONING",
              "ENABLE_WATCHLIST", "ENABLE_PHENOTYPE_ENGINE", "ENABLE_EXPLANATION",
              "ENABLE_PROVENANCE_UPGRADE", "ENABLE_EVIDENCE_TIMELINE"):
        monkeypatch.setenv(k, "false")
    from app.main import app
    with TestClient(app) as c:
        assert c.get("/api/v1/health").status_code == 200
        assert c.get("/api/status").status_code == 200
        body = c.post("/api/v1/acmg/evaluate", json={}).json()
        assert body["classification"] == "VUS"
        r = c.post("/api/v1/reanalysis/check")
        assert r.status_code == 503
        assert r.json()["error"]["code"] == "FEATURE_DISABLED"


def test_evidence_edge_requires_provenance(client):
    r = client.post("/api/v1/evidence/graph/edge", json={
        "source_key": "variant:x", "target_key": "evidence:x:PS3",
        "edge_type": "VARIANT_HAS_EVIDENCE",
        "source_node": {"type": "Variant", "label": "x"},
        "target_node": {"type": "Evidence", "label": "PS3"},
    })
    assert r.status_code == 422
    assert r.json()["error"]["code"] == "EVIDENCE_PROVENANCE_REQUIRED"


def test_evidence_graph_roundtrip(client):
    r = client.post("/api/v1/evidence/graph/edge", json={
        "source_key": "variant:demo",
        "target_key": "evidence:demo:PS3",
        "edge_type": "VARIANT_HAS_EVIDENCE",
        "source": "ClinVar",
        "source_id": "VCV000000",
        "source_version": "2026-08",
        "retrieved_at": "2026-09-17T00:00:00+00:00",
        "evidence_strength": "EXPERT_PANEL",
        "direction": "SUPPORTS_PATHOGENIC",
        "source_node": {"type": "Variant", "label": "demo"},
        "target_node": {"type": "Evidence", "label": "PS3"},
    })
    assert r.status_code == 200
    assert r.json()["source"] == "ClinVar"
    g = client.get("/api/v1/graph", params={"seed": "variant:demo"})
    assert g.status_code == 200
    assert any(e["edge_type"] == "VARIANT_HAS_EVIDENCE" for e in g.json()["edges"])


def test_conflict_radar_missing_is_not_benign(client):
    r = client.post("/api/v1/evidence/radar", json={})
    body = r.json()
    assert body["overall_state"] == "INSUFFICIENT"
    assert body["confidence"] == 0.0
    assert all(i["category"] != "BENIGN_SUPPORT" for i in body["items"] if i["category"] == "MISSING")
    assert body["human_review_required"] is True


def test_conflict_radar_conflicting(client):
    r = client.post("/api/v1/evidence/radar", json={"clinvar": "Pathogenic", "acmg": "BENIGN"})
    body = r.json()
    assert body["overall_state"] == "CONFLICTING"
    assert body["confidence"] <= 0.25
    assert body["human_review_required"] is True


def test_interpretation_versioning_and_diff(client):
    from app.platform import interpretations as I
    I.record(
        interpretation_id="INT-TEST1", classification="VUS",
        acmg_criteria={"classification": "VUS", "criteria": [
            {"id": "PM2", "status": "NOT_MET", "category": "pathogenic"}
        ], "met_criteria": []},
        ml_prediction={"top_class": "vus", "probabilities": {"vus": 0.61}, "calibrated_probabilities": {"vus": 0.61}},
        model_version="m1", phenotype_score=0.2, evidence_ids=["e1"],
        kg_version="kg-evidence-v2.0.0", guideline_version="acmg-amp-2015",
        variant_id="GRCh38:17:1:A>T",
    )
    I.record(
        interpretation_id="INT-TEST1", classification="LIKELY_PATHOGENIC",
        acmg_criteria={"classification": "LIKELY_PATHOGENIC", "criteria": [
            {"id": "PS3", "status": "MET", "applied_strength": "STRONG", "category": "pathogenic"}
        ], "met_criteria": ["PS3"]},
        ml_prediction={"top_class": "likely_pathogenic", "probabilities": {"likely_pathogenic": 0.87},
                       "calibrated_probabilities": {"likely_pathogenic": 0.87}},
        model_version="m1", phenotype_score=0.4, evidence_ids=["e1", "e2"],
        kg_version="kg-evidence-v2.0.0", guideline_version="acmg-amp-2015",
        variant_id="GRCh38:17:1:A>T",
    )
    hist = client.get("/api/v1/interpretations/INT-TEST1/history")
    assert hist.status_code == 200
    assert len(hist.json()["versions"]) == 2
    d = client.get("/api/v1/interpretations/INT-TEST1/diff/1/2")
    assert d.status_code == 200
    body = d.json()
    assert body["changed_classification"]["before"] == "VUS"
    assert body["changed_classification"]["after"] == "LIKELY_PATHOGENIC"
    assert "e2" in body["new_evidence"]
    assert "PS3" in body["summary"]
    assert "0.61" in body["summary"] or "MODEL:" in body["summary"]
    assert body["deterministic"] is True


def test_reanalysis_does_not_auto_finalize(client):
    from app.platform import interpretations as I
    I.record(
        interpretation_id="INT-RA", classification="VUS",
        acmg_criteria={"met_criteria": []}, ml_prediction={}, model_version="m",
        phenotype_score=None, evidence_ids=[], kg_version="k", guideline_version="g",
        variant_id="GRCh38:1:1:A>T", curation_state="FINALIZED",
    )
    chk = client.post("/api/v1/reanalysis/check")
    assert chk.status_code == 200
    run = client.post("/api/v1/reanalysis/run")
    assert run.status_code == 200
    assert run.json()["auto_finalized"] is False
    job_id = run.json()["job_id"]
    job = client.get(f"/api/v1/reanalysis/jobs/{job_id}")
    assert job.json()["status"] == "COMPLETED"
    from app.platform.interpretations import get
    assert get("INT-RA")["curation_state"] == "FINALIZED"
    assert get("INT-RA")["classification"] == "VUS"


def test_watchlist_trigger(client):
    w = client.post("/api/v1/watchlist", json={"variant_id": "GRCh38:1:1:A>T"},
                    headers={"X-Role": "DOCTOR"})
    assert w.status_code == 200
    from app.platform.watchlist import mark_triggered
    trig = mark_triggered("GRCh38:1:1:A>T", reason="WATCH TRIGGERED",
                          evidence_change="ClinVar update",
                          classification_before="VUS", classification_after="VUS")
    assert trig and trig[0]["review_required"] is True
    assert trig[0]["auto_altered_final"] is False
    listing = client.get("/api/v1/watchlist/triggers")
    assert listing.json()["triggers"]


def test_curation_audit_and_immutable_final(client):
    from app.platform import interpretations as I
    I.record(
        interpretation_id="INT-CUR", classification="VUS",
        acmg_criteria={"criteria": [{"id": "PM2", "status": "MET", "category": "pathogenic"}]},
        ml_prediction={}, model_version="m", phenotype_score=None, evidence_ids=[],
        kg_version="k", guideline_version="g",
    )
    r = client.post("/api/v1/curation", json={
        "interpretation_id": "INT-CUR", "action": "transition", "state": "LAB_REVIEW",
        "reason": "lab queue",
    }, headers={"X-Role": "DOCTOR"})
    assert r.status_code == 200
    r = client.post("/api/v1/curation", json={
        "interpretation_id": "INT-CUR", "action": "transition", "state": "CLINICAL_REVIEW",
        "reason": "ready",
    }, headers={"X-Role": "DOCTOR"})
    assert r.status_code == 200
    r = client.post("/api/v1/curation", json={
        "interpretation_id": "INT-CUR", "action": "finalize", "reason": "sign-out",
    }, headers={"X-Role": "DOCTOR"})
    assert r.status_code == 200
    assert r.json()["curation_state"] == "FINALIZED"
    r = client.post("/api/v1/curation", json={
        "interpretation_id": "INT-CUR", "action": "change_evidence", "criterion_id": "PM2",
        "new_status": "NOT_MET", "reason": "should fail",
    }, headers={"X-Role": "DOCTOR"})
    assert r.status_code == 409
    ev = client.get("/api/v1/curation/INT-CUR/events")
    assert any(e["action"] == "transition" for e in ev.json()["events"])
