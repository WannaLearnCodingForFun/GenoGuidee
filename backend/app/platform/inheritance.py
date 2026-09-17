"""Deterministic inheritance reasoning. Never infers phase without evidence."""
from __future__ import annotations

from typing import Any, Optional

from ..phenotype.family import analyze_trio, compound_het_candidates, couple_carrier_overlap


def solve(
    *,
    child: list[dict[str, Any]],
    mother: Optional[list[dict[str, Any]]] = None,
    father: Optional[list[dict[str, Any]]] = None,
    siblings: Optional[list[list[dict[str, Any]]]] = None,
    gene_inheritance: Optional[str] = None,
    zygosity: Optional[dict[str, str]] = None,
) -> dict[str, Any]:
    evidence: list[str] = []
    mother = mother or []
    father = father or []
    trio = analyze_trio(child, mother, father) if (mother or father) else {
        "mode": "proband_only",
        "de_novo_candidates": [],
        "note": "Parents not provided — de novo is NOT_EVALUABLE, not assumed.",
    }
    chet = compound_het_candidates(child, mother or None, father or None)

    phase = "UNKNOWN"
    phased_pairs = chet.get("putative_compound_hets_phased") or []
    multi = chet.get("genes_with_two_plus_variants") or {}
    if phased_pairs:
        phase = "TRANS"
        evidence.append("parental genotypes place candidate pairs in trans")
    elif multi and not (mother and father):
        phase = "UNKNOWN"
        evidence.append("two variants in gene; phase cannot be established without parental genotypes")

    x_linked = []
    mito = []
    for v in child:
        chrom = str(v.get("chromosome") or v.get("chrom") or "").upper().replace("CHR", "")
        if chrom in {"X", "23"}:
            x_linked.append(v.get("variant_id") or v.get("id"))
        if chrom in {"MT", "M", "MITO"}:
            mito.append(v.get("variant_id") or v.get("id"))

    model = (gene_inheritance or "UNKNOWN").upper().replace(" ", "_")
    if model in {"", "UNKNOWN"}:
        if phased_pairs or multi:
            model = "AUTOSOMAL_RECESSIVE"
        elif trio.get("de_novo_candidates") and mother and father:
            model = "DE_NOVO"
        elif x_linked:
            model = "X_LINKED"
        elif mito:
            model = "MITOCHONDRIAL"
        elif child:
            model = "AUTOSOMAL_DOMINANT_CANDIDATE"

    candidates = []
    for v in child:
        vid = v.get("variant_id") or v.get("id")
        candidates.append({
            "variant_id": vid,
            "gene": v.get("gene"),
            "zygosity": (zygosity or {}).get(vid or "", v.get("zygosity") or "UNKNOWN"),
            "de_novo_candidate": vid in (trio.get("de_novo_candidates") or []),
        })

    review = phase == "UNKNOWN" or model.endswith("CANDIDATE") or not (mother and father)
    confidence = 0.7 if phase == "TRANS" and mother and father else 0.35 if (mother or father) else 0.15

    return {
        "inheritance_model": model,
        "candidate_variants": candidates,
        "phase_status": phase,
        "evidence": evidence or [
            "No phase-defining genotypes; phase is UNKNOWN and is not inferred.",
        ],
        "confidence": round(confidence, 3),
        "human_review_required": True if review else False,
        "trio": trio,
        "compound_het": chet,
        "x_linked_flagged": x_linked,
        "mitochondrial_flagged": mito,
        "siblings_considered": bool(siblings),
        "couple": couple_carrier_overlap(mother, father) if mother and father else None,
        "note": "De novo here is absence from provided parental call sets, not confirmed maternity/paternity (PS2).",
    }
