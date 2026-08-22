"""
carrier_screen.py — recessive-disease carrier screening for a couple.

Per the guide: this is the headline demo feature, most judge-friendly visual.
Never cut this.

Logic:
  - Input: two variant lists (partner A, partner B), each a list of
    (gene, variant_id, classification) tuples already run through the
    reconciliation pipeline (or manually curated for demo purposes).
  - Filter to a hardcoded recessive-disease gene panel.
  - For each panel gene, check if BOTH partners carry >=1 pathogenic /
    likely-pathogenic variant in that gene (same or different variant —
    the guide calls out compound-het handling as the "interesting" detail:
    two different pathogenic variants in the same gene, one from each
    partner, still means each of their children has a 25% chance of being
    affected under the standard recessive model).
  - Output: flagged genes with both-carrier status and recurrence risk.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional

# Hardcoded recessive-disease gene panel (per the guide: ~10-15 genes).
# gene -> (disease name, inheritance pattern) — inheritance kept simple
# (all treated as autosomal recessive here; extend if you add X-linked genes).
RECESSIVE_GENE_PANEL: dict[str, str] = {
    "CFTR": "Cystic fibrosis",
    "HBB": "Beta-thalassemia / sickle cell disease",
    "GJB2": "Autosomal recessive nonsyndromic hearing loss",
    "HEXA": "Tay-Sachs disease",
    "PAH": "Phenylketonuria",
    "ATP7B": "Wilson disease",
    "SMN1": "Spinal muscular atrophy",
    "MEFV": "Familial Mediterranean fever",
    "ASPA": "Canavan disease",
    "GBA": "Gaucher disease",
    "G6PD": "G6PD deficiency",
    "BTD": "Biotinidase deficiency",
}

PATHOGENIC_CLASSES = {"Pathogenic", "Likely Pathogenic", "pathogenic", "likely_pathogenic"}


@dataclass
class CarrierVariant:
    gene: str
    variant_id: str
    classification: str  # e.g. "Pathogenic", "Likely Pathogenic"

    def is_pathogenic(self) -> bool:
        return self.classification in PATHOGENIC_CLASSES


@dataclass
class GeneCarrierFlag:
    gene: str
    disease: str
    partner_a_variants: list[CarrierVariant]
    partner_b_variants: list[CarrierVariant]
    both_carriers: bool
    compound_het: bool  # True if A and B carry different pathogenic variants (not the exact same one)
    recurrence_risk_pct: Optional[int] = None  # 25% for standard AR, both carriers

    def explain(self) -> str:
        lines = [f"{self.gene} ({self.disease})"]
        lines.append(
            f"  Partner A: {[v.variant_id for v in self.partner_a_variants] or 'none'}"
        )
        lines.append(
            f"  Partner B: {[v.variant_id for v in self.partner_b_variants] or 'none'}"
        )
        if self.both_carriers:
            het_note = " (compound heterozygous — different variants)" if self.compound_het else ""
            lines.append(
                f"  >>> BOTH CARRIERS{het_note} — {self.recurrence_risk_pct}% recurrence risk per pregnancy"
            )
        return "\n".join(lines)


@dataclass
class CarrierScreenResult:
    flagged_genes: list[GeneCarrierFlag] = field(default_factory=list)
    screened_genes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        if not self.flagged_genes:
            return f"No shared carrier risk found across {len(self.screened_genes)} screened genes."
        lines = [f"CARRIER RISK FLAGGED — {len(self.flagged_genes)} gene(s):\n"]
        for flag in self.flagged_genes:
            lines.append(flag.explain())
            lines.append("")
        return "\n".join(lines)


def screen_couple(
    partner_a_variants: list[CarrierVariant],
    partner_b_variants: list[CarrierVariant],
    gene_panel: Optional[dict[str, str]] = None,
) -> CarrierScreenResult:
    panel = gene_panel if gene_panel is not None else RECESSIVE_GENE_PANEL

    flags: list[GeneCarrierFlag] = []
    for gene, disease in panel.items():
        a_hits = [v for v in partner_a_variants if v.gene == gene and v.is_pathogenic()]
        b_hits = [v for v in partner_b_variants if v.gene == gene and v.is_pathogenic()]

        both = bool(a_hits) and bool(b_hits)
        if not both:
            continue

        a_ids = {v.variant_id for v in a_hits}
        b_ids = {v.variant_id for v in b_hits}
        compound_het = a_ids != b_ids or (len(a_ids) == 1 and len(b_ids) == 1 and a_ids != b_ids)

        flags.append(GeneCarrierFlag(
            gene=gene,
            disease=disease,
            partner_a_variants=a_hits,
            partner_b_variants=b_hits,
            both_carriers=True,
            compound_het=compound_het,
            recurrence_risk_pct=25,
        ))

    return CarrierScreenResult(flagged_genes=flags, screened_genes=list(panel.keys()))


if __name__ == "__main__":
    # Synthetic demo data — guaranteed to show a positive case, per the guide's
    # suggestion to synthesize a known "both carriers" gene for a reliable demo.
    partner_a = [
        CarrierVariant("CFTR", "c.1521_1523delCTT", "Pathogenic"),   # delF508
        CarrierVariant("HEXA", "c.1274_1277dupTATC", "Likely Pathogenic"),
        CarrierVariant("PAH", "c.1222C>T", "Likely Pathogenic"),      # only in A -> not flagged
    ]
    partner_b = [
        CarrierVariant("CFTR", "c.1652G>A", "Pathogenic"),  # different CFTR variant -> compound het
        CarrierVariant("GJB2", "c.35delG", "Pathogenic"),    # only in B -> not flagged
    ]

    print("=== Test: couple carrier screen ===\n")
    result = screen_couple(partner_a, partner_b)
    print(result.summary())
