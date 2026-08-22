"""
trio_phasing.py — parent-of-origin and de novo variant detection for a trio
(mother, father, child).

Per the guide: use the NA12878 trio (mother-father-child, public, standard
benchmark) as demo/test data.

Logic (simplified — no read-based phasing, genotype-presence only):
  For each child variant:
    - present in mother only  -> maternal
    - present in father only  -> paternal
    - present in both parents -> inherited (ambiguous origin without further info)
    - present in neither parent -> de novo
  De novo variants that also score pathogenic in the Phase 1 pipeline
  (reconcile.py) are flagged as high-priority — de novo pathogenic variants
  are clinically significant regardless of family history.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Optional


class Origin(Enum):
    MATERNAL = "maternal"
    PATERNAL = "paternal"
    BOTH_PARENTS = "inherited (both parents)"
    DE_NOVO = "de novo"


@dataclass(frozen=True)
class Variant:
    """Minimal variant identity for presence/absence comparison across a trio."""
    chrom: str
    pos: int
    ref: str
    alt: str
    gene: Optional[str] = None

    def key(self) -> tuple[str, int, str, str]:
        return (self.chrom, self.pos, self.ref, self.alt)


@dataclass
class PhasedVariant:
    variant: Variant
    origin: Origin
    is_pathogenic: Optional[bool] = None  # filled in by caller from reconcile.py output

    @property
    def high_priority(self) -> bool:
        return self.origin == Origin.DE_NOVO and self.is_pathogenic is True

    def explain(self) -> str:
        gene = f"{self.variant.gene} " if self.variant.gene else ""
        loc = f"{self.variant.chrom}:{self.variant.pos}{self.variant.ref}>{self.variant.alt}"
        flag = "  *** DE NOVO + PATHOGENIC ***" if self.high_priority else ""
        return f"{gene}{loc} — {self.origin.value}{flag}"


@dataclass
class TrioPhasingResult:
    phased_variants: list[PhasedVariant] = field(default_factory=list)

    @property
    def de_novo_variants(self) -> list[PhasedVariant]:
        return [pv for pv in self.phased_variants if pv.origin == Origin.DE_NOVO]

    @property
    def high_priority_variants(self) -> list[PhasedVariant]:
        return [pv for pv in self.phased_variants if pv.high_priority]

    def summary(self) -> str:
        lines = [f"Phased {len(self.phased_variants)} child variant(s):\n"]
        for pv in self.phased_variants:
            lines.append(f"  {pv.explain()}")
        lines.append("")
        lines.append(f"De novo: {len(self.de_novo_variants)}")
        lines.append(f"High-priority (de novo + pathogenic): {len(self.high_priority_variants)}")
        return "\n".join(lines)


def phase_trio(
    child_variants: list[Variant],
    mother_variants: list[Variant],
    father_variants: list[Variant],
    pathogenic_lookup: Optional[dict[tuple[str, int, str, str], bool]] = None,
) -> TrioPhasingResult:
    """
    pathogenic_lookup: optional {variant_key: is_pathogenic} map, typically built
    by running each child variant through reconcile.py beforehand. If omitted,
    is_pathogenic stays None and high_priority flagging is skipped.
    """
    mother_keys = {v.key() for v in mother_variants}
    father_keys = {v.key() for v in father_variants}
    pathogenic_lookup = pathogenic_lookup or {}

    phased: list[PhasedVariant] = []
    for cv in child_variants:
        key = cv.key()
        in_mother = key in mother_keys
        in_father = key in father_keys

        if in_mother and in_father:
            origin = Origin.BOTH_PARENTS
        elif in_mother:
            origin = Origin.MATERNAL
        elif in_father:
            origin = Origin.PATERNAL
        else:
            origin = Origin.DE_NOVO

        phased.append(PhasedVariant(
            variant=cv,
            origin=origin,
            is_pathogenic=pathogenic_lookup.get(key),
        ))

    return TrioPhasingResult(phased_variants=phased)


if __name__ == "__main__":
    # Synthetic trio — mirrors NA12878-style structure for a quick smoke test.
    # Swap in real NA12878 trio VCF variants once downloaded.
    mother_vars = [
        Variant("chr7", 117559590, "C", "T", gene="CFTR"),
        Variant("chr11", 5227002, "A", "G", gene="HBB"),
    ]
    father_vars = [
        Variant("chr7", 117559590, "C", "T", gene="CFTR"),
        Variant("chr13", 20189253, "G", "A", gene="GJB2"),
    ]
    child_vars = [
        Variant("chr7", 117559590, "C", "T", gene="CFTR"),   # in both parents
        Variant("chr11", 5227002, "A", "G", gene="HBB"),      # maternal only
        Variant("chr13", 20189253, "G", "A", gene="GJB2"),    # paternal only
        Variant("chr17", 41244936, "G", "A", gene="BRCA1"),   # de novo
    ]

    # Pretend BRCA1 de novo variant was scored pathogenic by reconcile.py
    pathogenic_lookup = {
        ("chr17", 41244936, "G", "A"): True,
    }

    print("=== Test: trio phasing ===\n")
    result = phase_trio(child_vars, mother_vars, father_vars, pathogenic_lookup)
    print(result.summary())
