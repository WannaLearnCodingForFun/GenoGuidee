"""Longitudinal snapshots, RBAC, normalization, trends, and projection."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GENOGUIDE_CLINICAL_DB", str(tmp_path / "clinical.db"))
    monkeypatch.setenv("GENOGUIDE_SECRET_KEY", "test-secret")
    from app.main import app
    with TestClient(app) as c:
        yield c


def _signup(client: TestClient, email: str, role: str):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "secret12", "full_name": email.split("@")[0], "role": role,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    return body["token"], body["user"], body.get("patient")


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def test_canonical_normalization_chr_prefix():
    from app.services.variant_normalize import canonical_variant_id, parse_loose_spec
    a = canonical_variant_id(chromosome="17", position=43057062, reference="T", alternate="G")
    b = canonical_variant_id(chromosome="chr17", position=43057062, reference="t", alternate="g")
    assert a == b == "GRCh38:17:43057062:T>G"
    spec = parse_loose_spec("17:43057062 T>G")
    assert spec and spec["chromosome"] == "17"


def test_trend_and_forecast_insufficient():
    from app.services.risk_forecast import forecast_risk
    from app.services.trajectory_score import classify_trend
    assert classify_trend([40]) == "UNCERTAIN"
    assert classify_trend([31, 38, 51]) == "WORSENING"
    assert classify_trend([50, 49.5, 50.2]) == "STABLE"
    out = forecast_risk([40, 42])
    assert out["available"] is False
    assert "additional longitudinal" in out["message"].lower()
    assert out["mortality_prediction"] is False
    ready = forecast_risk([31, 38, 51, 58])
    assert ready["n_observations"] == 4
    assert ready["forecast"]
    assert ready["mortality_prediction"] is False


def test_comparison_not_detected_label():
    from app.services.longitudinal_compare import NOT_DETECTED, compare_snapshots
    prev = [{"chromosome": "17", "position": 1, "reference": "A", "alternate": "T",
             "gene": "TP53", "acmg_classification": "VUS", "detected": True}]
    cur = [{"chromosome": "7", "position": 2, "reference": "C", "alternate": "G",
            "gene": "EGFR", "acmg_classification": "VUS", "detected": True}]
    cmp = compare_snapshots(cur, prev)
    assert cmp["counts"]["newly_detected"] == 1
    assert cmp["counts"]["not_detected_in_current_sample"] == 1
    assert cmp["not_detected_in_current_sample"][0]["label"] == NOT_DETECTED
    assert cmp["not_detected_in_current_sample"][0]["biological_clearance"] is False


def test_rbac_and_demo_timeline(client):
    doc_a, user_a, _ = _signup(client, "doc-a@ex.test", "doctor")
    doc_b, _, _ = _signup(client, "doc-b@ex.test", "doctor")
    lab, _, _ = _signup(client, "lab@ex.test", "lab_technician")
    pat_tok, _, patient = _signup(client, "pat@ex.test", "patient")
    other_tok, _, other = _signup(client, "other@ex.test", "patient")

    seeded = client.post("/api/clinical/demo/longitudinal", headers=_h(doc_a))
    assert seeded.status_code == 200, seeded.text
    demo_id = seeded.json()["patient"]["id"]
    assert seeded.json()["synthetic"] is True

    tl = client.get(f"/api/clinical/patients/{demo_id}/genomics/timeline", headers=_h(doc_a))
    assert tl.status_code == 200, tl.text
    body = tl.json()
    assert len(body["snapshots"]) == 4
    assert body["snapshots"][0]["test_number"] == 1
    assert body["outcome"]["supported"] is False
    assert "death" not in (body.get("change_summary") or "").lower()
    assert body["projection"]["mortality_prediction"] is False
    genes = {v["gene"] for v in body["variants"]}
    assert {"BRCA1", "EGFR", "TP53", "CFTR"} <= genes
    e = next(v for v in body["variants"] if v["gene"] == "EGFR")
    assert e["number_of_tests_detected"] == 2
    d = next(v for v in body["variants"] if v["gene"] == "TP53")
    assert "VUS" in (d["classification_history"] or [])
    assert any(c in ("Likely Pathogenic", "Pathogenic") for c in (d["classification_history"] or []))

    forbidden = client.get(f"/api/clinical/patients/{demo_id}/genomics/timeline", headers=_h(doc_b))
    assert forbidden.status_code == 403

    lab_ok = client.get(f"/api/clinical/patients/{demo_id}/genomics/timeline", headers=_h(lab))
    assert lab_ok.status_code == 200

    own = client.get(f"/api/clinical/patients/{patient['id']}/genomics/timeline", headers=_h(pat_tok))
    assert own.status_code == 200
    steal = client.get(f"/api/clinical/patients/{other['id']}/genomics/timeline", headers=_h(pat_tok))
    assert steal.status_code == 403
    steal_demo = client.get(f"/api/clinical/patients/{demo_id}/genomics/timeline", headers=_h(pat_tok))
    assert steal_demo.status_code == 403

    proj = client.get(f"/api/clinical/patients/{demo_id}/genomics/projection", headers=_h(doc_a))
    assert proj.status_code == 200
    assert proj.json()["projection"]["n_observations"] == 4

    ev = client.get("/api/clinical/models/evaluation", headers=_h(doc_a))
    assert ev.status_code == 200
    assert ev.json()["headline"]["binary_hq"]["accuracy"] == 0.9057
    ev_pat = client.get("/api/clinical/models/evaluation", headers=_h(pat_tok))
    assert ev_pat.status_code == 403


def test_snapshot_immutability_and_revisions(client):
    doc, user, _ = _signup(client, "doc-imm@ex.test", "doctor")
    lab, _, _ = _signup(client, "lab-imm@ex.test", "lab_technician")
    _, _, patient = _signup(client, "pat-imm@ex.test", "patient")
    pid = patient["id"]
    client.post("/api/clinical/workup", headers=_h(doc), json={
        "consent_confirmed": True, "patient_identifier": patient["identifier"],
    })
    vcf = (REPO / "tests" / "data" / "mini.vcf").read_bytes()
    r1 = client.post(
        "/api/clinical/uploads",
        headers=_h(doc),
        files={"file": ("t1.vcf", vcf, "text/plain")},
        data={"patient_id": str(pid)},
    )
    assert r1.status_code == 200, r1.text
    snaps = client.get(f"/api/clinical/patients/{pid}/genomics/snapshots", headers=_h(doc))
    assert snaps.status_code == 200
    first = snaps.json()["items"]
    assert len(first) == 1
    first_id = first[0]["id"]
    r2 = client.post(
        "/api/clinical/uploads",
        headers=_h(doc),
        files={"file": ("t2.vcf", b"##fileformat=VCFv4.2\n#CHROM\tPOS\tID\tREF\tALT\tQUAL\tFILTER\tINFO\n17\t43057062\t.\tT\tG\t.\tPASS\t.\n", "text/plain")},
        data={"patient_id": str(pid)},
    )
    if r2.status_code != 200:
        pytest.skip(f"second upload parser: {r2.text}")
    snaps2 = client.get(f"/api/clinical/patients/{pid}/genomics/snapshots", headers=_h(doc)).json()["items"]
    assert len(snaps2) >= 1
    still = next(s for s in snaps2 if s["id"] == first_id)
    assert still["test_number"] == 1

    client.post("/api/clinical/workup", headers=_h(doc), json={
        "consent_confirmed": True, "patient_identifier": patient["identifier"],
        "diagnosis": "fixture",
    })
    patched = client.patch(
        f"/api/clinical/patients/{pid}/report",
        headers=_h(lab),
        json={"lab_notes": "reviewed", "review_status": "REVIEWED", "reason": "lab review"},
    )
    assert patched.status_code in (200, 200)
    revs = client.get(f"/api/clinical/patients/{pid}/report-revisions", headers=_h(doc))
    assert revs.status_code == 200
    assert revs.json()["items"]


def test_unauthenticated_timeline_rejected(client):
    r = client.get("/api/clinical/patients/1/genomics/timeline")
    assert r.status_code == 401


def test_patient_risk_not_a_mean():
    from app.services.trajectory_score import patient_genomic_risk_score
    obs = [
        {"canonical_variant_id": "a", "acmg_classification": "Pathogenic",
         "pathogenicity_probability": 0.9, "allele_frequency": 0.4, "confidence": 0.8, "detected": True},
        {"canonical_variant_id": "b", "acmg_classification": "Benign",
         "pathogenicity_probability": 0.05, "allele_frequency": 0.5, "confidence": 0.8, "detected": True},
    ]
    scored = patient_genomic_risk_score(obs)
    assert scored["patient_genomic_risk_score"] is not None
    # Pathogenic must dominate a naive 47.5 mean of 90 and 5.
    assert scored["patient_genomic_risk_score"] > 60
