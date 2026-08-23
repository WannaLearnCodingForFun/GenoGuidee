# scripts/rag_recommend.py
r"""
rag_recommend.py -- retrieval-augmented clinical summary for a flagged
variant or gene, built entirely from real data already in this project:

  RETRIEVAL sources (all real, no invented text):
    - clinvar_panel_with_coords.csv: classification, conditions, disease_db_xrefs
    - carrier_screen.py's ANCESTRY_CARRIER_RATES: real published carrier
      frequencies
    - mutation_chain.py's find_hotspots(): real recurring-position data

  GENERATION: templated assembly of the above into a short, readable
  summary paragraph. This is NOT a free-text LLM call generating novel
  clinical claims -- every sentence traces back to a specific retrieved
  field, and the summary explicitly cites which field each claim came
  from. This keeps the "advisory, never prescriptive" posture used
  elsewhere in this project: it summarizes what real sources say, it does
  not recommend a course of action.

WHY THIS DESIGN (not embeddings/vector search): the actual questions this
project needs answered ("what does ClinVar say about this variant", "what's
the real carrier rate for this gene") are exact-match lookups against
structured fields you already have -- gene, variant_id, classification.
Embeddings/similarity search solve a different problem (fuzzy retrieval
over large unstructured text corpora), which isn't what's needed here and
would add a vector-DB dependency for no real retrieval benefit at this
data scale (~550 rows).

Usage:
    python -m scripts.rag_recommend --gene CFTR
    python -m scripts.rag_recommend --gene CFTR --variant-id c.1521_1523delCTT
"""
from __future__ import annotations

import argparse
import csv
import sys
from dataclasses import dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.family.carrier_screen import get_carrier_rate_context, RECESSIVE_GENE_PANEL
from src.family.mutation_chain import find_hotspots

CLINVAR_COORDS_CSV = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "clinvar_panel_with_coords.csv"


@dataclass
class RetrievedFacts:
    gene: str
    disease: str | None
    matched_rows: list[dict]           # raw CSV rows matching gene (+ variant_id if given)
    ancestry_rate: str | None
    ancestry_used: str | None
    hotspot_positions: list[int]       # protein positions with >=2 recurring pathogenic variants


def retrieve(gene: str, variant_id: str | None = None, ancestry: str | None = None) -> RetrievedFacts:
    """
    Pure retrieval step -- no text generation here, just gathering the real
    facts a summary will be built from. Kept separate from formatting so
    each retrieved fact is independently inspectable/testable.
    """
    if not CLINVAR_COORDS_CSV.exists():
        raise FileNotFoundError(f"{CLINVAR_COORDS_CSV} not found -- run vep_coordinate_lookup.py first")

    matched_rows = []
    with open(CLINVAR_COORDS_CSV, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["gene"] != gene:
                continue
            if variant_id and row["variant_id"] != variant_id:
                continue
            matched_rows.append(row)

    disease = RECESSIVE_GENE_PANEL.get(gene)
    ancestry_rate = get_carrier_rate_context(gene, ancestry)

    # Hotspot detection needs protein_pos -- reuse the same parsing logic
    # as mutation_chain_data.py rather than duplicating the regex here.
    from scripts.mutation_chain_data import parse_protein_pos
    hotspot_input = [
        {
            "gene": gene,
            "variant_id": r["variant_id"],
            "protein_pos": parse_protein_pos(r.get("title", "")),
            "classification": r["classification"],
        }
        for r in matched_rows
    ]
    # For a single-variant query, hotspots should reflect the WHOLE gene's
    # data, not just the one matched row -- so re-query without variant_id
    # filtering when a specific variant was requested.
    if variant_id:
        all_gene_rows = []
        with open(CLINVAR_COORDS_CSV, encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row["gene"] == gene:
                    all_gene_rows.append(row)
        hotspot_input = [
            {
                "gene": gene,
                "variant_id": r["variant_id"],
                "protein_pos": parse_protein_pos(r.get("title", "")),
                "classification": r["classification"],
            }
            for r in all_gene_rows
        ]

    hotspots = find_hotspots(hotspot_input, min_count=2)
    hotspot_positions = [h.protein_pos for h in hotspots]

    return RetrievedFacts(
        gene=gene,
        disease=disease,
        matched_rows=matched_rows,
        ancestry_rate=ancestry_rate,
        ancestry_used=ancestry,
        hotspot_positions=hotspot_positions,
    )


def generate_summary(facts: RetrievedFacts, summary_mode: bool = False) -> str:
    """
    Templated assembly -- every line is traceable to a specific retrieved
    field, no free-generated clinical claims. Explicitly advisory framing,
    consistent with the "never prescriptive" posture elsewhere in this
    project.

    summary_mode: when True and there are multiple matched variants (a
    gene-level query, no specific variant_id given), shows AGGREGATE stats
    (counts by classification, distinct conditions represented) instead of
    a full per-variant listing. Single-variant queries are unaffected --
    aggregating one row is meaningless, so full detail is always shown for
    a single match regardless of this flag.
    """
    lines: list[str] = []

    gene_disease = f"{facts.gene}" + (f" ({facts.disease})" if facts.disease else "")
    lines.append(f"=== Retrieval-grounded summary: {gene_disease} ===\n")

    if not facts.matched_rows:
        lines.append(f"No ClinVar entries found for this gene/variant in the local panel data.")
        return "\n".join(lines)

    if summary_mode and len(facts.matched_rows) > 1:
        classification_counts: dict[str, int] = {}
        conditions_seen: dict[str, int] = {}
        for row in facts.matched_rows:
            classification_counts[row["classification"]] = classification_counts.get(row["classification"], 0) + 1
            for cond in (row.get("conditions") or "").split("; "):
                cond = cond.strip()
                if cond:
                    conditions_seen[cond] = conditions_seen.get(cond, 0) + 1

        lines.append(f"{len(facts.matched_rows)} ClinVar entries in local panel data for {facts.gene}:")
        for classification, count in sorted(classification_counts.items(), key=lambda x: -x[1]):
            lines.append(f"  {classification}: {count}")
        lines.append("")
        if conditions_seen:
            lines.append("Condition(s) represented across these entries (per ClinVar):")
            for cond, count in sorted(conditions_seen.items(), key=lambda x: -x[1]):
                lines.append(f"  {cond}: {count} variant(s)")
            lines.append("")
        lines.append("(Use --variant-id for full per-variant detail, or omit --summary for the full listing.)")
        lines.append("")
    else:
        # Per-variant ClinVar facts -- full detail (single-variant query, or
        # summary_mode not requested)
        for row in facts.matched_rows:
            lines.append(f"Variant: {row['variant_id']}")
            lines.append(f"  ClinVar classification: {row['classification']} "
                         f"(review status: {row['review_status'] or 'not specified'})")
            if row.get("conditions"):
                lines.append(f"  Associated condition(s) per ClinVar: {row['conditions']}")
            if row.get("disease_db_xrefs"):
                lines.append(f"  Cross-referenced in: {row['disease_db_xrefs']}")
            lines.append("")

    # Ancestry-specific carrier rate, if available
    if facts.ancestry_rate:
        ancestry_note = f" ({facts.ancestry_used} ancestry specified)" if facts.ancestry_used else " (general population)"
        lines.append(f"Population carrier rate for {facts.gene}{ancestry_note}: {facts.ancestry_rate}")
        lines.append("")

    # Hotspot context
    if facts.hotspot_positions:
        lines.append(
            f"Note: protein position(s) {facts.hotspot_positions} in {facts.gene} recur across "
            f"multiple independent pathogenic ClinVar entries in this panel -- worth noting as a "
            f"potential mutational hotspot region, though this reflects ClinVar's curated "
            f"submissions and may partly reflect research/submission bias rather than confirmed "
            f"structural/functional significance."
        )
        lines.append("")

    lines.append(
        "ADVISORY: this summary reflects what the retrieved sources state. It is not a "
        "diagnosis or a treatment recommendation. Any clinical decision should involve a "
        "qualified genetic counselor or physician."
    )

    return "\n".join(lines)


def main():
    parser = argparse.ArgumentParser(description="Retrieval-grounded clinical summary for a gene/variant")
    parser.add_argument("--gene", required=True, help="Gene symbol, e.g. CFTR")
    parser.add_argument("--variant-id", default=None, help="Specific ClinVar variant_id (c. notation), optional")
    parser.add_argument("--ancestry", default=None, help="Ancestry label for carrier-rate context, optional")
    parser.add_argument("--summary", action="store_true",
                         help="Show aggregate stats instead of full per-variant listing (gene-level queries only)")
    args = parser.parse_args()

    facts = retrieve(args.gene, args.variant_id, args.ancestry)
    print(generate_summary(facts, summary_mode=args.summary))


if __name__ == "__main__":
    main()
