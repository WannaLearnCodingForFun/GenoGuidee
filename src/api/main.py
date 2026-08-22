"""
main.py — FastAPI app wiring together the GenoChain pipeline.

Endpoints (per the guide):
  POST /variant/interpret       -> Phase 1 (VEP + AlphaMissense + ACMG reconciliation)
  POST /family/carrier-screen   -> Phase 2 carrier logic
  POST /family/trio-phase       -> Phase 2 trio logic
  POST /recommend               -> Phase 3 RAG (stubbed until build_index.py/rag_recommend.py exist)
  GET  /ledger/verify           -> Phase 4 chain verification (stubbed until hash_chain.py exists)

Run locally:
    uvicorn src.api.main:app --reload
Then open http://127.0.0.1:8000/docs for interactive Swagger UI.
"""

from __future__ import annotations

from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, Field

from src.annotation.vep_client import VEPError
from src.family.carrier_screen import CarrierVariant, screen_couple
from src.family.trio_phasing import Variant as TrioVariant
from src.family.trio_phasing import phase_trio
from src.reconciliation.reconcile import reconcile

app = FastAPI(
    title="GenoChain API",
    description="Genomics variant interpretation pipeline — dual-path reconciliation, "
                 "carrier screening, trio phasing.",
    version="0.1.0",
)


# ---------------------------------------------------------------------------
# POST /variant/interpret
# ---------------------------------------------------------------------------

class VariantInterpretRequest(BaseModel):
    hgvs_notation: str = Field(
        ..., description="Variant in HGVS notation, e.g. 'ENST00000003084:c.1521_1523delCTT'"
    )


class VariantInterpretResponse(BaseModel):
    variant: str
    gene_symbol: Optional[str]
    consequence: Optional[str]
    gnomad_af: Optional[float]
    rule_tier: str
    rule_bucket: str
    ml_tier: Optional[str]
    ml_bucket: Optional[str]
    ml_source: str
    agreement: Optional[bool]
    triggered_criteria: list[str]


@app.post("/variant/interpret", response_model=VariantInterpretResponse)
def interpret_variant(req: VariantInterpretRequest) -> VariantInterpretResponse:
    try:
        result = reconcile(req.hgvs_notation)
    except VEPError as e:
        raise HTTPException(status_code=502, detail=f"VEP lookup failed: {e}")

    triggered = [c.code for c in result.rule_result.criteria if c.triggered]
    return VariantInterpretResponse(
        variant=result.variant,
        gene_symbol=result.gene_symbol,
        consequence=result.consequence,
        gnomad_af=result.gnomad_af,
        rule_tier=result.rule_result.tier,
        rule_bucket=result.rule_bucket,
        ml_tier=result.ml_tier,
        ml_bucket=result.ml_bucket,
        ml_source=result.ml_source,
        agreement=result.agreement,
        triggered_criteria=triggered,
    )


# ---------------------------------------------------------------------------
# POST /family/carrier-screen
# ---------------------------------------------------------------------------

class CarrierVariantIn(BaseModel):
    gene: str
    variant_id: str
    classification: str = Field(
        ..., description="e.g. 'Pathogenic', 'Likely Pathogenic', 'VUS', 'Benign'"
    )


class CarrierScreenRequest(BaseModel):
    partner_a_variants: list[CarrierVariantIn]
    partner_b_variants: list[CarrierVariantIn]


class GeneCarrierFlagOut(BaseModel):
    gene: str
    disease: str
    partner_a_variant_ids: list[str]
    partner_b_variant_ids: list[str]
    compound_het: bool
    recurrence_risk_pct: Optional[int]


class CarrierScreenResponse(BaseModel):
    flagged_genes: list[GeneCarrierFlagOut]
    screened_gene_count: int


@app.post("/family/carrier-screen", response_model=CarrierScreenResponse)
def carrier_screen_endpoint(req: CarrierScreenRequest) -> CarrierScreenResponse:
    a_vars = [CarrierVariant(v.gene, v.variant_id, v.classification) for v in req.partner_a_variants]
    b_vars = [CarrierVariant(v.gene, v.variant_id, v.classification) for v in req.partner_b_variants]

    result = screen_couple(a_vars, b_vars)

    flags = [
        GeneCarrierFlagOut(
            gene=f.gene,
            disease=f.disease,
            partner_a_variant_ids=[v.variant_id for v in f.partner_a_variants],
            partner_b_variant_ids=[v.variant_id for v in f.partner_b_variants],
            compound_het=f.compound_het,
            recurrence_risk_pct=f.recurrence_risk_pct,
        )
        for f in result.flagged_genes
    ]
    return CarrierScreenResponse(flagged_genes=flags, screened_gene_count=len(result.screened_genes))


# ---------------------------------------------------------------------------
# POST /family/trio-phase
# ---------------------------------------------------------------------------

class TrioVariantIn(BaseModel):
    chrom: str
    pos: int
    ref: str
    alt: str
    gene: Optional[str] = None
    is_pathogenic: Optional[bool] = Field(
        None, description="Optional — pass the reconcile.py result for this variant if known"
    )


class TrioPhaseRequest(BaseModel):
    child_variants: list[TrioVariantIn]
    mother_variants: list[TrioVariantIn]
    father_variants: list[TrioVariantIn]


class PhasedVariantOut(BaseModel):
    gene: Optional[str]
    chrom: str
    pos: int
    ref: str
    alt: str
    origin: str
    is_pathogenic: Optional[bool]
    high_priority: bool


class TrioPhaseResponse(BaseModel):
    phased_variants: list[PhasedVariantOut]
    de_novo_count: int
    high_priority_count: int


@app.post("/family/trio-phase", response_model=TrioPhaseResponse)
def trio_phase_endpoint(req: TrioPhaseRequest) -> TrioPhaseResponse:
    def to_variant(v: TrioVariantIn) -> TrioVariant:
        return TrioVariant(v.chrom, v.pos, v.ref, v.alt, gene=v.gene)

    child_vars = [to_variant(v) for v in req.child_variants]
    mother_vars = [to_variant(v) for v in req.mother_variants]
    father_vars = [to_variant(v) for v in req.father_variants]

    pathogenic_lookup = {
        (v.chrom, v.pos, v.ref, v.alt): v.is_pathogenic
        for v in req.child_variants
        if v.is_pathogenic is not None
    }

    result = phase_trio(child_vars, mother_vars, father_vars, pathogenic_lookup)

    phased_out = [
        PhasedVariantOut(
            gene=pv.variant.gene,
            chrom=pv.variant.chrom,
            pos=pv.variant.pos,
            ref=pv.variant.ref,
            alt=pv.variant.alt,
            origin=pv.origin.value,
            is_pathogenic=pv.is_pathogenic,
            high_priority=pv.high_priority,
        )
        for pv in result.phased_variants
    ]
    return TrioPhaseResponse(
        phased_variants=phased_out,
        de_novo_count=len(result.de_novo_variants),
        high_priority_count=len(result.high_priority_variants),
    )


# ---------------------------------------------------------------------------
# POST /recommend  (stub — Phase 3 not built yet)
# ---------------------------------------------------------------------------

class RecommendRequest(BaseModel):
    gene: str
    variant_notation: str
    tier: str


class RecommendResponse(BaseModel):
    recommendation: str
    sources: list[str]


@app.post("/recommend", response_model=RecommendResponse)
def recommend_endpoint(req: RecommendRequest) -> RecommendResponse:
    raise HTTPException(
        status_code=501,
        detail="Not implemented yet — Phase 3 (build_index.py / rag_recommend.py) "
               "hasn't been built. This endpoint is wired up so the frontend can "
               "call it once that lands.",
    )


# ---------------------------------------------------------------------------
# GET /ledger/verify  (stub — Phase 4 not built yet)
# ---------------------------------------------------------------------------

class LedgerVerifyResponse(BaseModel):
    valid: bool
    entry_count: int


@app.get("/ledger/verify", response_model=LedgerVerifyResponse)
def ledger_verify_endpoint() -> LedgerVerifyResponse:
    raise HTTPException(
        status_code=501,
        detail="Not implemented yet — Phase 4 (hash_chain.py) hasn't been built.",
    )


@app.get("/")
def root() -> dict:
    return {"service": "GenoChain API", "status": "ok", "docs": "/docs"}
