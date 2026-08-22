from app.bioinformatics.vcf import normalize_vcf, trim_alleles, validate_vcf


def test_validate_mini(mini_vcf):
    r = validate_vcf(mini_vcf)
    assert r["valid"] is True
    assert r["n_records"] == 5
    assert r["multiallelic_records"] == 1
    assert r["n_samples"] == 1


def test_trim_suffix_prefix():
    pos, ref, alt = trim_alleles(10, "ACGT", "AGT")
    assert (pos, ref, alt) == (10, "AC", "A")


def test_normalize_decomposes(mini_vcf, tmp_path):
    out = tmp_path / "norm.vcf"
    r = normalize_vcf(mini_vcf, output=out)
    assert r["success"] is True
    assert r["left_aligned"] is False
    assert r["decomposed"] == 1
    text = out.read_text()
    assert "NOT left-aligned" in text
    assert text.count("\n13\t") >= 2
