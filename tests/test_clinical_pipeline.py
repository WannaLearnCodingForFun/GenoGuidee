"""Clinical persistence, RBAC, ingest, provenance, and health (TEST FIXTURES)."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
MINI_VCF = REPO / "tests" / "data" / "mini.vcf"
TXT_OK = "17 43057062 T TG\nBRCA1:c.5266dupC\n"
TXT_BAD = "this is not a variant\n"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GENOGUIDE_CLINICAL_DB", str(tmp_path / "clinical.db"))
    monkeypatch.setenv("GENOGUIDE_SECRET_KEY", "test-secret")
    from app.main import app
    with TestClient(app) as c:
        yield c


def _signup(client: TestClient, email: str, role: str, password: str = "secret12"):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": password, "full_name": email.split("@")[0], "role": role,
    })
    assert r.status_code == 200, r.text
    body = r.json()
    return body["token"], body["user"]


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _patient_account(client: TestClient, email: str):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": "secret12", "full_name": email.split("@")[0], "role": "patient",
    })
    assert r.status_code == 200, r.text
    body = r.json()
    return body["token"], body["user"], body["patient"]


def _workup(client: TestClient, token: str, identifier: str, **extra):
    payload = {"consent_confirmed": True, "patient_identifier": identifier, **extra}
    r = client.post("/api/clinical/workup", headers=_h(token), json=payload)
    assert r.status_code == 200, r.text
    return r.json()


def test_signup_login_me_roles(client):
    for role in ("doctor", "patient", "lab_technician"):
        token, user = _signup(client, f"{role}@ex.test", role)
        assert user["role"] == role
        me = client.get("/api/auth/me", headers=_h(token))
        assert me.status_code == 200
        assert me.json()["role"] == role
        payload = {"email": f"{role}@ex.test", "password": "secret12"}
        if role == "patient":
            payload["patient_id"] = me.json()["patient"]["identifier"]
        login = client.post("/api/auth/login", json=payload)
        assert login.status_code == 200
        assert login.json()["user"]["role"] == role
    bad = client.post("/api/auth/login", json={"email": "doctor@ex.test", "password": "wrong"})
    assert bad.status_code == 401


def test_workup_persists_patient_and_history(client):
    token, _ = _signup(client, "doc@ex.test", "doctor")
    _, _, registered = _patient_account(client, "hist-pat@ex.test")
    r = _workup(client, token, registered["identifier"], **{
        "age": 42, "sex": "F", "diagnosis": "hereditary breast cancer",
        "presenting_complaint": "family history",
        "phenotypes": ["breast carcinoma"],
        "prior_conditions": ["hypertension"],
        "medications": ["tamoxifen"],
        "family_history_positive": True,
        "family_details": "mother breast cancer age 48",
    })
    ident = r["patient"]["identifier"]
    assert ident == registered["identifier"]
    pid = r["patient"]["id"]
    assert pid == registered["id"]
    bundle = client.get(f"/api/clinical/patients/{pid}", headers=_h(token)).json()
    assert bundle["patient"]["diagnosis"] == "hereditary breast cancer"
    assert bundle["phenotypes"][0]["phenotype"] == "breast carcinoma"
    assert bundle["medications"][0]["medication"] == "tamoxifen"
    assert bundle["family_history"]
    assert bundle["patient"]["consent_confirmed"] == 1
    consent = client.get(f"/api/clinical/patients/{pid}/consent", headers=_h(token)).json()
    assert consent["state"] == "granted"
    graph = client.get(f"/api/clinical/patients/{pid}/graph", headers=_h(token)).json()
    assert any(n["type"] == "Patient" for n in graph["nodes"])


def test_patient_cannot_access_other_patient(client):
    doc, _ = _signup(client, "doc2@ex.test", "doctor")
    _, _, registered = _patient_account(client, "other-target@ex.test")
    created = _workup(client, doc, registered["identifier"], age=30, sex="M", diagnosis="test")
    pid = created["patient"]["id"]
    pat, _ = _signup(client, "pat2@ex.test", "patient")
    r = client.get(f"/api/clinical/patients/{pid}", headers=_h(pat))
    assert r.status_code == 403
    own = client.get("/api/clinical/patients", headers=_h(pat))
    assert own.status_code == 200
    assert all(p["id"] != pid for p in own.json())


def test_technician_cannot_submit_workup(client):
    tech, _ = _signup(client, "lab@ex.test", "lab_technician")
    r = client.post("/api/clinical/workup", headers=_h(tech), json={
        "age": 20, "diagnosis": "blocked", "consent_confirmed": True,
    })
    assert r.status_code == 403


def test_lab_sees_assigned_patient(client):
    _signup(client, "lab-first@ex.test", "lab_technician")
    doc, _ = _signup(client, "doc-lab@ex.test", "doctor")
    _, _, registered = _patient_account(client, "lab-case@ex.test")
    created = _workup(client, doc, registered["identifier"], age=51, diagnosis="assigned-case")
    pid = created["patient"]["id"]
    tech, _ = _signup(client, "lab-later@ex.test", "lab_technician")
    rows = client.get("/api/clinical/patients", headers=_h(tech)).json()
    assert any(p["id"] == pid for p in rows)


def test_vcf_unassigned_then_assign(client):
    token, _ = _signup(client, "doc-vcf@ex.test", "doctor")
    _, _, registered = _patient_account(client, "vcf-pat@ex.test")
    work = _workup(client, token, registered["identifier"], age=40, diagnosis="vcf-case")
    pid = work["patient"]["id"]
    data = MINI_VCF.read_bytes()
    up = client.post(
        "/api/clinical/uploads",
        headers=_h(token),
        files={"file": ("mini.vcf", data, "text/plain")},
    )
    assert up.status_code == 200, up.text
    body = up.json()
    assert body["patient_id"] is None
    assert body["parsing_status"] == "PARSED"
    assert body["variant_count"] >= 1
    assert len(body["sha256"]) == 64
    assigned = client.post(
        f"/api/clinical/uploads/{body['id']}/assign",
        headers=_h(token),
        json={"patient_id": pid},
    )
    assert assigned.status_code == 200
    assert assigned.json()["patient_id"] == pid
    tracker = client.get("/api/clinical/uploads", headers=_h(token)).json()
    assert tracker[0]["id"] == body["id"]
    dup = client.post(
        "/api/clinical/uploads",
        headers=_h(token),
        files={"file": ("mini-again.vcf", data, "text/plain")},
    )
    assert dup.status_code == 409


def test_malformed_vcf_and_txt(client):
    token, _ = _signup(client, "doc-bad@ex.test", "doctor")
    bad_vcf = client.post(
        "/api/clinical/uploads",
        headers=_h(token),
        files={"file": ("bad.vcf", b"not a vcf", "text/plain")},
    )
    assert bad_vcf.status_code == 422
    ok_txt = client.post(
        "/api/clinical/uploads",
        headers=_h(token),
        files={"file": ("ok.txt", TXT_OK.encode(), "text/plain")},
    )
    assert ok_txt.status_code == 200, ok_txt.text
    assert ok_txt.json()["variant_count"] == 2
    bad_txt = client.post(
        "/api/clinical/uploads",
        headers=_h(token),
        files={"file": ("bad.txt", TXT_BAD.encode(), "text/plain")},
    )
    assert bad_txt.status_code == 422


def test_interpret_and_provenance_chain(client):
    token, _ = _signup(client, "doc-int@ex.test", "doctor")
    _, _, registered = _patient_account(client, "interp-pat@ex.test")
    work = _workup(client, token, registered["identifier"], age=44, diagnosis="interp-case")
    pid = work["patient"]["id"]
    up = client.post(
        "/api/clinical/uploads",
        headers=_h(token),
        data={"patient_id": str(pid)},
        files={"file": ("mini.vcf", MINI_VCF.read_bytes(), "text/plain")},
    )
    assert up.status_code == 200, up.text
    vid = up.json()["variants"][0]["id"]
    before = client.get(f"/api/clinical/patients/{pid}/provenance", headers=_h(token)).json()
    interp = client.post(
        f"/api/clinical/variants/{vid}/interpret?patient_id={pid}",
        headers=_h(token),
    )
    assert interp.status_code == 200, interp.text
    body = interp.json()
    assert "acmg" in body and "ml" in body and "reconciliation" in body
    assert body["reconciliation"]["authority"]
    after = client.get(f"/api/clinical/patients/{pid}/provenance", headers=_h(token)).json()
    assert after["block_count"] > before["block_count"]
    assert after["interpretations"] >= 1
    block_id = after["blocks"][-1]["id"]
    verified = client.post("/api/clinical/provenance/verify", headers=_h(token), json={"block_id": block_id})
    assert verified.status_code == 200
    assert verified.json()["verified"] is True
    grown = client.get(f"/api/clinical/patients/{pid}/provenance", headers=_h(token)).json()
    assert grown["block_count"] > after["block_count"]
    audit = client.get(f"/api/clinical/patients/{pid}/audit", headers=_h(token)).json()
    assert any(e["action"] == "clinical_workup_saved" for e in audit["events"])
    report = client.get(f"/api/clinical/patients/{pid}/report", headers=_h(token))
    assert report.status_code == 200


def test_txt_without_coordinates_is_not_invented(client):
    token, _ = _signup(client, "doc-hgvs@ex.test", "doctor")
    up = client.post(
        "/api/clinical/uploads",
        headers=_h(token),
        files={"file": ("hgvs.txt", b"BRCA1:c.5266dupC\n", "text/plain")},
    )
    assert up.status_code == 200
    vid = up.json()["variants"][0]["id"]
    interp = client.post(f"/api/clinical/variants/{vid}/interpret", headers=_h(token))
    assert interp.status_code == 200
    assert interp.json()["acmg"]["classification"] == "NOT_EVALUABLE"
    assert interp.json()["ml"]["confidence"] is None


def test_system_and_ml_health(client):
    sys_h = client.get("/api/system/health")
    assert sys_h.status_code == 200
    body = sys_h.json()
    assert body["backend"] == "ready"
    assert body["acmg"] == "ready"
    assert body["vcf_parser"] == "ready"
    assert body["knowledge_graph"] == "ready"
    ml = client.get("/api/ml/health")
    assert ml.status_code == 200
    assert ml.json()["status"] in {"ready", "not_configured"}
    th = client.get("/api/therapy/health")
    assert th.status_code == 200


def test_unauthenticated_clinical_is_401(client):
    assert client.get("/api/clinical/patients").status_code == 401
    assert client.get("/api/auth/me").status_code == 401


def test_doctor_cannot_see_another_doctors_patient(client):
    doc_a, _ = _signup(client, "doc-a@ex.test", "doctor")
    _, _, registered = _patient_account(client, "isolated-pat@ex.test")
    created = _workup(client, doc_a, registered["identifier"], age=41, diagnosis="isolated-case")
    pid = created["patient"]["id"]
    doc_b, _ = _signup(client, "doc-b@ex.test", "doctor")
    listed = client.get("/api/clinical/patients", headers=_h(doc_b)).json()
    assert all(p["id"] != pid for p in listed)
    denied = client.get(f"/api/clinical/patients/{pid}", headers=_h(doc_b))
    assert denied.status_code == 403
    assert denied.json()["detail"] == "You do not have access to this patient."


def test_patient_upload_auto_attaches_to_session(client):
    token, _ = _signup(client, "self-upload@ex.test", "patient")
    own = client.get("/api/clinical/patients", headers=_h(token)).json()
    assert len(own) == 1
    up = client.post(
        "/api/clinical/uploads",
        headers=_h(token),
        files={"file": ("mini.vcf", MINI_VCF.read_bytes(), "text/plain")},
    )
    assert up.status_code == 200, up.text
    assert up.json()["patient_id"] == own[0]["id"]
    assert up.json()["variants"][0]["source_type"] == "UPLOADED_VCF"
    lon = client.get(f"/api/clinical/patients/{own[0]['id']}/longitudinal", headers=_h(token)).json()
    assert lon["trajectory_available"] is False
    assert "Single observation" in (lon["message"] or "")
    assert lon["outcome"]["supported"] is False


def test_longitudinal_requires_multiple_real_samples(client):
    token, _ = _signup(client, "doc-lon@ex.test", "doctor")
    _, _, registered = _patient_account(client, "lon-pat@ex.test")
    work = _workup(client, token, registered["identifier"], age=55, diagnosis="lon-case")
    pid = work["patient"]["id"]
    first = MINI_VCF.read_bytes()
    second = first + b"\n# second independent sample\n"
    a = client.post(
        "/api/clinical/uploads",
        headers=_h(token),
        data={"patient_id": str(pid)},
        files={"file": ("sample-a.vcf", first, "text/plain")},
    )
    b = client.post(
        "/api/clinical/uploads",
        headers=_h(token),
        data={"patient_id": str(pid)},
        files={"file": ("sample-b.vcf", second, "text/plain")},
    )
    assert a.status_code == 200 and b.status_code == 200, (a.text, b.text)
    lon = client.get(f"/api/clinical/patients/{pid}/longitudinal", headers=_h(token)).json()
    assert lon["observation_count"] >= 2
    assert lon["trajectory_available"] is True
    assert any(s["trajectory_available"] for s in lon["series"])


def test_lab_updates_report_and_all_roles_see_it(client):
    doc, _ = _signup(client, "doc-rep@ex.test", "doctor")
    _, _, registered = _patient_account(client, "rep-pat@ex.test")
    work = _workup(client, doc, registered["identifier"], age=39, diagnosis="report-case")
    pid = work["patient"]["id"]
    up = client.post(
        "/api/clinical/uploads",
        headers=_h(doc),
        data={"patient_id": str(pid)},
        files={"file": ("mini.vcf", MINI_VCF.read_bytes(), "text/plain")},
    )
    vid = up.json()["variants"][0]["id"]
    interp = client.post(
        f"/api/clinical/variants/{vid}/interpret?patient_id={pid}",
        headers=_h(doc),
    )
    assert interp.status_code == 200
    assert interp.json()["observation_status"] == "PATIENT OBSERVED VARIANT"
    lab, _ = _signup(client, "lab-rep@ex.test", "lab_technician")
    seen = client.get("/api/clinical/patients", headers=_h(lab)).json()
    assert any(p["id"] == pid for p in seen)
    patched = client.patch(
        f"/api/clinical/patients/{pid}/report",
        headers=_h(lab),
        json={"lab_notes": "reviewed by laboratory", "review_status": "REVIEWED"},
    )
    assert patched.status_code == 200, patched.text
    payload = patched.json()["payload"]
    assert payload["lab_review"]["notes"] == "reviewed by laboratory"
    doctor_view = client.get(f"/api/clinical/patients/{pid}/report", headers=_h(doc)).json()
    assert doctor_view["payload"]["lab_review"]["status"] == "REVIEWED"


def test_workup_result_is_visible_to_patient_and_doctor(client):
    doc, _ = _signup(client, "doc-snap@ex.test", "doctor")
    pat, _, registered = _patient_account(client, "snap-pat@ex.test")
    attached = _workup(client, doc, registered["identifier"], diagnosis="snap-case")
    pid = attached["patient"]["id"]
    result = client.post("/api/workup", json={
        "variant_id": "VAR-BRCA1-5266DUP",
        "history": {"consent_confirmed": True},
        "subject_ref": registered["identifier"],
    })
    assert result.status_code == 200, result.text
    saved = client.post(
        f"/api/clinical/patients/{pid}/workup-result",
        headers=_h(doc),
        json=result.json(),
    )
    assert saved.status_code == 200, saved.text
    assert saved.json()["workup"]["gene"] == "BRCA1"
    bundle = client.get(f"/api/clinical/patients/{pid}", headers=_h(doc)).json()
    assert bundle["workup"]["hgvs_c"] == "c.5266dupC"
    assert bundle["workup"]["payload"]["acmg"]["classification"]
    me = client.get("/api/patient/me", headers=_h(pat)).json()
    assert me["workup"]["patient_id"] == pid
    assert me["workup"]["final_classification"]
    assert me["workup"]["payload"]["stages"]
    assert "payload_json" not in me["workup"]
    fetched = client.get(f"/api/clinical/patients/{pid}/workup-result", headers=_h(pat))
    assert fetched.status_code == 200
    assert fetched.json()["payload"]["reconciliation"]["final_classification"]
    assert me["reconciliations"]


def test_curated_catalog_is_labeled_candidate(client):
    token, _ = _signup(client, "doc-cur@ex.test", "doctor")
    r = client.get("/api/clinical/curated?gene=BRCA1", headers=_h(token))
    assert r.status_code == 200
    body = r.json()
    assert body["kind"] == "CANDIDATE"
    assert "NOT CONFIRMED IN PATIENT" in body["disclaimer"]
    if body["items"]:
        assert body["items"][0]["source_type"] == "CURATED_DATASET"
