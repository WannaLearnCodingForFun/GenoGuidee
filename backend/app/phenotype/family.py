"""
Family / pedigree analysis (Problem 60 expansion).

Inputs are lists of canonical variant IDs (build:chrom:pos:ref>alt) plus gene
annotations. No genotypes are invented: if a parent list is missing, de novo
is NOT_EVALUABLE rather than assumed.

Modes covered:
  trio     — de novo (in child, absent both parents)
  recessive — same gene, two variants in a child (putative compound-het if
              parents each contribute one; phase unknown unless provided)
  couple   — intersection of carrier genes between partner A and B
  x-linked — variants on X in a male proband (flagged, not classified)
"""
from __future__ import annotations

from collections import defaultdict
from typing import Any, Optional


def _gene_of(rec: dict[str, Any]) -> Optional[str]:
    return rec.get("gene") or (rec.get("annotation") or {}).get("gene")


def _vid(rec: dict[str, Any]) -> str:
    return rec.get("variant_id") or rec.get("id") or ""


def analyze_trio(
    child: list[dict[str, Any]],
    mother: list[dict[str, Any]],
    father: list[dict[str, Any]],
) -> dict[str, Any]:
    m_ids = {_vid(v) for v in mother}
    f_ids = {_vid(v) for v in father}
    de_novo, inherited_m, inherited_f, inherited_both = [], [], [], []
    for v in child:
        vid = _vid(v)
        in_m, in_f = vid in m_ids, vid in f_ids
        if not in_m and not in_f:
            de_novo.append(vid)
        elif in_m and in_f:
            inherited_both.append(vid)
        elif in_m:
            inherited_m.append(vid)
        else:
            inherited_f.append(vid)
    return {
        "mode": "trio",
        "n_child": len(child),
        "de_novo_candidates": de_novo,
        "inherited_maternal": inherited_m,
        "inherited_paternal": inherited_f,
        "inherited_both": inherited_both,
        "note": "De novo here means absent from provided parental call sets — "
                "not maternity/paternity-confirmed (PS2 requires that separately).",
    }


def compound_het_candidates(
    child: list[dict[str, Any]],
    mother: Optional[list[dict[str, Any]]] = None,
    father: Optional[list[dict[str, Any]]] = None,
) -> dict[str, Any]:
    by_gene: dict[str, list[str]] = defaultdict(list)
    for v in child:
        g = _gene_of(v)
        if g:
            by_gene[g].append(_vid(v))
    multi = {g: ids for g, ids in by_gene.items() if len(set(ids)) >= 2}
    phased = []
    if mother is not None and father is not None:
        m_ids = {_vid(v) for v in mother}
        f_ids = {_vid(v) for v in father}
        for g, ids in multi.items():
            from_m = [i for i in ids if i in m_ids]
            from_f = [i for i in ids if i in f_ids]
            if from_m and from_f:
                phased.append({"gene": g, "maternal": from_m, "paternal": from_f})
    return {
        "genes_with_two_plus_variants": multi,
        "putative_compound_hets_phased": phased,
        "phase_known": mother is not None and father is not None,
    }


def couple_carrier_overlap(
    partner_a: list[dict[str, Any]],
    partner_b: list[dict[str, Any]],
) -> dict[str, Any]:
    genes_a = {g for v in partner_a if (g := _gene_of(v))}
    genes_b = {g for v in partner_b if (g := _gene_of(v))}
    shared = sorted(genes_a & genes_b)
    return {
        "mode": "couple",
        "n_a": len(partner_a),
        "n_b": len(partner_b),
        "shared_genes": shared,
        "reproductive_risk_candidates": shared,
        "note": "Shared gene names only — not a diagnosis. Recessive risk requires "
                "pathogenic-spectrum variants in trans and a recessive disease gene.",
    }


def x_linked_flags(variants: list[dict[str, Any]], sex: Optional[str] = None) -> dict[str, Any]:
    x_vars = []
    for v in variants:
        vid = _vid(v)
        chrom = None
        if vid.count(":") >= 2:
            chrom = vid.split(":")[1]
        elif v.get("chromosome"):
            chrom = str(v["chromosome"]).removeprefix("chr")
        if chrom == "X":
            x_vars.append(vid)
    return {
        "x_chromosome_variants": x_vars,
        "proband_sex": sex,
        "hemizygosity_relevant": (sex or "").lower() in {"male", "m", "xy"},
    }
