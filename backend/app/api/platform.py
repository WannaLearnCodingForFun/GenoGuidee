"""Additive /api/v1 platform routes. Existing v1 handlers are untouched."""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Header
from pydantic import BaseModel, Field

from ..platform.errors import disabled, json_error, request_id
from ..platform.flags import enabled, snapshot
from ..platform.rbac import can_finalize, can_see_identity, has_perm, normalize_role

router = APIRouter(prefix="/api/v1", tags=["platform"])


def _rid(x_request_id: Optional[str]) -> str:
    return request_id(x_request_id)


def _guard(flag: str, rid: Optional[str] = None):
    if not enabled(flag):
        return disabled(flag, rid)
    return None


def _role(authorization: Optional[str], x_role: Optional[str]) -> tuple[str, Optional[dict[str, Any]]]:
    if authorization and authorization.lower().startswith("bearer "):
        try:
            from .. import clinical_db as DB
            from ..local_auth import parse_token
            payload = parse_token(authorization.split(" ", 1)[1].strip())
            user = DB.get_user(int(payload["uid"]))
            return normalize_role(user["role"]), user
        except Exception:
            pass
    return normalize_role(x_role), None


def _forbid_identity(role: str, rid: str):
    if not can_see_identity(role):
        return json_error(403, "IDENTITY_FORBIDDEN", "researcher cannot access identity", rid)
    return None


def _patient_guard(user: Optional[dict[str, Any]], patient_id: Optional[int], rid: str):
    if user is None or patient_id is None:
        return None
    from .. import clinical_db as DB
    if not DB.can_access_patient(user, int(patient_id)):
        return json_error(403, "FORBIDDEN", "patient cannot access another patient", rid)
    return None


@router.get("/platform/flags")
def platform_flags() -> dict[str, Any]:
    return {"flags": snapshot()}


# ---------------------------------------------------------------- evidence --

class GraphEdgeIn(BaseModel):
    source_key: str
    target_key: str
    edge_type: str
    source: Optional[str] = None
    source_id: Optional[str] = None
    source_version: Optional[str] = None
    retrieved_at: Optional[str] = None
    evidence_strength: Optional[str] = None
    direction: Optional[str] = None
    properties: dict[str, Any] = Field(default_factory=dict)
    source_node: Optional[dict[str, Any]] = None
    target_node: Optional[dict[str, Any]] = None


@router.post("/evidence/graph/edge")
def evidence_graph_edge(body: GraphEdgeIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_EVIDENCE_GRAPH", rid)
    if g:
        return g
    from ..platform import evidence_graph as G
    try:
        if body.source_node:
            G.upsert_node(body.source_key, body.source_node["type"], body.source_node.get("label") or body.source_key,
                          body.source_node.get("properties"))
        if body.target_node:
            G.upsert_node(body.target_key, body.target_node["type"], body.target_node.get("label") or body.target_key,
                          body.target_node.get("properties"))
        edge = G.add_edge(
            body.source_key, body.target_key, body.edge_type,
            source=body.source, source_id=body.source_id, source_version=body.source_version,
            retrieved_at=body.retrieved_at, evidence_strength=body.evidence_strength,
            direction=body.direction, properties=body.properties,
        )
        return edge
    except ValueError as exc:
        return json_error(422, "EVIDENCE_PROVENANCE_REQUIRED", str(exc), rid)


@router.get("/graph")
def graph_get(seed: str, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_EVIDENCE_GRAPH", rid)
    if g:
        return g
    from ..platform import evidence_graph as G
    return G.subgraph(seed)


class RadarIn(BaseModel):
    clinvar: Any = None
    clingen: Any = None
    gnomad: Any = None
    alphamissense: Any = None
    revel: Any = None
    spliceai: Any = None
    cadd: Any = None
    functional: Any = None
    literature: Any = None
    acmg: Any = None
    ml: Any = None
    phenotype: Any = None


@router.post("/evidence/radar")
def evidence_radar(body: RadarIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_EVIDENCE_GRAPH", rid)
    if g:
        return g
    from ..platform.conflict_radar import aggregate
    return aggregate(body.model_dump())


# ------------------------------------------------------ interpretations --

@router.get("/interpretations/{interpretation_id}/history")
def interpretation_history(interpretation_id: str, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_INTERPRETATION_VERSIONING", rid)
    if g:
        return g
    from ..platform import interpretations as I
    rows = I.history(interpretation_id)
    if not rows:
        return json_error(404, "INTERPRETATION_NOT_FOUND", "interpretation not found", rid)
    return {"interpretation_id": interpretation_id, "versions": rows}


@router.get("/interpretations/{interpretation_id}/diff/{version_a}/{version_b}")
def interpretation_diff(interpretation_id: str, version_a: int, version_b: int,
                        x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_INTERPRETATION_VERSIONING", rid)
    if g:
        return g
    from ..platform import interpretations as I
    try:
        return I.diff(interpretation_id, version_a, version_b)
    except KeyError:
        return json_error(404, "INTERPRETATION_NOT_FOUND", "version not found", rid)


# ---------------------------------------------------------- reanalysis --

@router.post("/reanalysis/check")
def reanalysis_check(x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_REANALYSIS", rid)
    if g:
        return g
    from ..platform import reanalysis as R
    return R.check()


@router.post("/reanalysis/run")
def reanalysis_run(x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_REANALYSIS", rid)
    if g:
        return g
    from ..platform import reanalysis as R
    return R.run()


@router.get("/reanalysis/jobs/{job_id}")
def reanalysis_job(job_id: str, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_REANALYSIS", rid)
    if g:
        return g
    from ..platform import reanalysis as R
    rec = R.job(job_id)
    if rec is None:
        return json_error(404, "JOB_NOT_FOUND", "reanalysis job not found", rid)
    return rec


@router.get("/reanalysis/changes")
def reanalysis_changes(x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_REANALYSIS", rid)
    if g:
        return g
    from ..platform import reanalysis as R
    return {"changes": R.changes()}


# ------------------------------------------------------------ watchlist --

class WatchIn(BaseModel):
    patient_id: Optional[int] = None
    case_id: Optional[str] = None
    variant_id: Optional[str] = None


@router.post("/watchlist")
def watchlist_add(body: WatchIn, authorization: Optional[str] = Header(default=None),
                  x_role: Optional[str] = Header(default=None),
                  x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_WATCHLIST", rid)
    if g:
        return g
    role, user = _role(authorization, x_role)
    if not has_perm(role, "watch") and role != "ADMIN":
        return json_error(403, "FORBIDDEN", "role cannot manage watchlist", rid)
    denied = _patient_guard(user, body.patient_id, rid)
    if denied:
        return denied
    from ..platform import watchlist as W
    rec = W.add(patient_id=body.patient_id, case_id=body.case_id, variant_id=body.variant_id,
                created_by=(user or {}).get("id") if user else None)
    from ..platform.store import audit
    audit(who=str((user or {}).get("email") or role), what="watchlist_add",
          case_id=body.case_id, object=body.variant_id, after=rec, request_id=rid)
    return rec


@router.get("/watchlist")
def watchlist_list(patient_id: Optional[int] = None,
                   authorization: Optional[str] = Header(default=None),
                   x_role: Optional[str] = Header(default=None),
                   x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_WATCHLIST", rid)
    if g:
        return g
    role, user = _role(authorization, x_role)
    denied = _patient_guard(user, patient_id, rid)
    if denied:
        return denied
    ident = _forbid_identity(role, rid) if patient_id is not None else None
    if ident:
        return ident
    from ..platform import watchlist as W
    return {"items": W.list_all(patient_id)}


@router.get("/watchlist/triggers")
def watchlist_triggers(watch_id: Optional[int] = None, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_WATCHLIST", rid)
    if g:
        return g
    from ..platform import watchlist as W
    return {"triggers": W.triggers(watch_id)}


# ----------------------------------------------------------- phenotypes --

class PhenotypeIn(BaseModel):
    terms: list[Any]
    gene: Optional[str] = None
    top: int = 20


@router.post("/phenotypes/normalize")
def phenotypes_normalize(body: PhenotypeIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_PHENOTYPE_ENGINE", rid)
    if g:
        return g
    from ..platform.phenotype_engine import normalize
    return normalize(body.terms)


@router.post("/phenotypes/match")
def phenotypes_match(body: PhenotypeIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_PHENOTYPE_ENGINE", rid)
    if g:
        return g
    from ..platform.phenotype_engine import match
    return match(body.terms, gene=body.gene)


@router.post("/phenotypes/rank-genes")
def phenotypes_rank_genes(body: PhenotypeIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_PHENOTYPE_ENGINE", rid)
    if g:
        return g
    from ..platform.phenotype_engine import rank_genes_ep
    return rank_genes_ep(body.terms, top=body.top)


@router.post("/phenotypes/rank-diseases")
def phenotypes_rank_diseases(body: PhenotypeIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_PHENOTYPE_ENGINE", rid)
    if g:
        return g
    from ..platform.phenotype_engine import rank_diseases_ep
    return rank_diseases_ep(body.terms, top=body.top)


class PhenoEvoIn(BaseModel):
    patient_id: int
    phenotype: str
    status: str = "observed"
    onset: Optional[str] = None
    observed_at: Optional[float] = None
    source: str = "evolution"
    confidence: Optional[str] = None
    negated: bool = False
    temporality: Optional[str] = None
    severity: Optional[str] = None


@router.post("/phenotypes/evolution")
def phenotypes_evolution(body: PhenoEvoIn, authorization: Optional[str] = Header(default=None),
                         x_role: Optional[str] = Header(default=None),
                         x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_PHENOTYPE_ENGINE", rid)
    if g:
        return g
    _, user = _role(authorization, x_role)
    denied = _patient_guard(user, body.patient_id, rid)
    if denied:
        return denied
    from ..platform.phenotype_engine import add_evolution
    return add_evolution(body.patient_id, body.phenotype, status=body.status, onset=body.onset,
                         observed_at=body.observed_at, source=body.source, confidence=body.confidence,
                         negated=body.negated, temporality=body.temporality, severity=body.severity)


@router.get("/phenotypes/evolution/{patient_id}")
def phenotypes_evolution_get(patient_id: int, authorization: Optional[str] = Header(default=None),
                             x_role: Optional[str] = Header(default=None),
                             x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_PHENOTYPE_ENGINE", rid)
    if g:
        return g
    _, user = _role(authorization, x_role)
    denied = _patient_guard(user, patient_id, rid)
    if denied:
        return denied
    from ..platform.phenotype_engine import profile
    return profile(patient_id)


# --------------------------------------------------------- inheritance --

class InheritanceIn(BaseModel):
    child: list[dict[str, Any]]
    mother: Optional[list[dict[str, Any]]] = None
    father: Optional[list[dict[str, Any]]] = None
    siblings: Optional[list[list[dict[str, Any]]]] = None
    gene_inheritance: Optional[str] = None
    zygosity: Optional[dict[str, str]] = None


@router.post("/inheritance/solve")
def inheritance_solve(body: InheritanceIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_INHERITANCE_SOLVER", rid)
    if g:
        return g
    from ..platform.inheritance import solve
    return solve(**body.model_dump())


# ------------------------------------------------------- ACMG simulate --

class SimulateIn(BaseModel):
    official: dict[str, Any]
    modifications: list[dict[str, Any]]


@router.post("/acmg/simulate")
def acmg_simulate(body: SimulateIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_VARIANT_SIMULATOR", rid)
    if g:
        return g
    from ..platform.acmg_simulate import simulate
    return simulate(body.official, body.modifications)


# ------------------------------------------------------------ curation --

class CurationIn(BaseModel):
    interpretation_id: str
    action: str
    state: Optional[str] = None
    criterion_id: Optional[str] = None
    new_status: Optional[str] = None
    comment: Optional[str] = None
    reason: str = "unspecified"


@router.post("/curation")
def curation_action(body: CurationIn, authorization: Optional[str] = Header(default=None),
                    x_role: Optional[str] = Header(default=None),
                    x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_HUMAN_REVIEW", rid)
    if g:
        return g
    role, user = _role(authorization, x_role)
    actor = (user or {}).get("email") if user else role
    from ..platform import curation as C
    try:
        if body.action in {"request_review", "transition"}:
            if body.state == "FINALIZED" and not can_finalize(role):
                return json_error(403, "FORBIDDEN", "unauthorized user cannot finalize interpretation", rid)
            if not has_perm(role, "curate") and not can_finalize(role):
                return json_error(403, "FORBIDDEN", "role cannot curate", rid)
            return C.transition(body.interpretation_id, body.state or "LAB_REVIEW",
                                actor=actor, role=role, reason=body.reason, request_id=rid)
        if body.action in {"accept", "reject", "change_evidence"}:
            if not has_perm(role, "curate"):
                return json_error(403, "FORBIDDEN", "role cannot curate", rid)
            return C.mutate_criterion(body.interpretation_id, body.criterion_id or "",
                                      body.new_status or ("MET" if body.action == "accept" else "NOT_MET"),
                                      actor=actor, role=role, reason=body.reason, request_id=rid)
        if body.action == "finalize":
            if not can_finalize(role):
                return json_error(403, "FORBIDDEN", "unauthorized user cannot finalize interpretation", rid)
            return C.transition(body.interpretation_id, "FINALIZED",
                                actor=actor, role=role, reason=body.reason, request_id=rid)
        if body.action == "supersede":
            if not can_finalize(role):
                return json_error(403, "FORBIDDEN", "unauthorized user cannot supersede interpretation", rid)
            return C.transition(body.interpretation_id, "SUPERSEDED",
                                actor=actor, role=role, reason=body.reason, request_id=rid)
        if body.action == "comment":
            return C.comment(body.interpretation_id, body.comment or "", actor=actor, role=role, request_id=rid)
        return json_error(422, "UNKNOWN_ACTION", f"unknown curation action {body.action}", rid)
    except KeyError:
        return json_error(404, "INTERPRETATION_NOT_FOUND", "interpretation not found", rid)
    except ValueError as exc:
        return json_error(409, "CURATION_CONFLICT", str(exc), rid)


@router.get("/curation/{interpretation_id}/events")
def curation_events(interpretation_id: str, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_HUMAN_REVIEW", rid)
    if g:
        return g
    from ..platform import curation as C
    return {"events": C.events(interpretation_id)}


# -------------------------------------------------------------- cases --

class CaseIn(BaseModel):
    patient_id: Optional[int] = None


@router.post("/cases")
def create_case(body: CaseIn, authorization: Optional[str] = Header(default=None),
                x_role: Optional[str] = Header(default=None),
                x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    role, user = _role(authorization, x_role)
    denied = _patient_guard(user, body.patient_id, rid)
    if denied:
        return denied
    ident = _forbid_identity(role, rid)
    if ident:
        return ident
    import uuid
    from ..platform import store
    cid = f"CASE-{uuid.uuid4().hex[:10].upper()}"
    store.execute(
        "INSERT INTO cases (case_id, patient_id, created_by, created_at) VALUES (?,?,?,?)",
        (cid, body.patient_id, (user or {}).get("id") if user else None, store.now()),
    )
    return {"case_id": cid, "patient_id": body.patient_id}


# -------------------------------------------------------- phenopackets --

class PhenopacketIn(BaseModel):
    phenopacket: dict[str, Any]
    patient_id: Optional[int] = None
    case_id: Optional[str] = None


@router.post("/phenopackets/import")
def phenopackets_import(body: PhenopacketIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_PHENOPACKET", rid)
    if g:
        return g
    from ..platform.phenopackets import from_phenopacket, save
    try:
        parsed = from_phenopacket(body.phenopacket)
    except ValueError as exc:
        return json_error(422, "INVALID_PHENOPACKET", str(exc), rid)
    save(body.phenopacket, case_id=body.case_id or parsed.get("phenopacket_id"),
         patient_id=body.patient_id)
    return {"imported": True, "parsed": parsed}


@router.get("/cases/{case_id}/phenopacket")
def phenopacket_export(case_id: str, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_PHENOPACKET", rid)
    if g:
        return g
    from ..platform.phenopackets import load_for_case, to_phenopacket
    existing = load_for_case(case_id)
    if existing:
        return existing
    from ..platform import store
    row = store.execute("SELECT patient_id FROM cases WHERE case_id=?", (case_id,), fetch="one")
    if not row or not row[0]:
        return json_error(404, "CASE_NOT_FOUND", "case not found", rid)
    from .. import clinical_db as DB
    from ..platform.phenotype_engine import profile
    patient = DB.get_patient(int(row[0]))
    prof = profile(int(row[0]))
    return to_phenopacket(patient, case_id=case_id, phenotypes=prof.get("timeline"))


# -------------------------------------------------------------- cohorts --

class CohortIn(BaseModel):
    name: str


class CohortCaseIn(BaseModel):
    case_id: str
    patient_id: Optional[int] = None


@router.post("/cohorts")
def cohort_create(body: CohortIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_COHORT_MODE", rid)
    if g:
        return g
    from ..platform.cohorts import create
    return create(body.name)


@router.post("/cohorts/{cohort_id}/cases")
def cohort_add(cohort_id: str, body: CohortCaseIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_COHORT_MODE", rid)
    if g:
        return g
    from ..platform.cohorts import add_case
    return add_case(cohort_id, body.case_id, body.patient_id)


@router.get("/cohorts/{cohort_id}")
def cohort_get(cohort_id: str, x_role: Optional[str] = Header(default=None),
               x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_COHORT_MODE", rid)
    if g:
        return g
    from ..platform.cohorts import deidentify_bundle
    bundle = deidentify_bundle(cohort_id)
    role = normalize_role(x_role)
    if role != "RESEARCHER" and can_see_identity(role):
        return bundle
    # strip any leftover identity
    for c in bundle["cases"]:
        c.pop("patient_id", None)
        c.pop("full_name", None)
        c.pop("email", None)
        c.pop("identifier", None)
    bundle["identity_fields_present"] = False
    return bundle


@router.get("/cohorts/{cohort_id}/shared-variants")
def cohort_shared(cohort_id: str, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_COHORT_MODE", rid)
    if g:
        return g
    from ..platform.cohorts import query_shared_variants
    return {"shared": query_shared_variants(cohort_id)}


@router.get("/cohorts/{cohort_id}/genes")
def cohort_genes(cohort_id: str, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_COHORT_MODE", rid)
    if g:
        return g
    from ..platform.cohorts import query_enriched_genes
    return {"genes": query_enriched_genes(cohort_id)}


# ---------------------------------------------------- model monitoring --

class MonitorIn(BaseModel):
    predictions: list[dict[str, Any]] = Field(default_factory=list)
    training_prior: Optional[dict[str, float]] = None


@router.post("/model-monitoring/snapshot")
def model_monitor_snap(body: MonitorIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_MODEL_MONITORING", rid)
    if g:
        return g
    from ..platform.model_monitor import snapshot as snap
    return snap(body.predictions, body.training_prior)


@router.get("/model-monitoring")
def model_monitor_get(x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_MODEL_MONITORING", rid)
    if g:
        return g
    from ..platform.model_monitor import latest
    rec = latest()
    return rec or {"drift_level": "LOW", "n": 0, "note": "no snapshots yet", "retrained": False}


class OodIn(BaseModel):
    ml: dict[str, Any]
    acmg_classification: Optional[str] = None


@router.post("/model-monitoring/ood")
def model_ood(body: OodIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_MODEL_MONITORING", rid)
    if g:
        return g
    from ..platform.model_monitor import ood_from_prediction
    info = ood_from_prediction(body.ml)
    if body.acmg_classification and info.get("prediction"):
        from ..interpretation.reconcile import bucket
        if bucket(str(info["prediction"])) != bucket(body.acmg_classification):
            if info.get("calibrated_probability") and info["calibrated_probability"] >= 0.8:
                info["human_review_required"] = True
                info["reason"] = "model confidence high BUT ACMG conflicts"
    return info


# -------------------------------------------------------------- explain --

class ExplainIn(BaseModel):
    acmg: Optional[dict[str, Any]] = None
    radar: Optional[dict[str, Any]] = None


@router.post("/evidence/explain")
def evidence_explain(body: ExplainIn, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_EXPLANATION", rid)
    if g:
        return g
    from ..platform.explain import explain
    return explain(acmg=body.acmg, radar=body.radar)


# -------------------------------------------------------------- timeline --

@router.get("/evidence/timeline/{variant_id}")
def evidence_timeline(variant_id: str, x_request_id: Optional[str] = Header(default=None)):
    rid = _rid(x_request_id)
    g = _guard("ENABLE_EVIDENCE_TIMELINE", rid)
    if g:
        return g
    from ..platform.evidence_timeline import timeline
    return {"variant_id": variant_id, "events": timeline(variant_id)}
