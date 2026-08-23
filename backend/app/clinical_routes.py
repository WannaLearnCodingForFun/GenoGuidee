"""Authenticated clinical API — persisted patients, uploads, interpretations."""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field

from . import clinical_db as DB
from . import ingest
from .local_auth import hash_password, issue_token, require_user, verify_password

log = logging.getLogger("genoguide")
router = APIRouter(prefix="/api", tags=["clinical"])

ROLES = {"doctor", "patient", "lab_technician"}


class SignupIn(BaseModel):
    email: str
    password: str = Field(min_length=6)
    full_name: str
    role: str
    lab_name: Optional[str] = None
    certification_id: Optional[str] = None
    invite_token: Optional[str] = None


class ClaimIn(BaseModel):
    invite_token: str


class LoginIn(BaseModel):
    email: str
    password: str
    patient_id: Optional[str] = None


class WorkupIn(BaseModel):
    age: Optional[int] = None
    sex: Optional[str] = None
    diagnosis: Optional[str] = None
    presenting_complaint: Optional[str] = None
    phenotypes: list[str] = []
    prior_conditions: list[str] = []
    medications: list[str] = []
    family_history_positive: bool = False
    family_details: Optional[str] = None
    consent_confirmed: bool = False
    variant_id: Optional[int] = None
    patient_id: Optional[int] = None
    patient_identifier: Optional[str] = None
    patient_email: Optional[str] = None
    patient_full_name: Optional[str] = None


class AssignIn(BaseModel):
    patient_id: Optional[int] = None


class AssignUserIn(BaseModel):
    user_id: int


class VerifyIn(BaseModel):
    block_id: int


class CuratedInterpretIn(BaseModel):
    chromosome: str
    position: int
    reference: str
    alternate: str
    gene: Optional[str] = None
    patient_id: Optional[int] = None


class ReportPatch(BaseModel):
    lab_notes: Optional[str] = None
    review_status: Optional[str] = None


def _need_role(user: dict[str, Any], *roles: str) -> None:
    if user["role"] not in roles:
        raise HTTPException(403, f"This action is limited to: {', '.join(roles)}.")


def _deny_patient() -> None:
    raise HTTPException(403, "You do not have access to this patient.")


def _require_patient(user: dict[str, Any], patient_id: int) -> None:
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()


@router.post("/auth/signup")
def signup(body: SignupIn) -> dict[str, Any]:
    if body.role not in ROLES:
        raise HTTPException(422, "role must be doctor, patient, or lab_technician")
    if DB.get_user_by_email(body.email):
        raise HTTPException(409, "email already registered")
    user = DB.create_user(body.email, hash_password(body.password), body.role, body.full_name)
    claimed = None
    if body.role == "patient":
        claimed = DB.create_patient(
            created_by=user["id"], user_id=user["id"], age=None, sex=None,
            diagnosis=None, presenting_complaint=None, consent_confirmed=False,
            email=body.email, full_name=body.full_name,
        )
        DB.assign_all_lab_technicians(claimed["id"])
        DB.audit(user["id"], claimed["id"], "patient_self_record", "patient", claimed["identifier"])
    elif body.role == "lab_technician":
        DB.assign_technician_to_existing_patients(user["id"])
    DB.audit(user["id"], None, "signup", "user", str(user["id"]), {"role": body.role})
    log.info("[AUTH] signup role=%s id=%s", body.role, user["id"])
    return {
        "token": issue_token(user),
        "user": DB.public_user(user),
        "patient": DB.public_patient(claimed) if claimed else None,
    }


@router.post("/auth/login")
def login(body: LoginIn) -> dict[str, Any]:
    user = DB.get_user_by_email(body.email)
    if not user or not verify_password(body.password, user["password_hash"]):
        raise HTTPException(401, "invalid email or password")
    linked = DB.patient_for_user(user) if user["role"] == "patient" else None
    if user["role"] == "patient":
        supplied = (body.patient_id or "").strip()
        if not supplied:
            raise HTTPException(401, "Patient ID is required for patient login.")
        if not linked or (
            supplied != linked.get("identifier") and supplied != linked.get("uuid")
        ):
            raise HTTPException(401, "Email, patient ID, and password do not match.")
    DB.audit(user["id"], linked["id"] if linked else None, "login", "user", str(user["id"]))
    return {
        "token": issue_token(user),
        "user": DB.public_user(user),
        "patient": DB.public_patient(linked) if linked else None,
    }


@router.get("/auth/me")
def me(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    body = DB.public_user(user)
    if user["role"] == "patient":
        own = DB.patient_for_user(user)
        body["patient"] = DB.public_patient(own) if own else None
        body["linked"] = bool(own and own.get("user_id") == user["id"])
    return body


@router.get("/patient/me")
def patient_me(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    _need_role(user, "patient")
    own = DB.patient_for_user(user)
    if not own:
        return {
            "linked": False,
            "message": "Your patient record exists, but your account has not been linked yet.",
            "patient": None,
        }
    workspace = DB.patient_workspace(int(own["id"]))
    return workspace


@router.post("/patient/claim")
def patient_claim(body: ClaimIn, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    _need_role(user, "patient")
    try:
        patient = DB.claim_invitation(body.invite_token, user)
    except KeyError as exc:
        raise HTTPException(404, "Invitation was not found.") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    DB.audit(user["id"], patient["id"], "patient_claimed", "patient", patient["uuid"])
    return {"linked": True, "patient": DB.public_patient(patient)}


@router.get("/patient/invite/{token}")
def peek_invite(token: str) -> dict[str, Any]:
    row = DB.peek_invitation(token)
    if not row:
        raise HTTPException(404, "Invitation was not found.")
    if row.get("used_at"):
        raise HTTPException(422, "invitation already used")
    if float(row["expires_at"]) < __import__("time").time():
        raise HTTPException(422, "invitation expired")
    return {
        "valid": True,
        "patient_code": row["identifier"],
        "patient_uuid": row["uuid"],
        "account_status": row["account_status"],
    }


@router.get("/clinical/overview")
def overview(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    patients = DB.list_patients_for(user)
    uploads = DB.list_uploads_for(user)
    return {
        "user": DB.public_user(user),
        "patients": patients,
        "uploads": uploads,
        "pending_signoffs": sum(1 for p in patients if not p.get("consent_confirmed")),
        "counts": DB.counts(),
    }


@router.get("/clinical/patients")
def patients(user: dict[str, Any] = Depends(require_user)) -> list[dict[str, Any]]:
    return DB.list_patients_for(user)


@router.get("/clinical/patient-lookup")
def patient_lookup(identifier: str, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    _need_role(user, "doctor", "lab_technician")
    try:
        patient = DB.resolve_registered_patient(identifier)
    except KeyError as exc:
        raise HTTPException(
            404,
            "No patient account exists for this Patient ID. The patient must create an account first.",
        ) from exc
    except ValueError as exc:
        raise HTTPException(422, "This Patient ID is not linked to a patient account.") from exc
    return {
        "id": patient["id"],
        "identifier": patient["identifier"],
        "full_name": patient.get("full_name"),
        "email": patient.get("email"),
        "account_status": patient.get("account_status"),
    }


@router.get("/clinical/patients/{patient_id}")
def patient_detail(patient_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    return DB.patient_bundle(patient_id)


@router.get("/clinical/patients/{patient_id}/graph")
def patient_graph(patient_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    return DB.get_graph(patient_id)


@router.get("/clinical/patients/{patient_id}/provenance")
def patient_provenance(patient_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    blocks = DB.list_provenance(patient_id)
    return {
        "patient_id": patient_id,
        "blocks": blocks,
        "block_count": len(blocks),
        "interpretations": sum(1 for b in blocks if b["event_type"] == "INTERPRETATION_CREATED"),
    }


@router.get("/clinical/patients/{patient_id}/consent")
def patient_consent(patient_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    p = DB.get_patient(patient_id)
    consents = [b for b in DB.list_provenance(patient_id) if b["event_type"] == "CONSENT_RECORDED"]
    return {
        "patient_id": p["identifier"],
        "state": "granted" if p["consent_confirmed"] else "not_recorded",
        "records": consents,
    }


@router.get("/clinical/patients/{patient_id}/audit")
def patient_audit(patient_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    return {"patient_id": patient_id, "events": DB.list_audit(patient_id)}


@router.post("/clinical/workup")
def workup(body: WorkupIn, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    _need_role(user, "doctor")
    ident = (body.patient_identifier or "").strip()
    if ident:
        try:
            patient = DB.resolve_registered_patient(ident)
        except KeyError as exc:
            raise HTTPException(
                404,
                "No patient account exists for this Patient ID. The patient must create an account first.",
            ) from exc
        except ValueError as exc:
            raise HTTPException(422, "This Patient ID is not linked to a patient account.") from exc
    elif body.patient_id:
        if not DB.can_access_patient(user, body.patient_id):
            _deny_patient()
        patient = DB.get_patient(body.patient_id)
        if not patient.get("user_id"):
            raise HTTPException(422, "This Patient ID is not linked to a patient account.")
    else:
        raise HTTPException(
            422,
            "Patient ID is required. The patient must create an account first and share their Patient ID.",
        )

    pid = int(patient["id"])
    if not DB.can_access_patient(user, pid):
        DB.assign_user(pid, user["id"], "doctor")
        DB.audit(user["id"], pid, "patient_attached", "patient", patient["identifier"])
        log.info("[CLINICAL] doctor_attached %s -> %s", user["id"], patient["identifier"])

    patient = DB.update_patient(
        pid, age=body.age, sex=body.sex, diagnosis=body.diagnosis,
        presenting_complaint=body.presenting_complaint,
        consent_confirmed=body.consent_confirmed,
        email=body.patient_email or patient.get("email"),
        full_name=body.patient_full_name or patient.get("full_name"),
    )
    DB.replace_history(
        pid, phenotypes=body.phenotypes, prior_conditions=body.prior_conditions,
        medications=body.medications, family_details=body.family_details,
        family_positive=body.family_history_positive,
    )
    if body.consent_confirmed:
        DB.append_provenance(patient_id=pid, event_type="CONSENT_RECORDED",
                             function_name="recordConsent",
                             payload={"patient": patient["identifier"], "consent": True})
    DB.append_provenance(patient_id=pid, event_type="CLINICAL_WORKUP_SAVED",
                         function_name="saveWorkup",
                         payload={"patient": patient["identifier"], "diagnosis": body.diagnosis})
    DB.audit(user["id"], pid, "clinical_workup_saved", "patient", patient["identifier"])
    _rebuild_graph(pid)

    interpretation = None
    if body.variant_id:
        interpretation = _interpret_variant(body.variant_id, pid, user)

    return {
        "patient": DB.public_patient(DB.get_patient(pid)),
        "bundle": DB.patient_bundle(pid),
        "graph": DB.get_graph(pid),
        "interpretation": interpretation,
        "invitation": None,
    }


@router.post("/clinical/patients/{patient_id}/workup-result")
def save_workup_result(
    patient_id: int,
    body: dict[str, Any],
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    _need_role(user, "doctor")
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    if not isinstance(body, dict) or not (body.get("variant") or body.get("acmg")):
        raise HTTPException(422, "Workup result is incomplete.")
    snap = DB.save_workup_snapshot(patient_id, body)
    patient = DB.get_patient(patient_id)
    DB.append_provenance(
        patient_id=patient_id, event_type="CLINICAL_WORKUP_RESULT_SAVED",
        function_name="saveWorkupResult",
        payload={
            "patient": patient["identifier"],
            "gene": snap.get("gene"),
            "hgvs_c": snap.get("hgvs_c"),
            "final_classification": snap.get("final_classification"),
        },
    )
    DB.audit(user["id"], patient_id, "workup_result_saved", "workup", str(snap.get("id")))
    return {"ok": True, "workup": snap}


@router.get("/clinical/patients/{patient_id}/workup-result")
def get_workup_result(patient_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    snap = DB.latest_workup_snapshot(patient_id)
    if not snap:
        raise HTTPException(404, "No clinical workup result is stored for this patient.")
    return snap


@router.post("/clinical/uploads")
async def upload_file(
    file: UploadFile = File(...),
    patient_id: Optional[int] = Form(default=None),
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    if user["role"] == "patient":
        own = DB.patient_for_user(user)
        if not own:
            raise HTTPException(
                422,
                "Patient identity could not be determined from the authenticated session.",
            )
        patient_id = int(own["id"])
    elif patient_id is not None and not DB.can_access_patient(user, patient_id):
        _deny_patient()
    data = await file.read()
    try:
        result = ingest.ingest_bytes(
            user_id=user["id"], filename=file.filename or "upload",
            data=data, patient_id=patient_id,
        )
    except ValueError as exc:
        status = 409 if "duplicate upload" in str(exc) else 422
        raise HTTPException(status, str(exc)) from exc
    DB.append_provenance(
        patient_id=patient_id, event_type="VCF_UPLOADED",
        function_name="uploadFile",
        payload={"filename": result["filename"], "sha256": result["sha256"],
                 "status": result["parsing_status"], "n": result["variant_count"]},
    )
    DB.audit(user["id"], patient_id, "vcf_uploaded", "upload", str(result["id"]))
    return result


@router.get("/clinical/uploads")
def uploads(user: dict[str, Any] = Depends(require_user)) -> list[dict[str, Any]]:
    return DB.list_uploads_for(user)


@router.get("/clinical/uploads/{upload_id}")
def upload_detail(upload_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    up = DB.get_upload(upload_id)
    if not DB.can_access_upload(user, up):
        raise HTTPException(403, "You do not have access to this upload.")
    variants = DB.list_variants(upload_id, page=1, page_size=500)
    return {**up, "variants": variants["items"]}


@router.post("/clinical/uploads/{upload_id}/assign")
def assign_upload(upload_id: int, body: AssignIn, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    _need_role(user, "doctor", "lab_technician")
    up = DB.get_upload(upload_id)
    if body.patient_id is not None and not DB.can_access_patient(user, body.patient_id):
        _deny_patient()
    DB.update_upload(upload_id, patient_id=body.patient_id)
    DB.append_provenance(
        patient_id=body.patient_id, event_type="VCF_ASSIGNED",
        function_name="assignUpload",
        payload={"upload_id": upload_id, "patient_id": body.patient_id},
    )
    if body.patient_id:
        DB.record_observations_for_upload(upload_id, body.patient_id)
        _rebuild_graph(body.patient_id)
    return DB.get_upload(upload_id)


@router.get("/clinical/patients/{patient_id}/candidates")
def phenotype_candidates(patient_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    """Phenotype-prioritized ClinVar candidates — NOT observed genotype."""
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    bundle = DB.patient_bundle(patient_id)
    terms = [p["phenotype"] for p in bundle["phenotypes"] if p.get("phenotype")]
    if not terms:
        return {
            "patient_id": patient_id,
            "kind": "CANDIDATE",
            "disclaimer": "CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT",
            "items": [],
            "reason": "no phenotypes on this patient",
        }
    from pathlib import Path
    import pandas as pd
    repo = Path(__file__).resolve().parents[2]
    hpo = repo / "research/data/raw/hpo/genes_to_phenotype.txt"
    clin = repo / "research/data/processed/clinvar_grch38.parquet"
    genes: set[str] = set()
    if hpo.exists():
        try:
            table = pd.read_csv(hpo, sep="\t", comment="#", dtype=str)
            blob = " ".join(t.lower() for t in terms)
            gene_col = next((c for c in table.columns if "gene" in c.lower() and "id" not in c.lower()), None)
            name_col = next((c for c in table.columns if "hpo" in c.lower() and "name" in c.lower()), None)
            if gene_col and name_col:
                mask = table[name_col].fillna("").str.lower().apply(lambda s: any(t.lower() in s for t in terms) or s in blob)
                genes = set(table.loc[mask, gene_col].dropna().astype(str).head(40))
        except Exception as exc:  # noqa: BLE001
            return {"patient_id": patient_id, "kind": "CANDIDATE", "items": [], "reason": str(exc)}
    items = []
    if genes and clin.exists():
        import duckdb
        con = duckdb.connect()
        glist = ",".join("'" + g.replace("'", "") + "'" for g in list(genes)[:25])
        q = f"""
            SELECT gene, chrom, pos, ref, alt, label, review_status
            FROM '{clin}'
            WHERE gene IN ({glist}) AND label IN ('pathogenic','likely_pathogenic')
            LIMIT 25
        """
        try:
            rows = con.execute(q).fetchall()
            cols = ["gene", "chrom", "pos", "ref", "alt", "label", "review_status"]
            for row in rows:
                rec = dict(zip(cols, row))
                rec["kind"] = "CANDIDATE"
                rec["disclaimer"] = "CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT"
                rec["source"] = "ClinVar + HPO phenotype match"
                items.append(rec)
        except Exception as exc:  # noqa: BLE001
            return {"patient_id": patient_id, "kind": "CANDIDATE", "items": [], "reason": str(exc)}
    return {
        "patient_id": patient_id,
        "kind": "CANDIDATE",
        "disclaimer": "CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT. These were not observed in an uploaded file.",
        "phenotypes": terms,
        "genes": sorted(genes),
        "items": items,
        "source": "HPO genes_to_phenotype + ClinVar GRCh38",
    }


@router.get("/clinical/variants")
def variants(page: int = 1, page_size: int = 50, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    return DB.list_variants_for(user, page=page, page_size=min(page_size, 200))


@router.get("/clinical/patients/{patient_id}/report")
def patient_report(patient_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    report = DB.latest_report(patient_id)
    if not report:
        raise HTTPException(404, "no report for this patient yet")
    return report


@router.get("/clinical/reports/{report_id}")
def report_by_id(report_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    try:
        report = DB.get_report(report_id)
    except KeyError as exc:
        raise HTTPException(404, "report not found") from exc
    if not DB.can_access_report(user, report):
        raise HTTPException(403, "You do not have access to this report.")
    return report


@router.post("/clinical/patients/{patient_id}/invite")
def invite_patient(patient_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    _need_role(user, "doctor")
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    patient = DB.get_patient(patient_id)
    if patient.get("user_id"):
        raise HTTPException(409, "This patient account is already linked.")
    token = DB.create_invitation(patient_id, user["id"])
    DB.audit(user["id"], patient_id, "patient_invited", "invitation", patient.get("uuid"))
    return {
        "patient": DB.public_patient(patient),
        "invitation": {
            "token": token,
            "account_status": "invited",
            "signup_path": f"/signup/patient?invite={token}",
        },
    }


@router.patch("/clinical/patients/{patient_id}/report")
def patch_report(
    patient_id: int,
    body: ReportPatch,
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    _need_role(user, "lab_technician")
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    updated = DB.append_report_review(
        patient_id,
        reviewed_by=user["id"],
        lab_notes=body.lab_notes,
        review_status=body.review_status,
    )
    DB.audit(user["id"], patient_id, "report_updated", "report", str(updated["id"]))
    DB.append_provenance(
        patient_id=patient_id, event_type="REPORT_UPDATED",
        function_name="updateReport",
        payload={"report_id": updated["id"], "status": body.review_status},
    )
    return DB.latest_report(patient_id) or updated


@router.get("/clinical/patients/{patient_id}/longitudinal")
def patient_longitudinal(patient_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    return DB.longitudinal_for_patient(patient_id)


@router.get("/clinical/curated")
def curated_variants(
    gene: Optional[str] = None,
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    """ClinVar catalog search. These are NOT patient-observed genotypes."""
    _need_role(user, "doctor", "lab_technician")
    if not gene or not gene.strip():
        return {
            "kind": "CANDIDATE",
            "disclaimer": "CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT",
            "items": [],
            "reason": "provide a gene symbol to search the curated ClinVar catalog",
        }
    from pathlib import Path
    clin = Path(__file__).resolve().parents[2] / "research/data/processed/clinvar_grch38.parquet"
    if not clin.exists():
        return {
            "kind": "CANDIDATE",
            "disclaimer": "CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT",
            "items": [],
            "reason": "ClinVar processed parquet is not available locally",
        }
    import duckdb
    safe = gene.strip().upper().replace("'", "")
    try:
        con = duckdb.connect()
        rows = con.execute(
            f"""
            SELECT gene, chrom, pos, ref, alt, label, review_status
            FROM '{clin}'
            WHERE upper(gene) = '{safe}'
            LIMIT 40
            """
        ).fetchall()
    except Exception as exc:  # noqa: BLE001
        return {
            "kind": "CANDIDATE",
            "disclaimer": "CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT",
            "items": [],
            "reason": "Variant annotation unavailable.",
            "detail": str(exc),
        }
    items = []
    for row in rows:
        items.append({
            "gene": row[0], "chrom": row[1], "pos": row[2], "ref": row[3], "alt": row[4],
            "label": row[5], "review_status": row[6],
            "kind": "CANDIDATE",
            "source_type": "CURATED_DATASET",
            "disclaimer": "CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT",
        })
    return {
        "kind": "CANDIDATE",
        "disclaimer": "CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT",
        "gene": safe,
        "items": items,
        "source": "ClinVar GRCh38 processed catalog",
    }


@router.post("/clinical/curated/interpret")
def interpret_curated(
    body: CuratedInterpretIn,
    user: dict[str, Any] = Depends(require_user),
) -> dict[str, Any]:
    _need_role(user, "doctor", "lab_technician")
    if body.patient_id and not DB.can_access_patient(user, body.patient_id):
        _deny_patient()
    catalog = DB.ensure_curated_catalog(user["id"])
    chrom = body.chromosome.replace("chr", "").upper()
    rec = {
        "chromosome": chrom,
        "position": body.position,
        "reference": body.reference.upper(),
        "alternate": body.alternate.upper(),
        "genome_build": "GRCh38",
        "gene": body.gene,
        "normalized_variant": f"GRCh38:{chrom}:{body.position}:{body.reference.upper()}>{body.alternate.upper()}",
        "source_type": "CURATED_DATASET",
    }
    vid = DB.insert_variant(catalog, rec)
    result = _interpret_variant(vid, body.patient_id, user)
    result["observation_status"] = "CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT"
    result["source_type"] = "CURATED_DATASET"
    return result


@router.post("/clinical/patients/{patient_id}/assign")
def assign_patient(patient_id: int, body: AssignUserIn, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    _need_role(user, "doctor")
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    target = DB.get_user(int(body.user_id))
    DB.assign_user(patient_id, target["id"], target["role"])
    DB.audit(user["id"], patient_id, "patient_assigned", "user", str(target["id"]))
    return DB.patient_bundle(patient_id)


@router.post("/clinical/patients/{patient_id}/consent/revoke")
def revoke_consent(patient_id: int, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    _need_role(user, "doctor")
    if not DB.can_access_patient(user, patient_id):
        _deny_patient()
    DB.update_patient(patient_id, consent_confirmed=False)
    p = DB.get_patient(patient_id)
    DB.append_provenance(
        patient_id=patient_id, event_type="CONSENT_REVOKED",
        function_name="revokeConsent",
        payload={"patient": p["identifier"]},
    )
    DB.audit(user["id"], patient_id, "consent_revoked", "patient", p["identifier"])
    return {"patient_id": p["identifier"], "state": "revoked"}


@router.post("/clinical/variants/{variant_id}/interpret")
def interpret(variant_id: int, patient_id: Optional[int] = None,
              user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    _need_role(user, "doctor", "lab_technician")
    try:
        variant = DB.get_variant(variant_id)
    except KeyError as exc:
        raise HTTPException(404, "variant not found") from exc
    if not DB.can_access_variant(user, variant):
        raise HTTPException(403, "You do not have access to this variant.")
    if patient_id and not DB.can_access_patient(user, patient_id):
        _deny_patient()
    return _interpret_variant(variant_id, patient_id, user)


@router.post("/clinical/provenance/verify")
def verify(body: VerifyIn, user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    result = DB.verify_block(body.block_id)
    pid = result["record"].get("patient_id")
    if pid and not DB.can_access_patient(user, int(pid)):
        _deny_patient()
    extra = DB.append_provenance(
        patient_id=result["record"].get("patient_id"),
        event_type="INTERPRETATION_VERIFIED",
        function_name="verifyInterpretation",
        payload={"block_id": body.block_id, "status": result["status"]},
    )
    DB.audit(user["id"], result["record"].get("patient_id"), "interpretation_verified",
             "provenance", str(body.block_id))
    result["verification_block"] = extra
    return result


@router.get("/ml/health")
def ml_health() -> dict[str, Any]:
    from .services.ml_predict import load_production_bundle, smoke_inference
    from .services import esm2_service
    smoke = smoke_inference()
    bundle = load_production_bundle()
    if not smoke.get("ok") or bundle is None:
        return {"status": "not_configured", "model": None, "detail": smoke.get("detail")}
    meta = bundle.get("meta") or {}
    return {
        "status": "ready",
        "model": meta.get("model_id"),
        "version": meta.get("model_id"),
        "trained_on": "ClinVar GRCh38 gene-disjoint tabular matrix",
        "validation_metrics": meta.get("metrics_gene_disjoint_test"),
        "calibrated": True,
        "esm2": esm2_service.represent(None, None),
        "inference": smoke,
    }


@router.get("/therapy/health")
def therapy_health() -> dict[str, Any]:
    from .services.drug_recommendation import connector_status
    st = connector_status()
    if st.get("local_engine") or st.get("enabled"):
        return {"status": "ready", **st}
    return {"status": "not_configured", **st}


@router.get("/system/health")
def system_health() -> dict[str, Any]:
    from .health import assemble_health
    body = assemble_health(detailed=True)
    for key, component in body.get("components", {}).items():
        body[key] = str(component.get("status", "ERROR")).lower()
    return body


@router.get("/system/integrity")
def system_integrity(user: dict[str, Any] = Depends(require_user)) -> dict[str, Any]:
    _need_role(user, "doctor", "lab_technician")
    return DB.integrity_report()


def _interpret_variant(variant_id: int, patient_id: int | None, user: dict[str, Any]) -> dict[str, Any]:
    v = DB.get_variant(variant_id)
    acmg: dict[str, Any]
    ml: dict[str, Any]
    if v.get("normalized_variant") and v.get("chromosome") and v.get("position"):
        from .schemas.variant import CanonicalVariant, GenomeBuild
        from .services.interpret import InterpretationService
        cv = CanonicalVariant.from_vcf_fields(
            GenomeBuild.GRCH38, str(v["chromosome"]), int(v["position"]),
            str(v["reference"]), str(v["alternate"]), gene=v.get("gene"),
            hgvs_p=v.get("hgvs_p"),
        )
        obj = InterpretationService().interpret(cv)
        dumped = obj.model_dump(mode="json")
        acmg_obj = dumped.get("acmg_interpretation") or {}
        acmg = {
            "classification": acmg_obj.get("classification"),
            "criteria": acmg_obj.get("criteria") or [],
            "met_criteria": acmg_obj.get("met_criteria") or [],
            "rule_note": acmg_obj.get("combining_note") or acmg_obj.get("rule_note"),
            "framework": acmg_obj.get("rule_version") or "ACMG/AMP 2015",
        }
        ml_obj = dumped.get("ml_prediction") or {}
        from .services.ml_predict import finalize_prediction
        probs = ml_obj.get("calibrated_probabilities") or ml_obj.get("probabilities") or {}
        if probs:
            ml = finalize_prediction(
                {str(k): float(v) for k, v in probs.items()},
                model_name=str(ml_obj.get("model_id") or "genoguide-xgboost-clinvar"),
                model_version=str(ml_obj.get("model_id") or ml_obj.get("model_version") or "unknown"),
                dataset_version="research/data/processed/training_dataset.parquet",
                feature_schema_version="clinvar-tabular-v1",
                calibrated=bool(ml_obj.get("calibrated")),
            )
            seq = dumped.get("sequence_model") or {}
            ml["esm2"] = seq
        else:
            ml = {
                "top_class": None,
                "predicted_class": None,
                "confidence": None,
                "probabilities": {},
                "model_version": ml_obj.get("model_id"),
                "engine": "not_run",
                "model_status": "not_run",
            }
        rec_obj = dumped.get("reconciliation") or {}
        recon = {
            "status": rec_obj.get("status"),
            "final_classification": rec_obj.get("final_classification") or acmg.get("classification"),
            "ml_classification": ml.get("top_class"),
            "acmg_classification": acmg.get("classification"),
            "confidence": rec_obj.get("confidence"),
            "note": rec_obj.get("note"),
            "authority": rec_obj.get("authority") or "ACMG/AMP (ML never overrides)",
            "disagreement": rec_obj.get("status") == "DISCORDANT",
        }
        try:
            ev = dumped.get("evidence") or {}
            DB.save_annotation(variant_id, {
                "clinvar_significance": (ev.get("clinvar") or {}).get("clinical_significance"),
                "review_status": (ev.get("clinvar") or {}).get("review_status"),
                "allele_frequency": (ev.get("gnomad") or {}).get("af"),
                "evidence_source": "ClinVar/local evidence store",
                "source_database": "ClinVar",
                **ev,
            })
        except Exception as exc:  # noqa: BLE001
            log.info("[ANNOTATION] skipped: %s", exc)
    else:
        acmg = {
            "classification": "NOT_EVALUABLE",
            "criteria": [],
            "met_criteria": [],
            "rule_note": (
                "Variant not present in local annotation database with genomic coordinates. "
                "ACMG was not evaluated and no classification was invented."
            ),
            "framework": "ACMG/AMP 2015",
        }
        ml = {
            "top_class": None,
            "confidence": None,
            "probabilities": {},
            "model_version": "not_run",
            "engine": "not_run",
            "note": "ML inference requires chromosome, position, REF, and ALT. No probability was invented.",
        }
        recon = {
            "status": "NOT_EVALUABLE",
            "final_classification": "NOT_EVALUABLE",
            "ml_classification": None,
            "acmg_classification": "NOT_EVALUABLE",
            "confidence": None,
            "note": "Model/ACMG disagreement is not applicable — both paths lacked evaluable evidence.",
            "authority": "ACMG/AMP (ML never overrides)",
        }
    conf = ml.get("confidence")
    if isinstance(conf, (int, float)):
        if conf >= 0.85:
            ml["calibration"] = "HIGH CONFIDENCE"
        elif conf >= 0.60:
            ml["calibration"] = "MEDIUM CONFIDENCE"
        else:
            ml["calibration"] = "LOW CONFIDENCE"
    DB.save_acmg(variant_id, patient_id, acmg)
    DB.save_ml(variant_id, ml)
    DB.save_reconciliation(variant_id, patient_id, recon)
    source_type = v.get("source_type") or "UPLOADED_VCF"
    observed = source_type != "CURATED_DATASET"
    observation_status = (
        "PATIENT OBSERVED VARIANT" if observed
        else "CANDIDATE VARIANT — NOT CONFIRMED IN PATIENT"
    )
    report = {
        "patient_id": patient_id,
        "variant": v,
        "ml": ml,
        "acmg": acmg,
        "reconciliation": recon,
        "model_version": ml.get("model_version"),
        "acmg_engine_version": acmg.get("framework"),
        "source_type": source_type,
        "observation_status": observation_status,
        "disclaimer": "Research prototype — clinical decision support requiring human review. Not a diagnosis.",
    }
    DB.save_report(patient_id, variant_id, report)
    if v.get("vcf_upload_id"):
        try:
            DB.update_upload(int(v["vcf_upload_id"]), analysis_status="COMPLETED")
        except Exception:  # noqa: BLE001
            pass
    DB.append_provenance(
        patient_id=patient_id, event_type="INTERPRETATION_CREATED",
        function_name="recordInterpretation",
        payload={"variant_id": variant_id, "final": recon.get("final_classification")},
    )
    if patient_id:
        _rebuild_graph(patient_id)
    log.info("[ACMG] interpretation variant=%s final=%s", variant_id, recon.get("final_classification"))
    return {
        "variant": v,
        "acmg": acmg,
        "ml": ml,
        "reconciliation": recon,
        "report": report,
        "source_type": source_type,
        "observation_status": observation_status,
    }


def _rebuild_graph(patient_id: int) -> None:
    bundle = DB.patient_bundle(patient_id)
    p = bundle["patient"]
    nodes = [
        {"id": f"patient:{p['id']}", "type": "Patient", "label": p["identifier"],
         "sublabel": p.get("diagnosis") or "no diagnosis"},
    ]
    edges = []
    if p.get("diagnosis"):
        nodes.append({"id": f"disease:{p['diagnosis']}", "type": "Disease",
                      "label": p["diagnosis"], "sublabel": "intake"})
        edges.append({"source": f"patient:{p['id']}", "target": f"disease:{p['diagnosis']}",
                      "relation": "HAS_DIAGNOSIS"})
    for ph in bundle["phenotypes"]:
        key = f"pheno:{ph['id']}"
        nodes.append({"id": key, "type": "Phenotype", "label": ph["phenotype"],
                      "sublabel": ph.get("hpo_id") or "intake"})
        edges.append({"source": f"patient:{p['id']}", "target": key, "relation": "HAS_PHENOTYPE"})
    for med in bundle["medications"]:
        key = f"med:{med['id']}"
        nodes.append({"id": key, "type": "Drug", "label": med["medication"], "sublabel": "intake"})
        edges.append({"source": f"patient:{p['id']}", "target": key, "relation": "TAKES"})
    for up in bundle["uploads"]:
        key = f"upload:{up['id']}"
        nodes.append({"id": key, "type": "Evidence", "label": up["filename"],
                      "sublabel": up["parsing_status"]})
        edges.append({"source": f"patient:{p['id']}", "target": key, "relation": "HAS_UPLOAD"})
        for item in DB.list_variants(up["id"], page=1, page_size=50)["items"]:
            vk = f"var:{item['id']}"
            nodes.append({"id": vk, "type": "Variant",
                          "label": item.get("normalized_variant") or item.get("hgvs_c") or f"var-{item['id']}",
                          "sublabel": item.get("gene") or ""})
            edges.append({"source": key, "target": vk, "relation": "CONTAINS_VARIANT"})
            if item.get("gene"):
                gk = f"gene:{item['gene']}"
                nodes.append({"id": gk, "type": "Gene", "label": item["gene"], "sublabel": "HGNC"})
                edges.append({"source": vk, "target": gk, "relation": "VARIANT_IN_GENE"})
    for rec in bundle["reconciliations"]:
        key = f"interp:{rec['id']}"
        nodes.append({"id": key, "type": "Interpretation",
                      "label": rec["final_classification"], "sublabel": rec.get("confidence") or ""})
        edges.append({"source": f"patient:{p['id']}", "target": key, "relation": "HAS_INTERPRETATION"})
    DB.replace_graph(patient_id, nodes, edges)
