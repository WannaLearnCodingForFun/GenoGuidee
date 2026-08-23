"""Patient identity: signup issues the only Patient ID; doctors attach to it."""
from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

REPO = Path(__file__).resolve().parents[1]
MINI_VCF = REPO / "tests" / "data" / "mini.vcf"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("GENOGUIDE_CLINICAL_DB", str(tmp_path / "clinical.db"))
    monkeypatch.setenv("GENOGUIDE_SECRET_KEY", "test-secret")
    from app.main import app
    with TestClient(app) as c:
        yield c


def _signup(client: TestClient, email: str, role: str, password: str = "secret12", **extra):
    r = client.post("/api/auth/signup", json={
        "email": email, "password": password, "full_name": email.split("@")[0],
        "role": role, **extra,
    })
    assert r.status_code == 200, r.text
    return r.json()["token"], r.json()["user"], r.json()


def _h(token: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {token}"}


def _workup(client, token, identifier, diagnosis="case"):
    r = client.post("/api/clinical/workup", headers=_h(token), json={
        "age": 40, "sex": "F", "diagnosis": diagnosis,
        "consent_confirmed": True,
        "patient_identifier": identifier,
    })
    assert r.status_code == 200, r.text
    return r.json()


def test_patient_signup_issues_the_only_patient_id(client):
    token, user, body = _signup(client, "self@ex.test", "patient")
    patient = body["patient"]
    assert patient["uuid"]
    assert patient["identifier"].startswith("PAT-")
    assert patient["id"] != patient["uuid"]
    assert patient["user_id"] == user["id"]
    assert patient["account_status"] == "active"
    linked = client.get("/api/patient/me", headers=_h(token)).json()
    assert linked["linked"] is True
    assert linked["patient"]["identifier"] == patient["identifier"]


def test_doctor_cannot_mint_a_patient_id(client):
    doc, _, _ = _signup(client, "doc-mint@ex.test", "doctor")
    missing = client.post("/api/clinical/workup", headers=_h(doc), json={
        "age": 40, "diagnosis": "no-id", "consent_confirmed": True,
    })
    assert missing.status_code == 422
    unknown = client.post("/api/clinical/workup", headers=_h(doc), json={
        "age": 40, "diagnosis": "ghost", "consent_confirmed": True,
        "patient_identifier": "PAT-2026-999999",
    })
    assert unknown.status_code == 404


def test_doctor_workup_uses_the_patients_signup_id(client):
    doc, _, _ = _signup(client, "doc-a@ex.test", "doctor")
    pat_token, user, body = _signup(client, "invitee@ex.test", "patient")
    ident = body["patient"]["identifier"]
    attached = _workup(client, doc, ident, "identity-case")
    assert attached["patient"]["id"] == body["patient"]["id"]
    assert attached["patient"]["identifier"] == ident
    assert attached["patient"]["user_id"] == user["id"]
    assert attached["invitation"] is None
    listed = client.get("/api/clinical/patients", headers=_h(doc)).json()
    assert any(p["id"] == body["patient"]["id"] for p in listed)
    me = client.get("/api/patient/me", headers=_h(pat_token)).json()
    assert me["patient"]["id"] == body["patient"]["id"]
    assert me["patient"]["diagnosis"] == "identity-case"


def test_lookup_confirms_registered_patient(client):
    doc, _, _ = _signup(client, "doc-look@ex.test", "doctor")
    _, _, body = _signup(client, "look-pat@ex.test", "patient")
    found = client.get(
        f"/api/clinical/patient-lookup?identifier={body['patient']['identifier']}",
        headers=_h(doc),
    )
    assert found.status_code == 200
    assert found.json()["id"] == body["patient"]["id"]
    assert found.json()["email"] == "look-pat@ex.test"
    missing = client.get(
        "/api/clinical/patient-lookup?identifier=PAT-0000-000000",
        headers=_h(doc),
    )
    assert missing.status_code == 404


def test_doctor_b_cannot_see_or_upload_for_doctor_a_patient(client):
    doc_a, _, _ = _signup(client, "doc-a2@ex.test", "doctor")
    _, _, body = _signup(client, "a-only@ex.test", "patient")
    created = _workup(client, doc_a, body["patient"]["identifier"], "a-only")
    pid = created["patient"]["id"]
    doc_b, _, _ = _signup(client, "doc-b2@ex.test", "doctor")
    assert all(p["id"] != pid for p in client.get("/api/clinical/patients", headers=_h(doc_b)).json())
    denied = client.get(f"/api/clinical/patients/{pid}", headers=_h(doc_b))
    assert denied.status_code == 403
    up = client.post(
        "/api/clinical/uploads",
        headers=_h(doc_b),
        data={"patient_id": str(pid)},
        files={"file": ("mini.vcf", MINI_VCF.read_bytes(), "text/plain")},
    )
    assert up.status_code == 403


def test_patient_idor_on_patient_report_and_upload(client):
    doc, _, _ = _signup(client, "doc-idor@ex.test", "doctor")
    pat_a, _, a = _signup(client, "pa@ex.test", "patient")
    pat_b, _, b = _signup(client, "pb@ex.test", "patient")
    _workup(client, doc, a["patient"]["identifier"], "patient-a")
    _workup(client, doc, b["patient"]["identifier"], "patient-b")
    up = client.post(
        "/api/clinical/uploads",
        headers=_h(doc),
        data={"patient_id": str(b["patient"]["id"])},
        files={"file": ("mini.vcf", MINI_VCF.read_bytes(), "text/plain")},
    )
    assert up.status_code == 200
    vid = up.json()["variants"][0]["id"]
    interp = client.post(
        f"/api/clinical/variants/{vid}/interpret?patient_id={b['patient']['id']}",
        headers=_h(doc),
    )
    assert interp.status_code == 200
    report = client.get(
        f"/api/clinical/patients/{b['patient']['id']}/report", headers=_h(doc),
    ).json()
    assert client.get(
        f"/api/clinical/patients/{b['patient']['id']}", headers=_h(pat_a),
    ).status_code == 403
    assert client.get(
        f"/api/clinical/reports/{report['id']}", headers=_h(pat_a),
    ).status_code == 403
    assert client.get(
        f"/api/clinical/uploads/{up.json()['id']}", headers=_h(pat_a),
    ).status_code == 403
    assert client.get(
        f"/api/clinical/reports/{report['id']}", headers=_h(pat_b),
    ).status_code == 200


def test_lab_sees_all_and_updates_report_with_audit(client):
    doc, _, _ = _signup(client, "doc-lab2@ex.test", "doctor")
    _, _, body = _signup(client, "lab-visible@ex.test", "patient")
    created = _workup(client, doc, body["patient"]["identifier"], "lab-visible")
    lab, _, _ = _signup(client, "lab-all@ex.test", "lab_technician")
    rows = client.get("/api/clinical/patients", headers=_h(lab)).json()
    assert any(p["id"] == created["patient"]["id"] for p in rows)
    up = client.post(
        "/api/clinical/uploads",
        headers=_h(lab),
        data={"patient_id": str(created["patient"]["id"])},
        files={"file": ("mini.vcf", MINI_VCF.read_bytes(), "text/plain")},
    )
    assert up.status_code == 200
    vid = up.json()["variants"][0]["id"]
    assert client.post(
        f"/api/clinical/variants/{vid}/interpret?patient_id={created['patient']['id']}",
        headers=_h(lab),
    ).status_code == 200
    patched = client.patch(
        f"/api/clinical/patients/{created['patient']['id']}/report",
        headers=_h(lab),
        json={"lab_notes": "lab reviewed", "review_status": "REVIEWED"},
    )
    assert patched.status_code == 200
    audit = client.get(
        f"/api/clinical/patients/{created['patient']['id']}/audit", headers=_h(lab),
    ).json()
    assert any(e["action"] == "report_updated" for e in audit["events"])


def test_patient_upload_binds_to_own_record(client):
    token, _, body = _signup(client, "own-up2@ex.test", "patient")
    up = client.post(
        "/api/clinical/uploads",
        headers=_h(token),
        files={"file": ("mini.vcf", MINI_VCF.read_bytes(), "text/plain")},
    )
    assert up.status_code == 200
    assert up.json()["patient_id"] == body["patient"]["id"]


def test_patient_login_requires_matching_patient_id(client):
    token, user, body = _signup(client, "login-pat@ex.test", "patient")
    ident = body["patient"]["identifier"]
    missing = client.post("/api/auth/login", json={
        "email": "login-pat@ex.test", "password": "secret12",
    })
    assert missing.status_code == 401
    wrong = client.post("/api/auth/login", json={
        "email": "login-pat@ex.test", "password": "secret12", "patient_id": "PAT-0000-999999",
    })
    assert wrong.status_code == 401
    ok = client.post("/api/auth/login", json={
        "email": "login-pat@ex.test", "password": "secret12", "patient_id": ident,
    })
    assert ok.status_code == 200
    assert ok.json()["patient"]["id"] == body["patient"]["id"]
    assert user["id"] == ok.json()["user"]["id"]
    assert token


def test_patient_ids_are_unique(client):
    _, _, a = _signup(client, "uniq-a@ex.test", "patient")
    _, _, b = _signup(client, "uniq-b@ex.test", "patient")
    assert a["patient"]["identifier"] != b["patient"]["identifier"]
    assert a["patient"]["uuid"] != b["patient"]["uuid"]


def test_integrity_endpoint(client):
    doc, _, _ = _signup(client, "doc-intg@ex.test", "doctor")
    r = client.get("/api/system/integrity", headers=_h(doc))
    assert r.status_code == 200
    body = r.json()
    assert "patients_missing_uuid" in body
    assert body["patients_missing_uuid"] == 0
