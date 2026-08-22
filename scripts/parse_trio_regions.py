"""
Parses the region VCFs from remote_tabix_fetch.py and builds trio variant
lists for phase_trio().

IMPORTANT DATA-REALITY NOTE (confirmed this session via direct header
inspection of the fetched VCFs):

  NA12878 (child) IS present and real -- 1000 Genomes phase 3's main
  "unrelated individuals" panel includes her as one of its 2504 samples.

  NA12891 and NA12892 (her parents) are NOT present in this panel. That
  release deliberately excludes known relatives -- it's built to be an
  unrelated-individuals set for population allele-frequency stats, and
  only kept one representative per family. Confirmed directly: the CFTR
  region VCF header has exactly 2513 columns (9 fixed + 2504 samples),
  matching the unrelated-panel size, with NA12878 present and both parent
  IDs absent.

  Real parent genotypes for this trio exist in OTHER 1000 Genomes-adjacent
  releases (e.g. the NYGC 30x high-coverage release, on GRCh38) or in
  Illumina's Platinum Genomes project, but pulling from either is a fresh
  filename-discovery exercise and, for the NYGC release, a different
  reference build than what's used here.

  For now: child genotypes below are REAL. Parent genotypes are
  SYNTHETIC, generated from the real child variant list to be
  biologically plausible for demo purposes (see _synthesize_parents).
  State this explicitly in any demo or pitch material -- don't present
  the parent side as real 1000 Genomes data.
"""
from __future__ import annotations

import random
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.family.trio_phasing import Variant

TRIO_SAMPLES = {"child": "NA12878", "mother": "NA12892", "father": "NA12891"}
REGION_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "trio_regions"

# Synthetic parent assignment probabilities -- tuned so a run reliably
# produces at least one of each interesting case (maternal-only,
# paternal-only, both-parents/homozygous-demo, de-novo-demo) rather than
# leaving it to chance on a small (~14 variant) real variant set.
_MATERNAL_ONLY_P = 0.45
_PATERNAL_ONLY_P = 0.45   # cumulative: up to 0.90
_BOTH_PARENTS_P = 0.05    # cumulative: up to 0.95
# remaining ~0.05 -> withheld from both parents (de novo demo case)


def _has_alt(gt_field: str) -> bool:
    gt = gt_field.split(":")[0]
    alleles = gt.replace("|", "/").split("/")
    return any(a not in ("0", ".") for a in alleles)


def parse_region_vcf(path: Path) -> dict[str, list[Variant]]:
    """Parses one region VCF, returns real presence/absence per trio role
    for whichever sample columns actually exist in this file's header."""
    per_sample: dict[str, list[Variant]] = {k: [] for k in TRIO_SAMPLES}
    with open(path, encoding="utf-8") as f:
        header_cols = None
        for line in f:
            if line.startswith("##"):
                continue
            if line.startswith("#CHROM"):
                header_cols = line.rstrip("\n").split("\t")
                continue
            if header_cols is None:
                continue
            fields = line.rstrip("\n").split("\t")
            row = dict(zip(header_cols, fields))
            chrom, pos, ref, alt = row["#CHROM"], int(row["POS"]), row["REF"], row["ALT"]
            gene = path.stem  # region file is named e.g. CFTR.vcf
            for role, sample_id in TRIO_SAMPLES.items():
                if sample_id not in row:
                    continue  # sample not present in this file's panel -- expected for parents
                if _has_alt(row[sample_id]):
                    per_sample[role].append(
                        Variant(f"chr{chrom}", pos, ref, alt.split(",")[0], gene=gene)
                    )
    return per_sample


def _synthesize_parents(child_vars: list[Variant], seed: int = 11):
    """
    SYNTHETIC parent genotype generator -- see module docstring for why
    this exists. Not real 1000 Genomes data. Assigns each real child
    variant to a plausible parental origin so phase_trio() has something
    non-trivial to classify.

    Guarantees at least one de-novo case and one both-parents case when
    there are enough variants to do so, rather than leaving those
    demo-relevant outcomes to random chance -- with only ~14 real variants
    and a 5% per-variant probability for each rare case, a given run can
    easily produce zero of either, which isn't a bug but also isn't a
    useful thing to build a demo around.
    """
    rng = random.Random(seed)
    mother_vars, father_vars = [], []

    forced_de_novo_idx = 0 if len(child_vars) >= 1 else None
    forced_both_idx = 1 if len(child_vars) >= 2 else None

    for i, v in enumerate(child_vars):
        if i == forced_de_novo_idx:
            continue  # withheld from both parents -- guaranteed de novo demo case
        if i == forced_both_idx:
            mother_vars.append(v)
            father_vars.append(v)  # guaranteed both-parents / homozygous demo case
            continue

        roll = rng.random()
        if roll < _MATERNAL_ONLY_P:
            mother_vars.append(v)
        elif roll < _MATERNAL_ONLY_P + _PATERNAL_ONLY_P:
            father_vars.append(v)
        elif roll < _MATERNAL_ONLY_P + _PATERNAL_ONLY_P + _BOTH_PARENTS_P:
            mother_vars.append(v)
            father_vars.append(v)
        # else: withheld from both -- de novo demo case
    return mother_vars, father_vars


def build_trio_fixture():
    """Returns (child_vars, mother_vars, father_vars).
    child_vars: 100% real, from actual fetched 1000 Genomes region VCFs.
    mother_vars / father_vars: SYNTHETIC -- see module docstring."""
    child_vars: list[Variant] = []
    for vcf_path in sorted(REGION_DIR.glob("*.vcf")):
        per_sample = parse_region_vcf(vcf_path)
        child_vars += per_sample["child"]
        print(
            f"{vcf_path.stem}: child={len(per_sample['child'])} (real) "
            f"mother={len(per_sample['mother'])} father={len(per_sample['father'])} "
            f"(real parent data unavailable in this panel -- see module note)"
        )

    mother_vars, father_vars = _synthesize_parents(child_vars, seed=11)
    return child_vars, mother_vars, father_vars


if __name__ == "__main__":
    child, mother, father = build_trio_fixture()
    print(
        f"\nSummary: {len(child)} real child variant(s), "
        f"{len(mother)} synthetic maternal, {len(father)} synthetic paternal"
    )
    print("\nChild variants (real):")
    for v in child:
        print(f"  {v}")
    print("\nSynthetic maternal assignment:")
    for v in mother:
        print(f"  {v}")
    print("\nSynthetic paternal assignment:")
    for v in father:
        print(f"  {v}")
