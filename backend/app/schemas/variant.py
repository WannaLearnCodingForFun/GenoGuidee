"""
Canonical internal variant representation.

Every variant entering the research engine — from a VCF, a curated dataset, or
an API request — is converted into a `CanonicalVariant`. Genome builds are
explicit and never mixed silently: any operation combining two variants MUST
compare `genome_build` first (see `assert_same_build`).

The schema is deliberately germline-first but carries `variant_context` so
somatic logic can be added without a schema break, and the coordinate model
(pos/ref/alt + `end` for symbolic alleles) leaves room for CNV/SV extensions.
"""
from __future__ import annotations

import hashlib
import re
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field, field_validator, model_validator


class GenomeBuild(str, Enum):
    GRCH38 = "GRCh38"
    GRCH37 = "GRCh37"


class VariantType(str, Enum):
    SNV = "SNV"
    MNV = "MNV"
    INSERTION = "insertion"
    DELETION = "deletion"
    INDEL = "indel"           # mixed-length substitution
    DUPLICATION = "duplication"
    # extension points (schema-ready, logic NOT IMPLEMENTED yet):
    CNV = "CNV"
    SV = "SV"


class Consequence(str, Enum):
    MISSENSE = "missense_variant"
    SYNONYMOUS = "synonymous_variant"
    STOP_GAINED = "stop_gained"
    STOP_LOST = "stop_lost"
    START_LOST = "start_lost"
    FRAMESHIFT = "frameshift_variant"
    INFRAME_INSERTION = "inframe_insertion"
    INFRAME_DELETION = "inframe_deletion"
    SPLICE_DONOR = "splice_donor_variant"          # canonical ±2 donor
    SPLICE_ACCEPTOR = "splice_acceptor_variant"    # canonical ±2 acceptor
    SPLICE_REGION = "splice_region_variant"
    INTRON = "intron_variant"
    UTR5 = "5_prime_UTR_variant"
    UTR3 = "3_prime_UTR_variant"
    UPSTREAM = "upstream_gene_variant"
    DOWNSTREAM = "downstream_gene_variant"
    INTERGENIC = "intergenic_variant"
    OTHER = "other"


class VariantContext(str, Enum):
    GERMLINE = "GERMLINE"
    SOMATIC = "SOMATIC"       # opt-in for the external oncology ranking connector;
                              # germline ACMG/AMP rules are still applied unchanged


class Zygosity(str, Enum):
    HETEROZYGOUS = "heterozygous"
    HOMOZYGOUS = "homozygous"
    HEMIZYGOUS = "hemizygous"
    UNKNOWN = "unknown"


_VALID_CHROMS = {str(i) for i in range(1, 23)} | {"X", "Y", "MT"}
_ALLELE_RE = re.compile(r"^[ACGTN]+$", re.IGNORECASE)


class CanonicalVariant(BaseModel):
    """Normalized, build-explicit variant record."""

    genome_build: GenomeBuild
    chromosome: str
    position: int = Field(gt=0, description="1-based POS of the normalized allele")
    reference: str
    alternate: str
    end: Optional[int] = Field(default=None, description="END for symbolic/CNV/SV alleles")

    variant_type: VariantType
    variant_context: VariantContext = VariantContext.GERMLINE

    # nomenclature / mapping
    hgvs_g: Optional[str] = None
    hgvs_c: Optional[str] = None
    hgvs_p: Optional[str] = None
    transcript_id: Optional[str] = None
    gene: Optional[str] = None
    gene_id: Optional[str] = None
    exon: Optional[str] = None
    consequence: Optional[Consequence] = None

    # call-level metadata (from VCF sample columns; None when not from a VCF)
    zygosity: Zygosity = Zygosity.UNKNOWN
    allele_depth: Optional[int] = None
    read_depth: Optional[int] = None
    vaf: Optional[float] = Field(default=None, ge=0.0, le=1.0)
    qual: Optional[float] = None
    filter_status: Optional[str] = None

    @field_validator("chromosome", mode="before")
    @classmethod
    def _norm_chrom(cls, v: str) -> str:
        c = str(v).removeprefix("chr").removeprefix("Chr").upper()
        c = {"M": "MT", "23": "X", "24": "Y"}.get(c, c)
        if c not in _VALID_CHROMS:
            raise ValueError(f"invalid chromosome: {v!r}")
        return c

    @field_validator("reference", "alternate")
    @classmethod
    def _norm_allele(cls, v: str) -> str:
        v = str(v).upper()
        if not _ALLELE_RE.match(v):
            raise ValueError(f"invalid allele: {v!r} (symbolic/SV alleles not yet supported)")
        return v

    @model_validator(mode="after")
    def _check(self) -> "CanonicalVariant":
        if self.reference == self.alternate:
            raise ValueError("reference and alternate alleles are identical")
        return self

    # ------------------------------------------------------------------
    @property
    def variant_id(self) -> str:
        """Canonical, build-explicit variant identifier."""
        return f"{self.genome_build.value}:{self.chromosome}:{self.position}:{self.reference}>{self.alternate}"

    @property
    def input_hash(self) -> str:
        return hashlib.sha256(self.variant_id.encode()).hexdigest()

    @staticmethod
    def infer_type(ref: str, alt: str) -> VariantType:
        if len(ref) == 1 and len(alt) == 1:
            return VariantType.SNV
        if len(ref) == len(alt):
            return VariantType.MNV
        if len(ref) == 1 and len(alt) > 1 and alt.startswith(ref):
            return VariantType.INSERTION
        if len(alt) == 1 and len(ref) > 1 and ref.startswith(alt):
            return VariantType.DELETION
        return VariantType.INDEL

    @classmethod
    def from_vcf_fields(
        cls,
        build: GenomeBuild,
        chrom: str,
        pos: int,
        ref: str,
        alt: str,
        **kwargs,
    ) -> "CanonicalVariant":
        return cls(
            genome_build=build,
            chromosome=chrom,
            position=pos,
            reference=ref,
            alternate=alt,
            variant_type=cls.infer_type(ref.upper(), alt.upper()),
            **kwargs,
        )


def assert_same_build(a: CanonicalVariant, b: CanonicalVariant) -> None:
    if a.genome_build != b.genome_build:
        raise ValueError(
            f"genome build mismatch: {a.genome_build.value} vs {b.genome_build.value} "
            "— coordinate systems must never be silently mixed"
        )


# Consequence groups used by the ACMG engine and feature builder
NULL_CONSEQUENCES = {
    Consequence.STOP_GAINED,
    Consequence.FRAMESHIFT,
    Consequence.SPLICE_DONOR,
    Consequence.SPLICE_ACCEPTOR,
    Consequence.START_LOST,
}

PROTEIN_LENGTH_CHANGING = {
    Consequence.INFRAME_INSERTION,
    Consequence.INFRAME_DELETION,
    Consequence.STOP_LOST,
}
