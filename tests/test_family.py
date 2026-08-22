from app.phenotype.family import (
    analyze_trio, compound_het_candidates, couple_carrier_overlap, x_linked_flags,
)


def test_trio_de_novo():
    child = [{"variant_id": "GRCh38:17:1:A>T", "gene": "TP53"}]
    out = analyze_trio(child, mother=[], father=[])
    assert out["de_novo_candidates"] == ["GRCh38:17:1:A>T"]


def test_compound_het_phased():
    child = [
        {"variant_id": "GRCh38:7:1:A>T", "gene": "CFTR"},
        {"variant_id": "GRCh38:7:2:C>G", "gene": "CFTR"},
    ]
    mother = [{"variant_id": "GRCh38:7:1:A>T", "gene": "CFTR"}]
    father = [{"variant_id": "GRCh38:7:2:C>G", "gene": "CFTR"}]
    out = compound_het_candidates(child, mother, father)
    assert out["phase_known"] is True
    assert out["putative_compound_hets_phased"][0]["gene"] == "CFTR"


def test_couple_shared_gene():
    a = [{"variant_id": "GRCh38:7:1:A>T", "gene": "CFTR"}]
    b = [{"variant_id": "GRCh38:7:9:C>G", "gene": "CFTR"}]
    out = couple_carrier_overlap(a, b)
    assert out["shared_genes"] == ["CFTR"]


def test_x_linked_male():
    out = x_linked_flags([{"variant_id": "GRCh38:X:100:A>T", "gene": "DMD"}], sex="male")
    assert out["hemizygosity_relevant"] is True
    assert out["x_chromosome_variants"]
