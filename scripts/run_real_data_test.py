# scripts/run_real_data_test.py
r"""
Wires real ClinVar panel data + real NA12878 trio genotypes into your
actual carrier_screen / trio_phasing / graph_builders code, then renders
with the same pyvis harness from tests/visual_test.py.

UPDATE: trio phasing's high_priority flag (de novo + pathogenic) was
previously always 0, because phase_trio() was called without a
pathogenic_lookup dict. Now wired to a GENE-LEVEL watchlist built from
the real ClinVar panel data.

IMPORTANT CAVEAT (read before using in any demo/pitch):
ClinVar panel variants are stored as HGVS coding notation (e.g. "c.3895del")
with no genomic coordinate, while trio variants are chrom:pos:ref:alt. There
is no shared key between them without an intermediate coordinate lookup
(VEP could provide this — not yet wired). So this is GENE-LEVEL flagging,
not position-level: a de novo variant is flagged high-priority if it falls
in a gene where the real ClinVar panel has at least one Pathogenic/Likely
Pathogenic entry -- NOT because that exact variant was matched to a known
pathogenic record. Say it exactly that way if you present this: "this gene
has known pathogenic variants elsewhere in ClinVar," not "this variant is
pathogenic." The rigorous fix (position-exact matching via VEP coordinate
lookup) is the next real milestone, not done here.
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.family.carrier_screen import CarrierVariant, screen_couple
from src.visualization.graph_builders import carrier_network_graph, trio_pedigree_graph
from scripts.parse_trio_regions import build_trio_fixture
from src.family.trio_phasing import phase_trio

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tests.visual_test import render  # reuse the pyvis renderer

CLINVAR_CSV = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "clinvar_panel.csv"

PATHOGENIC_LABELS = {"Pathogenic", "Likely Pathogenic", "Pathogenic/Likely Pathogenic"}


def load_real_clinvar_by_gene() -> dict[str, list[CarrierVariant]]:
    by_gene: dict[str, list[CarrierVariant]] = {}
    with open(CLINVAR_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_gene.setdefault(row["gene"], []).append(
                CarrierVariant(row["gene"], row["variant_id"], row["classification"])
            )
    return by_gene


def build_gene_level_watchlist(clinvar_csv_path: Path) -> set[str]:
    """
    Genes with at least one real ClinVar Pathogenic/Likely Pathogenic entry.

    NOTE: this is gene-level, not position-level -- the ClinVar panel stores
    HGVS c. notation with no genomic coordinate, and trio variants are
    chrom:pos:ref:alt, so there's no direct position match possible without
    an intermediate coordinate-lookup step (VEP could supply this -- not
    wired yet). A de novo variant flagged via this watchlist means "this
    gene has known pathogenic variants elsewhere in ClinVar", NOT "this
    exact variant is pathogenic". Keep that distinction explicit in any
    output or presentation of these results.
    """
    watchlist: set[str] = set()
    with open(clinvar_csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["classification"] in PATHOGENIC_LABELS:
                watchlist.add(row["gene"])
    return watchlist


def synthetic_couple_from_real_variants(seed: int = 3):
    """
    Real variant catalog, synthetic patients: each partner is assigned a
    random subset of REAL ClinVar variants per gene, at a plausible carrier
    rate -- this is the honest version of "real data" for carrier screening,
    since real two-patient genomes aren't something to fetch for a demo.
    """
    random.seed(seed)
    by_gene = load_real_clinvar_by_gene()
    partner_a, partner_b = [], []
    for gene, variants in by_gene.items():
        if not variants:
            continue
        if random.random() < 0.25:
            partner_a.append(random.choice(variants))
        if random.random() < 0.25:
            partner_b.append(random.choice(variants))
    return partner_a, partner_b


if __name__ == "__main__":
    print("=== Carrier screen on REAL ClinVar variants (synthetic patients) ===")
    a, b = synthetic_couple_from_real_variants()
    print("Partner A:", [(v.gene, v.variant_id, v.classification) for v in a])
    print("Partner B:", [(v.gene, v.variant_id, v.classification) for v in b])
    result = screen_couple(a, b)
    print(result.summary())
    graph = carrier_network_graph("Partner A", "Partner B", result)
    render(graph, "carrier_network_real.html", "Carrier network (real ClinVar)")

    print("\n=== Trio phasing on REAL NA12878 trio genotypes ===")
    child, mother, father = build_trio_fixture()

    watchlist = build_gene_level_watchlist(CLINVAR_CSV)
    print(f"Gene-level watchlist (real ClinVar path/likely-path entries): {sorted(watchlist)}")

    # Gene-level pathogenic_lookup: any child variant in a watchlisted gene
    # is marked is_pathogenic=True for phase_trio's high_priority check.
    # This only affects variants that ALSO turn out de novo (high_priority
    # requires both DE_NOVO origin and is_pathogenic=True), so non-de-novo
    # variants in watchlisted genes are unaffected.
    pathogenic_lookup = {
        v.key(): True
        for v in child
        if v.gene in watchlist
    }

    phasing = phase_trio(child, mother, father, pathogenic_lookup)
    print(phasing.summary())

    print("\nDe novo variants, with gene-level watch status:")
    for pv in phasing.de_novo_variants:
        watch_tag = f" [gene-level watch: {pv.variant.gene}]" if pv.variant.gene in watchlist else ""
        print(f"  {pv.explain()}{watch_tag}")

    pedigree = trio_pedigree_graph(phasing, mother_label="NA12892", father_label="NA12891", child_label="NA12878")
    render(pedigree, "pedigree_real.html", "Trio pedigree (real 1000G)")
