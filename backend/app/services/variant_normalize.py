"""Deterministic canonical variant identity. Formatting must not create duplicates."""
from __future__ import annotations

import re
from typing import Any, Optional

_CHR = re.compile(r"^CHR", re.I)
_HGVS = re.compile(r"^(?:c|p|n|g|m)\.", re.I)


def normalize_chromosome(chrom: Any) -> str:
    raw = str(chrom or "").strip().upper()
    raw = _CHR.sub("", raw)
    if raw in {"MT", "MITO", "MITOCHONDRIA"}:
        return "M"
    return raw


def normalize_allele(allele: Any) -> str:
    return str(allele or "").strip().upper().replace(" ", "")


def canonical_variant_id(
    *,
    chromosome: Any = None,
    position: Any = None,
    reference: Any = None,
    alternate: Any = None,
    genome_build: Any = "GRCh38",
    hgvs: Any = None,
    gene: Any = None,
) -> str:
    chrom = normalize_chromosome(chromosome)
    ref = normalize_allele(reference)
    alt = normalize_allele(alternate)
    build = str(genome_build or "GRCh38").strip() or "GRCh38"
    try:
        pos = int(position)
    except (TypeError, ValueError):
        pos = None
    if chrom and pos is not None and ref and alt:
        return f"{build}:{chrom}:{pos}:{ref}>{alt}"
    hgvs_s = str(hgvs or "").strip()
    gene_s = str(gene or "").strip().upper()
    if hgvs_s and _HGVS.match(hgvs_s):
        return f"{build}:{gene_s}:{hgvs_s}" if gene_s else f"{build}:{hgvs_s}"
    if gene_s and hgvs_s:
        return f"{build}:{gene_s}:{hgvs_s}"
    raise ValueError("insufficient fields for a stable canonical variant id")


def same_variant(left: dict[str, Any], right: dict[str, Any]) -> bool:
    try:
        return canonical_id_from_record(left) == canonical_id_from_record(right)
    except ValueError:
        return False


def canonical_id_from_record(rec: dict[str, Any]) -> str:
    existing = rec.get("canonical_variant_id") or rec.get("normalized_variant")
    if existing and ":" in str(existing):
        chrom = normalize_chromosome(rec.get("chromosome"))
        if chrom and rec.get("position") is not None and rec.get("reference") and rec.get("alternate"):
            return canonical_variant_id(
                chromosome=rec.get("chromosome"),
                position=rec.get("position"),
                reference=rec.get("reference"),
                alternate=rec.get("alternate"),
                genome_build=rec.get("genome_build") or "GRCh38",
            )
        return str(existing)
    return canonical_variant_id(
        chromosome=rec.get("chromosome"),
        position=rec.get("position"),
        reference=rec.get("reference"),
        alternate=rec.get("alternate"),
        genome_build=rec.get("genome_build") or "GRCh38",
        hgvs=rec.get("hgvs") or rec.get("hgvs_c"),
        gene=rec.get("gene"),
    )


def parse_loose_spec(spec: str) -> Optional[dict[str, str]]:
    """Accept '17:43057062 T>G', 'chr17:43057062:T:G', 'GRCh38:17:43057062:T>G'."""
    s = spec.strip().replace(" ", "")
    s = s.replace("chr", "", 1) if s.lower().startswith("chr") else s
    m = re.match(r"^(?:(GRCh3[78]):)?([0-9XYM]+):(\d+)[:>]?([ACGTN]+)[>/:]([ACGTN]+)$", s, re.I)
    if not m:
        return None
    build, chrom, pos, ref, alt = m.groups()
    return {
        "genome_build": build or "GRCh38",
        "chromosome": normalize_chromosome(chrom),
        "position": pos,
        "reference": normalize_allele(ref),
        "alternate": normalize_allele(alt),
    }
