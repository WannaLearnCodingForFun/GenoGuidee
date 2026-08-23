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

ANCESTRY CONTEXT (added): real, published population carrier-frequency
estimates for a subset of panel genes/diseases where ancestry-specific
rates are well established in the literature (e.g. CDC/ACOG/NIH-cited
figures). This is NOT synthetic and NOT a prediction -- it's textbook
epidemiological context attached to a flag, e.g. "CFTR carrier rate is
~1/25 in individuals of European ancestry" -- to make a "both carriers"
flag clinically legible instead of a bare gene name. Ancestry is optional
input; if not provided, only the general-population rate is shown (or
none, for genes without a well-established general figure). Genes/diseases
not in ANCESTRY_CARRIER_RATES simply show no rate context -- this table is
deliberately not exhaustive, only entries with solid, citable sources are
included.
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
    "GBA1": "Gaucher disease",  # HGNC renamed GBA -> GBA1 in 2023; must match ClinVar data / cohort script
    "G6PD": "G6PD deficiency",
    "BTD": "Biotinidase deficiency",
}

PATHOGENIC_CLASSES = {"Pathogenic", "Likely Pathogenic", "pathogenic", "likely_pathogenic"}

# Real, published carrier-frequency estimates, by gene/disease and ancestry
# group, where well-established figures exist. Sources are the kind of
# numbers cited by ACOG/NIH/CDC carrier-screening guidance -- approximate,
# rounded, and meant for demo/education context, NOT for clinical use.
# Structure: gene -> {ancestry_label: "1 in N" string}. "general" is used
# when no ancestry is specified or matched.
ANCESTRY_CARRIER_RATES: dict[str, dict[str, str]] = {
    "CFTR": {
        "european": "1 in 25",
        "ashkenazi_jewish": "1 in 24",
        "hispanic": "1 in 46",
        "african": "1 in 65",
        "asian": "1 in 94",
        "general": "1 in 25 (European ancestry; varies by population)",
    },
    "HEXA": {
        "ashkenazi_jewish": "1 in 27",
        "general": "1 in 250-300 general population (~1 in 27 Ashkenazi Jewish)",
    },
    "ASPA": {
        "ashkenazi_jewish": "1 in 40",
        # Reworded -- the previous "(~1 in 40)" here read as if it applied to
        # the general population too, contradicting the real ~1/159
        # non-Ashkenazi rate used in generate_synthetic_cohort.py's fallback
        # table. Now explicit and consistent with that source.
        "general": "~1 in 159 outside Ashkenazi Jewish population (~1 in 40 within it)",
    },
    # Ported from generate_synthetic_cohort.py's FALLBACK_CARRIER_FREQ so
    # these two genes also get real population context on a flag, not just
    # a bare gene name. Sources documented there (ScienceDirect for MEFV,
    # PMC multi-ancestry study for SMN1).
    "MEFV": {
        "ashkenazi_jewish": "1 in 5 (21% carrier frequency; NOTE: reduced penetrance for "
                             "the most common variant, E148Q -- high carrier rate does NOT "
                             "translate proportionally to disease incidence)",
    },
    "SMN1": {
        "european": "1 in 37",
        "ashkenazi_jewish": "1 in 46",
        "asian": "1 in 56",
        "african": "1 in 91",
        "hispanic": "1 in 125",
        "general": "varies by ancestry, roughly 1 in 40-125 -- see population-specific rate",
    },
    "HBB": {
        "african": "1 in 12 (sickle cell trait)",
        "mediterranean": "1 in 20-30 (beta-thalassemia trait, varies by region)",
        "general": "varies widely by ancestry -- see population-specific rate",
    },
    "BTD": {
        "general": "1 in 60 (profound + partial deficiency combined, general population)",
    },
    "GJB2": {
        "general": "1 in 30-40 (varies by population; among the most common causes of hereditary hearing loss)",
    },
}


def get_carrier_rate_context(gene: str, ancestry: Optional[str] = None) -> Optional[str]:
    """
    Returns a real published carrier-frequency string for the given gene,
    preferring an ancestry-specific figure if `ancestry` is provided and
    matched, else falling back to the "general" entry, else None if this
    gene has no well-established rate in the table.

    `ancestry` should be a lowercase label matching ANCESTRY_CARRIER_RATES'
    keys (e.g. "european", "ashkenazi_jewish", "african", "hispanic",
    "asian", "mediterranean"). Unmatched or unknown ancestry labels fall
    back to "general" rather than raising -- this is optional context, not
    a strict lookup.
    """
    rates = ANCESTRY_CARRIER_RATES.get(gene)
    if not rates:
        return None
    if ancestry:
        key = ancestry.strip().lower().replace(" ", "_")
        if key in rates:
            return rates[key]
    return rates.get("general")


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
    carrier_rate_context: Optional[str] = None  # e.g. "1 in 25 (European ancestry)"

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
            if self.carrier_rate_context:
                lines.append(
                    f"  Population carrier rate for {self.gene}: {self.carrier_rate_context}"
                )
        return "\n".join(lines)


@dataclass
class GeneNearMissFlag:
    """
    A gene where exactly ONE partner carries a pathogenic/likely-pathogenic
    variant, not both. Not a reproductive risk under the standard recessive
    model (needs both partners), but worth surfacing visually -- distinct
    from a fully-flagged gene, and distinct from a gene with zero carriers
    on either side.
    """
    gene: str
    disease: str
    carrier_partner: str  # "A" or "B" -- which partner carries it
    variants: list[CarrierVariant]

    def explain(self) -> str:
        return (
            f"{self.gene} ({self.disease}) -- single carrier: Partner {self.carrier_partner} "
            f"[{[v.variant_id for v in self.variants]}] (not both -- no reproductive risk flagged)"
        )


@dataclass
class CarrierScreenResult:
    flagged_genes: list[GeneCarrierFlag] = field(default_factory=list)
    near_miss_genes: list[GeneNearMissFlag] = field(default_factory=list)
    screened_genes: list[str] = field(default_factory=list)

    def summary(self) -> str:
        lines: list[str] = []
        if self.flagged_genes:
            lines.append(f"CARRIER RISK FLAGGED — {len(self.flagged_genes)} gene(s):\n")
            for flag in self.flagged_genes:
                lines.append(flag.explain())
                lines.append("")
        else:
            lines.append(f"No shared carrier risk found across {len(self.screened_genes)} screened genes.")

        if self.near_miss_genes:
            lines.append(f"Single-carrier (not both) — {len(self.near_miss_genes)} gene(s), no reproductive risk:")
            for near in self.near_miss_genes:
                lines.append(f"  {near.explain()}")

        return "\n".join(lines)


def screen_couple(
    partner_a_variants: list[CarrierVariant],
    partner_b_variants: list[CarrierVariant],
    gene_panel: Optional[dict[str, str]] = None,
    ancestry: Optional[str] = None,
) -> CarrierScreenResult:
    """
    ancestry: optional label (e.g. "european", "ashkenazi_jewish", "african",
    "hispanic", "asian", "mediterranean") used to attach a real, published
    ancestry-specific carrier-rate figure to any flagged gene, where available
    (see ANCESTRY_CARRIER_RATES). Purely additive context -- omitting it
    changes nothing about which genes get flagged or the 25% recurrence-risk
    logic; it only affects whether a carrier_rate_context string is attached.
    """
    panel = gene_panel if gene_panel is not None else RECESSIVE_GENE_PANEL

    flags: list[GeneCarrierFlag] = []
    near_misses: list[GeneNearMissFlag] = []
    for gene, disease in panel.items():
        a_hits = [v for v in partner_a_variants if v.gene == gene and v.is_pathogenic()]
        b_hits = [v for v in partner_b_variants if v.gene == gene and v.is_pathogenic()]

        both = bool(a_hits) and bool(b_hits)
        if not both:
            if a_hits or b_hits:
                carrier_partner = "A" if a_hits else "B"
                near_misses.append(GeneNearMissFlag(
                    gene=gene,
                    disease=disease,
                    carrier_partner=carrier_partner,
                    variants=a_hits or b_hits,
                ))
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
            carrier_rate_context=get_carrier_rate_context(gene, ancestry),
        ))

    return CarrierScreenResult(
        flagged_genes=flags,
        near_miss_genes=near_misses,
        screened_genes=list(panel.keys()),
    )


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

    print("=== Test: couple carrier screen (no ancestry specified) ===\n")
    result = screen_couple(partner_a, partner_b)
    print(result.summary())

    print("\n=== Test: same couple, ancestry='ashkenazi_jewish' ===\n")
    result_ashkenazi = screen_couple(partner_a, partner_b, ancestry="ashkenazi_jewish")
    print(result_ashkenazi.summary())
