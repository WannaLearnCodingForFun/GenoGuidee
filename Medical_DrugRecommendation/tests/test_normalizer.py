"""Unit tests for entity normalizer module."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from preprocessing.normalizer import (
    normalize_disease,
    normalize_gene,
    normalize_payload,
    normalize_variant,
)


def test_normalize_gene() -> None:
    assert normalize_gene("erbb1") == "EGFR"
    assert normalize_gene("her1") == "EGFR"
    assert normalize_gene("b-raf") == "BRAF"
    assert normalize_gene("k-ras") == "KRAS"
    assert normalize_gene("p53") == "TP53"
    assert normalize_gene("EGFR") == "EGFR"


def test_normalize_variant() -> None:
    assert normalize_variant("L858R") == "L858R"
    assert normalize_variant("p.L858R") == "L858R"
    assert normalize_variant("p.Leu858Arg") == "L858R"
    assert normalize_variant("V600E") == "V600E"
    assert normalize_variant("p.Val600Glu") == "V600E"
    assert normalize_variant("Amplification") == "AMPLIFICATION"


def test_normalize_disease() -> None:
    assert normalize_disease("nsclc") == "Non-Small Cell Lung Cancer"
    assert normalize_disease("LUNG ADENOCARCINOMA") == "Non-Small Cell Lung Cancer"
    assert normalize_disease("melanoma") == "Melanoma"
    assert normalize_disease("crc") == "Colorectal Cancer"
    assert normalize_disease("gist") == "Gastrointestinal Stromal Tumor"


def test_normalize_payload() -> None:
    payload = {"gene": "erbb1", "variant": "p.Leu858Arg", "disease": "nsclc"}
    norm = normalize_payload(payload)
    assert norm["gene"] == "EGFR"
    assert norm["variant"] == "L858R"
    assert norm["disease"] == "Non-Small Cell Lung Cancer"
