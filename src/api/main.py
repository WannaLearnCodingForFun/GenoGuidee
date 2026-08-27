"""
main.py — FastAPI app wiring together the GenoChain pipeline.

Endpoints (per the guide):
  POST /variant/interpret       -> Phase 1 (VEP + AlphaMissense + ACMG reconciliation)
  POST /family/carrier-screen   -> Phase 2 carrier logic
  POST /family/trio-phase       -> Phase 2 trio logic
  POST /recommend               -> Phase 3 RAG (NOW WIRED to rag_recommend.py)
  GET  /family/mutation-hotspots -> real ClinVar recurring-position aggregation
  GET  /family/mutation-path    -> AlphaMissense-ordered heuristic path (NEW)
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
from src.decision.decision_mapping import build_evidence_trace, map_variant_to_actions
from src.family.carrier_screen import CarrierVariant, screen_couple
from src.family.trio_phasing import Variant as TrioVariant
from src.family.trio_phasing import phase_trio
from src.family.mutation_chain import find_hotspots, build_heuristic_path
from src.reconciliation.reconcile import reconcile
from src.visualization.graph_builders import (
    carrier_network_graph,
    dual_path_graph,
    evidence_flow_graph,
    trio_pedigree_graph,
)

# rag_recommend.py lives in scripts/, not src/ -- imported directly since
# it's a standalone retrieval+templating module, not a package-style module.
# If you move it into src/ later, update this import to match.
from scripts.rag_recommend import retrieve as rag_retrieve, generate_summary as rag_generate_summary
from scripts.mutation_chain_data import load_real_variants_for_mutation_chain

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
# POST /variant/decision-map  (full pipeline: reconcile + evidence trace + decision)
# ---------------------------------------------------------------------------

class DecisionMapResponse(BaseModel):
    variant: str
    tier: str
    agreement: Optional[bool]
    actions: list[dict]
    evidence_flow_graph: dict
    dual_path_graph: dict


@app.post("/variant/decision-map", response_model=DecisionMapResponse)
def decision_map_endpoint(req: VariantInterpretRequest) -> DecisionMapResponse:
    """
    One-call endpoint that runs the full pipeline for a single variant and
    returns everything the frontend needs: the recommended clinical actions,
    plus both visualization graphs (evidence flow + dual-path convergence),
    ready to hand straight to a chart component.
    """
    try:
        result = reconcile(req.hgvs_notation)
    except VEPError as e:
        raise HTTPException(status_code=502, detail=f"VEP lookup failed: {e}")

    trace = build_evidence_trace(result.rule_result)
    decision = map_variant_to_actions(result)

    return DecisionMapResponse(
        variant=result.variant,
        tier=result.rule_result.tier,
        agreement=result.agreement,
        actions=[
            {"priority": a.priority.value, "recommendation": a.recommendation, "reasoning": a.reasoning}
            for a in decision.actions
        ],
        evidence_flow_graph=evidence_flow_graph(trace),
        dual_path_graph=dual_path_graph(result),
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
    ancestry: Optional[str] = Field(
        None, description="Optional ancestry label for real published carrier-rate context, "
                           "e.g. 'european', 'ashkenazi_jewish', 'african', 'hispanic', 'asian'"
    )


class GeneCarrierFlagOut(BaseModel):
    gene: str
    disease: str
    partner_a_variant_ids: list[str]
    partner_b_variant_ids: list[str]
    compound_het: bool
    recurrence_risk_pct: Optional[int]
    carrier_rate_context: Optional[str] = None


class GeneNearMissOut(BaseModel):
    gene: str
    disease: str
    carrier_partner: str
    variant_ids: list[str]


class CarrierScreenResponse(BaseModel):
    flagged_genes: list[GeneCarrierFlagOut]
    near_miss_genes: list[GeneNearMissOut]
    screened_gene_count: int
    network_graph: dict


@app.post("/family/carrier-screen", response_model=CarrierScreenResponse)
def carrier_screen_endpoint(req: CarrierScreenRequest) -> CarrierScreenResponse:
    a_vars = [CarrierVariant(v.gene, v.variant_id, v.classification) for v in req.partner_a_variants]
    b_vars = [CarrierVariant(v.gene, v.variant_id, v.classification) for v in req.partner_b_variants]

    result = screen_couple(a_vars, b_vars, ancestry=req.ancestry)

    flags = [
        GeneCarrierFlagOut(
            gene=f.gene,
            disease=f.disease,
            partner_a_variant_ids=[v.variant_id for v in f.partner_a_variants],
            partner_b_variant_ids=[v.variant_id for v in f.partner_b_variants],
            compound_het=f.compound_het,
            recurrence_risk_pct=f.recurrence_risk_pct,
            carrier_rate_context=f.carrier_rate_context,
        )
        for f in result.flagged_genes
    ]
    near_misses = [
        GeneNearMissOut(
            gene=n.gene,
            disease=n.disease,
            carrier_partner=n.carrier_partner,
            variant_ids=[v.variant_id for v in n.variants],
        )
        for n in result.near_miss_genes
    ]
    return CarrierScreenResponse(
        flagged_genes=flags,
        near_miss_genes=near_misses,
        screened_gene_count=len(result.screened_genes),
        network_graph=carrier_network_graph("Partner A", "Partner B", result),
    )


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
    pedigree_graph: dict


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
        pedigree_graph=trio_pedigree_graph(result),
    )


# ---------------------------------------------------------------------------
# GET /family/mutation-hotspots  (NEW — real ClinVar recurring-position data)
# ---------------------------------------------------------------------------

class HotspotOut(BaseModel):
    protein_pos: int
    variant_count: int
    variant_ids: list[str]
    classifications: list[str]


class MutationHotspotsResponse(BaseModel):
    gene: str
    hotspots: list[HotspotOut]
    caveat: str = (
        "Hotspots reflect recurrence in ClinVar's curated pathogenic entries, "
        "not necessarily a structurally or functionally critical residue -- "
        "ClinVar's own submission bias toward well-studied positions is a "
        "real confound, not corrected for here."
    )


@app.get("/family/mutation-hotspots", response_model=MutationHotspotsResponse)
def mutation_hotspots_endpoint(gene: str, min_count: int = 2) -> MutationHotspotsResponse:
    variants = load_real_variants_for_mutation_chain(genes=[gene])
    hotspots = find_hotspots(variants, min_count=min_count)
    return MutationHotspotsResponse(
        gene=gene,
        hotspots=[
            HotspotOut(
                protein_pos=h.protein_pos,
                variant_count=h.variant_count,
                variant_ids=h.variant_ids,
                classifications=h.classifications,
            )
            for h in hotspots
        ],
    )


# ---------------------------------------------------------------------------
# GET /family/mutation-path  (NEW — AlphaMissense-ordered heuristic path)
# ---------------------------------------------------------------------------

class PathStepOut(BaseModel):
    order: int
    variant_id: str
    protein_pos: Optional[int]
    alphamissense_score: Optional[float]
    cumulative_label: str


class MutationPathResponse(BaseModel):
    gene: str
    final_variant_ids: list[str]
    steps: list[PathStepOut]
    caveat: str


@app.get("/family/mutation-path", response_model=Optional[MutationPathResponse])
def mutation_path_endpoint(gene: str) -> Optional[MutationPathResponse]:
    """
    Returns None (HTTP 200, null body) rather than a 404/500 if fewer than 2
    variants in this gene have a real AlphaMissense score -- this is an
    expected, non-error outcome (e.g. AlphaMissense doesn't score indels,
    or the local index doesn't cover this gene's variants), not a failure.
    """
    variants = load_real_variants_for_mutation_chain(genes=[gene])
    path = build_heuristic_path(gene, variants)
    if path is None:
        return None
    return MutationPathResponse(
        gene=path.gene,
        final_variant_ids=path.final_variant_ids,
        steps=[
            PathStepOut(
                order=s.order,
                variant_id=s.variant_id,
                protein_pos=s.protein_pos,
                alphamissense_score=s.alphamissense_score,
                cumulative_label=s.cumulative_label,
            )
            for s in path.steps
        ],
        caveat=path.caveat,
    )


# ---------------------------------------------------------------------------
# POST /recommend  (Phase 3 -- NOW WIRED to rag_recommend.py)
# ---------------------------------------------------------------------------

class RecommendRequest(BaseModel):
    gene: str
    variant_id: Optional[str] = Field(
        None, description="Specific ClinVar variant_id (c. notation). If omitted, "
                           "returns aggregate gene-level summary."
    )
    ancestry: Optional[str] = Field(
        None, description="Optional ancestry label for carrier-rate context"
    )
    summary_mode: bool = Field(
        False, description="If true and variant_id is omitted, return aggregate stats "
                            "instead of full per-variant listing"
    )


class RecommendResponse(BaseModel):
    summary_text: str
    gene: str
    disease: Optional[str]
    matched_variant_count: int
    ancestry_rate: Optional[str]
    hotspot_positions: list[int]


@app.post("/recommend", response_model=RecommendResponse)
def recommend_endpoint(req: RecommendRequest) -> RecommendResponse:
    facts = rag_retrieve(req.gene, req.variant_id, req.ancestry)
    if not facts.matched_rows:
        raise HTTPException(
            status_code=404,
            detail=f"No ClinVar entries found for gene={req.gene}"
                   + (f", variant_id={req.variant_id}" if req.variant_id else "")
                   + " in local panel data.",
        )

    summary_text = rag_generate_summary(facts, summary_mode=req.summary_mode)
    return RecommendResponse(
        summary_text=summary_text,
        gene=facts.gene,
        disease=facts.disease,
        matched_variant_count=len(facts.matched_rows),
        ancestry_rate=facts.ancestry_rate,
        hotspot_positions=facts.hotspot_positions,
    )


# ---------------------------------------------------------------------------
# GET /ledger/verify  (stub — Phase 4 not built yet, not in scope here)
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
