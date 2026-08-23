"""
mutation_chain.py -- three different lenses on "how does this gene get to
pathogenic", combined because they answer related but genuinely distinct
questions. Building all three in one module since they share input data
(the ClinVar panel + AlphaMissense scores) but each has its own caveats
worth keeping visible, not blended together.

ASSUMED INPUT SCHEMA (adjust field names to match your actual
clinvar_panel_with_coords.csv / AlphaMissense scoring output -- these are
placeholders based on columns seen in this project's terminal output so
far; not confirmed against your real CSV headers):

  variant dict per row:
    gene: str
    variant_id: str            # e.g. "c.1521_1523delCTT"
    protein_pos: Optional[int] # amino acid position, if resolvable
    ref_aa: Optional[str]
    alt_aa: Optional[str]
    classification: str        # ClinVar label, e.g. "Pathogenic"
    alphamissense_score: Optional[float]  # 0-1, higher = more pathogenic

If your actual AlphaMissenseScore class (src/scoring/alphamissense.py)
has different field names, adapt the accessor functions at the top --
everything below only touches variants through those accessors, so a
schema mismatch is a one-place fix, not a rewrite.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from typing import Any, Optional

# ---------------------------------------------------------------------------
# Accessors -- change these if your real variant dict / dataclass field
# names differ. Everything downstream goes through these, not raw keys.
# ---------------------------------------------------------------------------

def _pos(v: dict) -> Optional[int]:
    return v.get("protein_pos")

def _score(v: dict) -> Optional[float]:
    return v.get("alphamissense_score")

def _is_pathogenic(v: dict) -> bool:
    return v.get("classification") in {"Pathogenic", "Likely Pathogenic"}


# ---------------------------------------------------------------------------
# 1. Mutational hotspots -- which positions in a gene recur across many
#    different pathogenic ClinVar entries. Pure real-data aggregation, no
#    modeling/heuristic involved -- this is the most "just count it" of
#    the three.
# ---------------------------------------------------------------------------

@dataclass
class Hotspot:
    protein_pos: int
    variant_count: int
    variant_ids: list[str]
    classifications: list[str]


def find_hotspots(gene_variants: list[dict], min_count: int = 2) -> list[Hotspot]:
    """
    Groups pathogenic/likely-pathogenic variants for one gene by protein
    position. Positions with >= min_count distinct pathogenic variant_ids
    are returned, sorted by count descending -- these are candidate
    mutational hotspots (worth noting in output that "hotspot" here means
    "recurs in ClinVar's curated pathogenic entries", not necessarily a
    structurally/functionally critical residue -- ClinVar's own submission
    bias toward well-studied positions is a real confound, not corrected
    for here).
    """
    by_pos: dict[int, list[dict]] = defaultdict(list)
    for v in gene_variants:
        pos = _pos(v)
        if pos is not None and _is_pathogenic(v):
            by_pos[pos].append(v)

    hotspots = [
        Hotspot(
            protein_pos=pos,
            variant_count=len(vs),
            variant_ids=[v["variant_id"] for v in vs],
            classifications=[v["classification"] for v in vs],
        )
        for pos, vs in by_pos.items()
        if len(vs) >= min_count
    ]
    return sorted(hotspots, key=lambda h: h.variant_count, reverse=True)


# ---------------------------------------------------------------------------
# 2. Family-level chain -- how two pathogenic hits in the same gene combine
#    across a real family/couple. This reuses your existing carrier_screen
#    and trio_phasing results rather than reinventing detection logic --
#    it's a presentation layer on data you already compute correctly.
# ---------------------------------------------------------------------------

@dataclass
class FamilyChainStep:
    label: str          # e.g. "Partner A carries", "Inherited from mother"
    variant_id: str
    gene: str
    classification: str


@dataclass
class FamilyChain:
    gene: str
    disease: str
    steps: list[FamilyChainStep]
    outcome: str  # e.g. "25% recurrence risk (compound het)", "de novo -- child affected"


def carrier_screen_chain(flag: "GeneCarrierFlag") -> FamilyChain:  # noqa: F821 -- see carrier_screen.py
    """
    Builds a chain from a GeneCarrierFlag (carrier_screen.py). Two
    independent single-variant carriers combining into a both-carrier
    reproductive-risk state -- the "chain" is: Partner A's variant +
    Partner B's variant -> flagged gene -> 25% risk per pregnancy.
    """
    steps = [
        FamilyChainStep("Partner A carries", v.variant_id, flag.gene, v.classification)
        for v in flag.partner_a_variants
    ] + [
        FamilyChainStep("Partner B carries", v.variant_id, flag.gene, v.classification)
        for v in flag.partner_b_variants
    ]
    het_note = "compound heterozygous" if flag.compound_het else "same variant"
    return FamilyChain(
        gene=flag.gene,
        disease=flag.disease,
        steps=steps,
        outcome=f"{flag.recurrence_risk_pct}% recurrence risk per pregnancy ({het_note})",
    )


def trio_phasing_chain(phased_variants: list["PhasedVariant"], gene: str) -> Optional[FamilyChain]:  # noqa: F821
    """
    Builds a chain from trio_phasing.py's phased_variants for one gene:
    parent origin(s) -> child. Returns None if the gene has no phased
    variants in this trio.
    """
    gene_variants = [pv for pv in phased_variants if pv.variant.gene == gene]
    if not gene_variants:
        return None

    steps = []
    for pv in gene_variants:
        origin_label = {
            "maternal": "Inherited from mother",
            "paternal": "Inherited from father",
            "both_parents": "Inherited from both parents",
            "de_novo": "De novo (neither parent)",
        }.get(pv.origin.value, pv.origin.value)
        steps.append(FamilyChainStep(
            origin_label,
            f"{pv.variant.chrom}:{pv.variant.pos}{pv.variant.ref}>{pv.variant.alt}",
            gene,
            "Pathogenic" if pv.is_pathogenic else "Unknown significance",
        ))

    high_priority = any(pv.high_priority for pv in gene_variants)
    outcome = "HIGH PRIORITY -- de novo pathogenic" if high_priority else "phased, not flagged high-priority"
    return FamilyChain(gene=gene, disease="", steps=steps, outcome=outcome)


# ---------------------------------------------------------------------------
# 3. Evolutionary path (heuristic) -- AlphaMissense-ordered single-mutation
#    steps from wildtype toward a final multi-mutation genotype.
#
#    IMPORTANT CAVEAT, repeat from module docstring: AlphaMissense scores
#    each substitution INDEPENDENTLY. It has no epistasis model, so
#    ordering steps by ascending score is a heuristic proxy for "least
#    resistance path" (Weinreich-style mutational accessibility), NOT a
#    validated or literature-confirmed evolutionary trajectory. Label this
#    clearly anywhere it's shown -- do not present it as ground truth.
# ---------------------------------------------------------------------------

@dataclass
class PathStep:
    order: int
    variant_id: str
    protein_pos: Optional[int]
    alphamissense_score: Optional[float]
    cumulative_label: str  # e.g. "1 of 3 mutations acquired"


@dataclass
class HeuristicPath:
    gene: str
    final_variant_ids: list[str]
    steps: list[PathStep]
    caveat: str = (
        "Heuristic ordering only: AlphaMissense scores each substitution "
        "independently and does not model epistasis between mutations. "
        "This path is the least-resistance ordering by ascending "
        "pathogenicity score, not a validated evolutionary trajectory."
    )


def build_heuristic_path(gene: str, multi_hit_variants: list[dict]) -> Optional[HeuristicPath]:
    """
    Given 2+ variants in the same gene believed to co-occur (e.g. a
    multi-hit genotype from trio/carrier data, or hypothetically explored
    variants of interest), orders them by ascending AlphaMissense score --
    least damaging first -- as a heuristic "path of least resistance"
    from wildtype toward the full combined genotype.

    Returns None if fewer than 2 variants have a usable score (nothing
    meaningful to order).
    """
    scored = [v for v in multi_hit_variants if v.get("gene") == gene and _score(v) is not None]
    if len(scored) < 2:
        return None

    scored.sort(key=lambda v: _score(v))
    steps = [
        PathStep(
            order=i + 1,
            variant_id=v["variant_id"],
            protein_pos=_pos(v),
            alphamissense_score=_score(v),
            cumulative_label=f"{i + 1} of {len(scored)} mutations acquired",
        )
        for i, v in enumerate(scored)
    ]
    return HeuristicPath(
        gene=gene,
        final_variant_ids=[v["variant_id"] for v in scored],
        steps=steps,
    )


if __name__ == "__main__":
    # Smoke test with made-up but structurally realistic data -- swap in
    # your real clinvar_panel_with_coords.csv rows (with alphamissense_score
    # joined in) once schema is confirmed.
    demo_variants = [
        {"gene": "CFTR", "variant_id": "c.1521_1523delCTT", "protein_pos": 508,
         "classification": "Pathogenic", "alphamissense_score": 0.97},
        {"gene": "CFTR", "variant_id": "c.1585-1G>A", "protein_pos": 508,
         "classification": "Pathogenic", "alphamissense_score": 0.91},
        {"gene": "CFTR", "variant_id": "c.350G>A", "protein_pos": 117,
         "classification": "Pathogenic", "alphamissense_score": 0.42},
        {"gene": "CFTR", "variant_id": "c.1000C>T", "protein_pos": 334,
         "classification": "Likely Pathogenic", "alphamissense_score": 0.68},
    ]

    print("=== 1. Hotspots ===")
    for h in find_hotspots(demo_variants, min_count=2):
        print(f"  position {h.protein_pos}: {h.variant_count} pathogenic variants -> {h.variant_ids}")

    print("\n=== 3. Heuristic evolutionary path (CFTR, all 4 demo variants treated as co-occurring) ===")
    path = build_heuristic_path("CFTR", demo_variants)
    if path:
        print(f"  {path.caveat}\n")
        for step in path.steps:
            print(f"  step {step.order}: {step.variant_id} (pos {step.protein_pos}, "
                  f"AlphaMissense {step.alphamissense_score}) -- {step.cumulative_label}")
