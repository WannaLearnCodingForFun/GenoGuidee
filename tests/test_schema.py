"""Canonical variant schema — no silent genome-build mixing."""
import pytest

from app.schemas.variant import CanonicalVariant, GenomeBuild, VariantType, assert_same_build


def test_snv_id_and_type():
    v = CanonicalVariant.from_vcf_fields(GenomeBuild.GRCH38, "chr17", 7674220, "C", "T")
    assert v.chromosome == "17"
    assert v.variant_type == VariantType.SNV
    assert v.variant_id == "GRCh38:17:7674220:C>T"
    assert len(v.input_hash) == 64


def test_rejects_identical_alleles():
    with pytest.raises(ValueError):
        CanonicalVariant.from_vcf_fields(GenomeBuild.GRCH38, "1", 10, "A", "A")


def test_rejects_invalid_chrom():
    with pytest.raises(ValueError):
        CanonicalVariant.from_vcf_fields(GenomeBuild.GRCH38, "chr99", 1, "A", "T")


def test_never_mix_builds():
    a = CanonicalVariant.from_vcf_fields(GenomeBuild.GRCH38, "1", 1, "A", "T")
    b = CanonicalVariant.from_vcf_fields(GenomeBuild.GRCH37, "1", 1, "A", "T")
    with pytest.raises(ValueError, match="must never be silently mixed"):
        assert_same_build(a, b)


def test_indel_type():
    v = CanonicalVariant.from_vcf_fields(GenomeBuild.GRCH38, "7", 117559590, "ATCT", "A")
    assert v.variant_type == VariantType.DELETION
