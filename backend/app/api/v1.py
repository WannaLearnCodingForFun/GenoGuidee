"""
GenoGuide API v1 — versioned research-engine endpoints.

The legacy demo API under /api/* is preserved untouched (the existing
frontend depends on it); everything new lives under /api/v1/*.

Role-based access (section 43): lightweight token-role primitives via the
X-Role header (PATIENT, DOCTOR, LAB_CLINICIAN, RESEARCHER, GENETIC_COUNSELOR,
ADMIN). This is an authorization ARCHITECTURE demonstration — production
deployments must replace the header trust with real authentication (OIDC/
mTLS); the dependency structure is the extension point.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, Header, HTTPException
from pydantic import BaseModel, Field

from ..bioinformatics import vcf as vcfmod
from ..interpretation.acmg_v2 import (
    ENGINE_VERSION, RULE_VERSION, CRITERIA_REGISTRY, EvidenceInputs, evaluate)
from ..interpretation.clingen_specs import list_specifications, load_specification
from ..knowledge_graph.graph import KG_VERSION, build_gene_graph
from ..provenance2 import ledger
from ..schemas.variant import CanonicalVariant, GenomeBuild
from ..services.evidence import EvidenceService
from ..services.interpret import InterpretationService

router = APIRouter(prefix="/api/v1", tags=["v1"])

ROLES = {"PATIENT", "DOCTOR", "LAB_CLINICIAN", "RESEARCHER", "GENETIC_COUNSELOR", "ADMIN"}

ROLE_PERMISSIONS: dict[str, set[str]] = {
    "PATIENT": {"read:own"},
    "DOCTOR": {"read:own", "read:assigned", "interpret"},
    "LAB_CLINICIAN": {"read:assigned", "interpret", "vcf"},
    "GENETIC_COUNSELOR": {"read:assigned", "interpret"},
    "RESEARCHER": {"read:deidentified", "research"},
    "ADMIN": {"read:own", "read:assigned", "read:deidentified",
              "interpret", "vcf", "research", "admin"},
}


def get_role(x_role: Optional[str] = Header(default=None)) -> str:
    role = (x_role or "RESEARCHER").upper()
    if role not in ROLES:
        raise HTTPException(403, f"unknown role {role!r}")
    return role


def require(permission: str):
    def checker(role: str = Depends(get_role)) -> str:
        if permission not in ROLE_PERMISSIONS[role]:
            raise HTTPException(403, f"role {role} lacks permission {permission!r}")
        return role
    return checker


_interp_service: Optional[InterpretationService] = None


def interp_service() -> InterpretationService:
    global _interp_service
    if _interp_service is None:
        _interp_service = InterpretationService()
    return _interp_service


# ---------------------------------------------------------------- health ----

@router.get("/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "engine": "genoguide-research",
            "acmg_engine": ENGINE_VERSION, "kg_version": KG_VERSION}


@router.get("/system/status")
def system_status() -> dict[str, Any]:
    svc = interp_service()
    return {"evidence_sources": svc.evidence.source_summary(),
            "acmg_rule_version": RULE_VERSION,
            "clingen_specifications": list_specifications()}


@router.get("/models/status")
def models_status() -> dict[str, Any]:
    from ..services.interpret import _load_ml_model
    bundle = _load_ml_model()
    if bundle is None:
        return {"ml_model": None,
                "note": "no registered model artifact — run: python -m cli.genoguide train"}
    meta = bundle["meta"]
    return {"ml_model": meta["model_id"],
            "metrics_gene_disjoint_test": meta.get("metrics_gene_disjoint_test"),
            "calibration": meta.get("calibration"),
            "artifact_sha256": meta.get("artifact_sha256")}


# -------------------------------------------------------------- variants ----

class VariantIn(BaseModel):
    genome_build: GenomeBuild = GenomeBuild.GRCH38
    chromosome: str
    position: int
    reference: str
    alternate: str
    gene: Optional[str] = None
    hgvs_p: Optional[str] = None


def _canonical(v: VariantIn) -> CanonicalVariant:
    try:
        return CanonicalVariant.from_vcf_fields(
            v.genome_build, v.chromosome, v.position, v.reference, v.alternate,
            gene=v.gene, hgvs_p=v.hgvs_p)
    except ValueError as e:
        raise HTTPException(422, str(e)) from e


@router.post("/variants/normalize")
def normalize_variant(v: VariantIn) -> dict[str, Any]:
    pos, ref, alt = vcfmod.trim_alleles(v.position, v.reference, v.alternate)
    cv = _canonical(VariantIn(**{**v.model_dump(), "position": pos,
                                 "reference": ref, "alternate": alt}))
    return {"variant_id": cv.variant_id, "normalized": cv.model_dump(mode="json"),
            "left_aligned": False,
            "note": "reference-free parsimony trimming; bcftools+FASTA enables left alignment"}


@router.post("/variants/annotate")
def annotate_variant(v: VariantIn, _: str = Depends(require("interpret"))) -> dict[str, Any]:
    return interp_service().evidence.annotate(_canonical(v))


@router.get("/variants/{variant_id}")
def get_variant(variant_id: str) -> dict[str, Any]:
    try:
        build, chrom, pos, alleles = variant_id.split(":", 3)
        ref, alt = alleles.split(">")
        cv = CanonicalVariant.from_vcf_fields(GenomeBuild(build), chrom, int(pos), ref, alt)
    except (ValueError, KeyError) as e:
        raise HTTPException(422, f"variant_id must be build:chrom:pos:ref>alt ({e})") from e
    return interp_service().evidence.annotate(cv)


@router.post("/variants/batch")
def batch_variants(variants: list[VariantIn],
                   _: str = Depends(require("interpret"))) -> list[dict[str, Any]]:
    if len(variants) > 500:
        raise HTTPException(413, "batch limited to 500 variants")
    return [interp_service().evidence.annotate(_canonical(v)) for v in variants]


# --------------------------------------------------------- interpretation ----

class PatientContext(BaseModel):
    patient_id: Optional[str] = None
    hpo_terms: list[str] = Field(default_factory=list)
    age: Optional[int] = None
    sex: Optional[str] = None


class InterpretRequest(BaseModel):
    variant: VariantIn
    patient: Optional[PatientContext] = None


@router.post("/interpret")
def interpret(req: InterpretRequest, _: str = Depends(require("interpret"))) -> dict[str, Any]:
    obj = interp_service().interpret(
        _canonical(req.variant),
        patient=req.patient.model_dump() if req.patient else None)
    return obj.model_dump(mode="json")


@router.post("/interpret/batch")
def interpret_batch(reqs: list[InterpretRequest],
                    _: str = Depends(require("interpret"))) -> list[dict[str, Any]]:
    if len(reqs) > 100:
        raise HTTPException(413, "batch limited to 100 interpretations")
    return [interpret(r, _) for r in reqs]


@router.get("/interpret/{interpretation_id}")
def get_interpretation(interpretation_id: str) -> dict[str, Any]:
    rec = ledger.get_record(interpretation_id)
    if rec is None:
        raise HTTPException(404, "interpretation not found on ledger")
    return rec


# ------------------------------------------------------------------- acmg ----

@router.post("/acmg/evaluate")
def acmg_evaluate(evidence: EvidenceInputs, gene: Optional[str] = None) -> dict[str, Any]:
    spec = load_specification(gene)
    return evaluate(evidence, spec).model_dump(mode="json")


@router.get("/acmg/rules")
def acmg_rules() -> dict[str, Any]:
    return {"rule_version": RULE_VERSION,
            "criteria": [{"id": c.id, "name": c.name, "category": c.category,
                          "default_strength": c.default_strength.value,
                          "enabled_by_default": c.enabled_by_default}
                         for c in CRITERIA_REGISTRY.values()],
            "specifications": list_specifications()}


# -------------------------------------------------------------- phenotype ----

class PhenotypeMatchRequest(BaseModel):
    hpo_terms: list[str]
    gene: Optional[str] = None
    measure: str = "lin"
    top: int = 15


@router.post("/phenotype/match")
def phenotype_match(req: PhenotypeMatchRequest) -> dict[str, Any]:
    from ..phenotype.similarity import match_patient_to_gene, rank_genes
    if req.gene:
        return match_patient_to_gene(req.hpo_terms, req.gene, req.measure)
    return rank_genes(req.hpo_terms, measure=req.measure, top=req.top)


@router.post("/phenotype/gene-ranking")
def phenotype_gene_ranking(req: PhenotypeMatchRequest) -> dict[str, Any]:
    from ..phenotype.similarity import rank_genes
    return rank_genes(req.hpo_terms, measure=req.measure, top=req.top)


@router.post("/phenotype/disease-ranking")
def phenotype_disease_ranking(req: PhenotypeMatchRequest) -> dict[str, Any]:
    from ..phenotype.similarity import rank_diseases
    return rank_diseases(req.hpo_terms, measure=req.measure, top=req.top)


# ---------------------------------------------------------------- graph ----

@router.get("/graph/gene/{gene}")
def graph_gene(gene: str) -> dict[str, Any]:
    return build_gene_graph(gene.upper())


# ------------------------------------------------------------- provenance ----

@router.get("/provenance/{interpretation_id}")
def provenance_get(interpretation_id: str) -> dict[str, Any]:
    rec = ledger.get_record(interpretation_id)
    if rec is None:
        raise HTTPException(404, "not found")
    return rec


@router.post("/provenance/{interpretation_id}/verify")
def provenance_verify(interpretation_id: str) -> dict[str, Any]:
    return ledger.verify_interpretation(interpretation_id)


@router.get("/provenance/{interpretation_id}/audit")
def provenance_audit(interpretation_id: str) -> dict[str, Any]:
    return {"interpretation": ledger.get_record(interpretation_id),
            "chain": ledger.verify_chain(),
            "recent_blocks": ledger.audit_trail(20)}


# ---------------------------------------------------------------- research ----

@router.get("/research/datasets")
def research_datasets(_: str = Depends(require("research"))) -> list[dict[str, Any]]:
    import cli  # noqa: F401 — sys.path bootstrap for repo root
    from research import acquisition
    manifest = acquisition.load_manifest()
    return [acquisition.dataset_status(n, s) for n, s in manifest.items()]


@router.get("/research/models")
def research_models(_: str = Depends(require("research"))) -> list[dict[str, Any]]:
    import json as _json
    from pathlib import Path
    reg = Path(__file__).resolve().parents[3] / "models" / "registry"
    return [_json.loads(p.read_text()) for p in sorted(reg.glob("*.json"))] if reg.exists() else []


@router.get("/research/benchmarks")
def research_benchmarks(_: str = Depends(require("research"))) -> dict[str, Any]:
    import json as _json
    from pathlib import Path
    p = Path(__file__).resolve().parents[3] / "research/reports/benchmark_results.json"
    if not p.exists():
        raise HTTPException(404, "no benchmark results yet — run: python -m cli.genoguide benchmark")
    return _json.loads(p.read_text())


# ------------------------------------------------------------------ VCF ----

class VcfPath(BaseModel):
    path: str
    build: GenomeBuild = GenomeBuild.GRCH38


@router.post("/vcf/validate")
def vcf_validate(req: VcfPath, _: str = Depends(require("vcf"))) -> dict[str, Any]:
    return vcfmod.validate_vcf(req.path)


@router.post("/vcf/normalize")
def vcf_normalize(req: VcfPath, _: str = Depends(require("vcf"))) -> dict[str, Any]:
    return vcfmod.normalize_vcf(req.path)


# ------------------------------------------------------------- family ----

class FamilyMember(BaseModel):
    variants: list[VariantIn]
    sex: Optional[str] = None


class TrioRequest(BaseModel):
    child: list[VariantIn]
    mother: list[VariantIn] = Field(default_factory=list)
    father: list[VariantIn] = Field(default_factory=list)


class CoupleRequest(BaseModel):
    partner_a: list[VariantIn]
    partner_b: list[VariantIn]


def _as_recs(vs: list[VariantIn]) -> list[dict[str, Any]]:
    out = []
    for v in vs:
        cv = _canonical(v)
        out.append({"variant_id": cv.variant_id, "gene": v.gene, "chromosome": cv.chromosome})
    return out


@router.post("/family/trio")
def family_trio(req: TrioRequest, _: str = Depends(require("interpret"))) -> dict[str, Any]:
    from ..phenotype.family import analyze_trio, compound_het_candidates
    child, mother, father = _as_recs(req.child), _as_recs(req.mother), _as_recs(req.father)
    return {**analyze_trio(child, mother, father),
            "compound_het": compound_het_candidates(child, mother, father)}


@router.post("/family/couple")
def family_couple(req: CoupleRequest, _: str = Depends(require("interpret"))) -> dict[str, Any]:
    from ..phenotype.family import couple_carrier_overlap
    return couple_carrier_overlap(_as_recs(req.partner_a), _as_recs(req.partner_b))


@router.get("/interpret/{interpretation_id}/evidence")
def interpretation_evidence(interpretation_id: str) -> dict[str, Any]:
    rec = ledger.get_record(interpretation_id)
    if rec is None:
        raise HTTPException(404, "interpretation not found")
    return {"interpretation_id": interpretation_id,
            "evidence_snapshot_hash": rec.get("evidence_snapshot_hash"),
            "annotation_version": rec.get("annotation_version"),
            "acmg_rule_version": rec.get("acmg_rule_version")}


@router.get("/interpret/{interpretation_id}/explanation")
def interpretation_explanation(interpretation_id: str) -> dict[str, Any]:
    rec = ledger.get_record(interpretation_id)
    if rec is None:
        raise HTTPException(404, "interpretation not found")
    return {
        "interpretation_id": interpretation_id,
        "text": "Structured explanation only — no LLM. See ACMG criteria on the interpretation record.",
        "record": rec,
    }


@router.post("/graph/query")
def graph_query(body: dict[str, Any]) -> dict[str, Any]:
    gene = (body.get("gene") or "").upper()
    if not gene:
        raise HTTPException(422, "provide {\"gene\": \"BRCA1\"}")
    return build_gene_graph(gene)
