# scripts/mutation_chain_data.py
r"""
Adapter: builds the variant-dict schema mutation_chain.py's accessors expect
(gene, variant_id, protein_pos, classification, alphamissense_score), from
your REAL data sources -- clinvar_panel_with_coords.csv + alphamissense.py's
DuckDB index -- instead of the made-up demo list in mutation_chain.py's
__main__ block.

WHY THIS EXISTS (confirmed by direct inspection of your real files):
  - clinvar_panel_with_coords.csv has NO "protein_pos" column at all -- only
    genomic chrom/pos. mutation_chain.py's _pos() assumed a dict key that
    doesn't exist, so it would silently return None for every real row
    (not an error -- a silent, empty-results failure).
  - alphamissense.py's lookup() returns an AlphaMissenseScore DATACLASS
    (fields: am_pathogenicity, protein_variant, ...), not a dict with an
    "alphamissense_score" key. mutation_chain.py's _score() would also
    silently return None on every real row for the same reason.

This module does NOT modify mutation_chain.py at all -- it only builds the
dict shape mutation_chain.py's find_hotspots()/build_heuristic_path()
already expect, by:
  1. Parsing protein position out of the ClinVar "title" field's HGVS
     protein notation, e.g. "...(p.Phe508del)" -> 508. Not all rows have
     resolvable protein notation (e.g. structural variants, splice-site
     changes with no p. notation) -- those get protein_pos=None, same as
     mutation_chain.py already handles for missing positions.
  2. Calling alphamissense.lookup() per row (using the row's real
     chrom/pos/ref/alt) to fetch am_pathogenicity, if a local AlphaMissense
     DuckDB index has been built. If no index exists yet (build_index() not
     run), every row gets alphamissense_score=None -- hotspot detection
     still works (it doesn't need scores), but build_heuristic_path() will
     return None for any gene (it requires >=2 variants with real scores).
"""
from __future__ import annotations

import csv
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scoring.alphamissense import lookup, DEFAULT_DB_PATH

CLINVAR_COORDS_CSV = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "clinvar_panel_with_coords.csv"

# Matches HGVS protein notation like "(p.Phe508del)", "(p.Gly542Ter)",
# "(p.Arg117His)" -- captures the numeric position in the middle.
# Does NOT match every possible protein HGVS variant (e.g. frameshift
# "fs" suffixes, extension notation) -- those return None rather than a
# wrong guess.
_PROTEIN_POS_RE = re.compile(r"\(p\.[A-Za-z]{3}(\d+)[A-Za-z]")


def parse_protein_pos(title: str) -> int | None:
    m = _PROTEIN_POS_RE.search(title)
    return int(m.group(1)) if m else None


def load_real_variants_for_mutation_chain(
    csv_path: Path = CLINVAR_COORDS_CSV,
    alphamissense_db_path: str = DEFAULT_DB_PATH,
    genes: list[str] | None = None,
) -> list[dict]:
    """
    Returns a list of dicts in the exact schema mutation_chain.py's
    find_hotspots() / build_heuristic_path() already expect:
        {gene, variant_id, protein_pos, classification, alphamissense_score}

    genes: optional filter to only load specific panel genes (faster if you
    only care about one gene's hotspots/path right now).

    AlphaMissense lookups are best-effort: if the local DuckDB index
    (alphamissense.py's build_index()) hasn't been built yet, every
    alphamissense_score comes back None and a warning is printed once --
    hotspot detection still works fine without it; the heuristic path
    function will just return None per gene until scores are available.
    """
    if not csv_path.exists():
        raise FileNotFoundError(f"{csv_path} not found -- run vep_coordinate_lookup.py first")

    am_index_available = Path(alphamissense_db_path).exists()
    if not am_index_available:
        print(
            f"NOTE: no AlphaMissense index found at {alphamissense_db_path} -- "
            f"alphamissense_score will be None for all variants. Hotspot detection "
            f"still works; build_heuristic_path() will return None until the index "
            f"is built (see alphamissense.py's __main__ for setup steps)."
        )

    variants: list[dict] = []
    no_protein_pos_count = 0
    no_score_count = 0

    with open(csv_path, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            gene = row["gene"]
            if genes is not None and gene not in genes:
                continue

            protein_pos = parse_protein_pos(row.get("title", ""))
            if protein_pos is None:
                no_protein_pos_count += 1

            am_score = None
            if am_index_available and row.get("chrom") and row.get("pos") and row.get("ref") and row.get("alt"):
                try:
                    score_obj = lookup(row["chrom"], int(row["pos"]), row["ref"], row["alt"], db_path=alphamissense_db_path)
                    if score_obj is not None:
                        am_score = score_obj.am_pathogenicity
                except Exception:
                    pass  # missense-only lookup; indels/nonsense variants correctly return nothing
            if am_score is None:
                no_score_count += 1

            variants.append({
                "gene": gene,
                "variant_id": row["variant_id"],
                "protein_pos": protein_pos,
                "classification": row["classification"],
                "alphamissense_score": am_score,
            })

    print(
        f"Loaded {len(variants)} real variant(s) for mutation_chain.py "
        f"({no_protein_pos_count} with no resolvable protein position, "
        f"{no_score_count} with no AlphaMissense score)"
    )
    return variants


if __name__ == "__main__":
    from src.family import mutation_chain  # local import to avoid a hard dependency at module load time

    real_variants = load_real_variants_for_mutation_chain()

    # Real hotspot detection, per panel gene present in the data
    genes_seen = sorted({v["gene"] for v in real_variants})
    print(f"\n=== Real hotspots by gene ({len(genes_seen)} gene(s)) ===")
    any_hotspots = False
    for gene in genes_seen:
        gene_variants = [v for v in real_variants if v["gene"] == gene]
        hotspots = mutation_chain.find_hotspots(gene_variants, min_count=2)
        if hotspots:
            any_hotspots = True
            print(f"\n{gene}:")
            for h in hotspots:
                print(f"  protein position {h.protein_pos}: {h.variant_count} pathogenic variant(s) -> {h.variant_ids}")
    if not any_hotspots:
        print("  No positions with >=2 recurring pathogenic variants found in current data "
              "(expected if protein_pos resolution or panel size is limited -- not a bug).")

    # Heuristic evolutionary path -- requires >=2 variants in the same gene
    # with a real AlphaMissense score. Only meaningful now that the local
    # index is built (see setup_alphamissense_index.py) -- before that,
    # every alphamissense_score was None and this would always return None.
    print(f"\n=== Heuristic evolutionary paths by gene (requires AlphaMissense index) ===")
    any_path = False
    for gene in genes_seen:
        gene_variants = [v for v in real_variants if v["gene"] == gene]
        path = mutation_chain.build_heuristic_path(gene, gene_variants)
        if path:
            any_path = True
            print(f"\n{gene}:")
            print(f"  {path.caveat}")
            for step in path.steps:
                pos_str = f"pos {step.protein_pos}" if step.protein_pos is not None else "pos unknown"
                print(f"  step {step.order}: {step.variant_id} ({pos_str}, "
                      f"AlphaMissense {step.alphamissense_score:.3f}) -- {step.cumulative_label}")
    if not any_path:
        print("  No gene has >=2 variants with a real AlphaMissense score yet -- "
              "confirm the index built successfully (data/processed/alphamissense.duckdb "
              "should exist) and that this gene's variants are missense (AlphaMissense "
              "only scores missense substitutions, not indels/nonsense/splice-site changes "
              "-- many ClinVar panel entries are indels, which will never get a score).")
