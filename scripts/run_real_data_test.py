# scripts/run_real_data_test.py
r"""
Wires real ClinVar panel data + real NA12878 trio genotypes into your
actual carrier_screen / trio_phasing / graph_builders code, then renders
with the same pyvis harness from tests/visual_test.py.

UPDATE (position-exact): trio phasing's high_priority flag (de novo +
pathogenic) is now wired to a POSITION-EXACT pathogenic_lookup, built
from clinvar_panel_with_coords.csv (real genomic coordinates resolved
via VEP). A de novo variant is flagged high-priority only if its exact
chrom:pos:ref:alt matches a real ClinVar Pathogenic/Likely Pathogenic
entry -- not merely "same gene as something pathogenic elsewhere" (the
old gene-level watchlist approach, now removed).

NOTE ON EXPECTED RESULTS: the real child variant set is small (~14
variants across 4 genes), and clinvar_panel_with_coords.csv has ~425
resolved positions. An exact position match between the two is
genuinely rare by chance. A high-priority count of 0 on a given run is
NOT a bug -- it means no coincidental exact match, which is the correct,
defensible behavior. This replaces the old gene-level approach, which
could produce inflated counts (e.g. 16) that weren't real position-level
findings.
"""
from __future__ import annotations

import csv
import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.family.carrier_screen import CarrierVariant, screen_couple
from src.family.trio_phasing import Variant, phase_trio
from src.visualization.graph_builders import carrier_network_graph, trio_pedigree_graph
from scripts.parse_trio_regions import build_trio_fixture

sys.path.insert(0, str(Path(__file__).resolve().parent))
from tests.visual_test import render  # reuse the pyvis renderer

CLINVAR_CSV = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "clinvar_panel.csv"
CLINVAR_COORDS_CSV = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "clinvar_panel_with_coords.csv"

PATHOGENIC_LABELS = {"Pathogenic", "Likely Pathogenic", "Pathogenic/Likely Pathogenic"}


def load_real_clinvar_by_gene() -> dict[str, list[CarrierVariant]]:
    by_gene: dict[str, list[CarrierVariant]] = {}
    with open(CLINVAR_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            by_gene.setdefault(row["gene"], []).append(
                CarrierVariant(row["gene"], row["variant_id"], row["classification"])
            )
    return by_gene


def build_position_level_lookup(coords_csv_path: Path) -> dict[tuple[str, int, str, str], bool]:
    """
    Position-exact pathogenic lookup, built from clinvar_panel_with_coords.csv.

    Keys are (chrom, pos, ref, alt) tuples matching Variant.key()'s exact
    format -- chrom already carries the "chr" prefix and pos is an int,
    both written that way by vep_coordinate_lookup.py's _extract_coords(),
    so no reformatting is needed here.

    Only rows with real resolved coordinates (non-blank chrom/pos/ref/alt)
    AND a Pathogenic/Likely Pathogenic classification are included. Rows
    that VEP couldn't resolve (blank coordinate columns) are skipped --
    they simply can't participate in a position-exact match.
    """
    lookup: dict[tuple[str, int, str, str], bool] = {}
    skipped_unresolved = 0
    with open(coords_csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if not (row.get("chrom") and row.get("pos") and row.get("ref") and row.get("alt")):
                skipped_unresolved += 1
                continue
            if row["classification"] not in PATHOGENIC_LABELS:
                continue
            key = (row["chrom"], int(row["pos"]), row["ref"], row["alt"])
            lookup[key] = True
    print(
        f"Position-exact pathogenic lookup built: {len(lookup)} real ClinVar "
        f"pathogenic/likely-pathogenic position(s) loaded "
        f"({skipped_unresolved} row(s) skipped -- no resolved coordinates)"
    )
    return lookup


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
    # ancestry is optional context only -- doesn't change which genes get
    # flagged, just attaches a real published carrier-rate figure where
    # available. "ashkenazi_jewish" chosen here since it has well-established
    # rates for both CFTR and ASPA/Canavan, the two genes this synthetic
    # couple already flags.
    result = screen_couple(a, b, ancestry="ashkenazi_jewish")
    print(result.summary())
    graph = carrier_network_graph("Partner A", "Partner B", result)
    render(graph, "carrier_network_real.html", "Carrier network (real ClinVar)")

    print("\n=== Trio phasing on REAL NA12878 trio genotypes ===")
    child, mother, father = build_trio_fixture()

    pathogenic_lookup = build_position_level_lookup(CLINVAR_COORDS_CSV)

    phasing = phase_trio(child, mother, father, pathogenic_lookup)
    print(phasing.summary())

    print("\nDe novo variants, with position-exact match status:")
    for pv in phasing.de_novo_variants:
        match_tag = " [POSITION-EXACT ClinVar pathogenic match]" if pv.is_pathogenic else ""
        print(f"  {pv.explain()}{match_tag}")

    pedigree = trio_pedigree_graph(phasing, mother_label="NA12892", father_label="NA12891", child_label="NA12878")
    render(pedigree, "pedigree_real.html", "Trio pedigree (real 1000G)")
