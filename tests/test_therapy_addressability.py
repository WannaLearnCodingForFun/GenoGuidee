"""Phase B4 — explicit therapy_addressable / therapy_block_reason bridge."""
from __future__ import annotations

from app.services.drug_recommendation import classify_therapy_addressability


def test_egfr_missense_is_addressable():
    r = classify_therapy_addressability("p.Leu858Arg")
    assert r.therapy_addressable is True
    assert r.protein_short == "L858R"
    assert r.therapy_block_reason is None


def test_brca1_frameshift_is_not_addressable():
    # GRCh38:17:43057062:T>TG is a BRCA1 frameshift; its protein HGVS form.
    r = classify_therapy_addressability("p.Gln1756fs")
    assert r.therapy_addressable is False
    assert r.protein_short is None
    assert "frameshift" in r.therapy_block_reason.lower()


def test_genomic_coordinate_is_not_addressable():
    r = classify_therapy_addressability("GRCh38:17:43057062:T>TG")
    assert r.therapy_addressable is False
    assert r.therapy_block_reason


def test_missing_hgvs_p_is_not_addressable():
    r = classify_therapy_addressability(None)
    assert r.therapy_addressable is False
    assert r.therapy_block_reason


def test_indel_is_not_addressable():
    r = classify_therapy_addressability("p.Phe508del")
    assert r.therapy_addressable is False
    assert "indel" in r.therapy_block_reason.lower() or "cnv" in r.therapy_block_reason.lower()
