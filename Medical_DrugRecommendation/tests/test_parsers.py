"""Unit tests for CIViC and DGIdb dataset parsers."""

from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from preprocessing.civic_parser import CIViCParser
from preprocessing.dgidb_parser import DGIdbParser


def test_civic_parser_loading() -> None:
    parser = CIViCParser()
    parser.load_data()
    assert parser.loaded
    assert len(parser.evidence_items) > 0

    items = parser.get_evidence_by_variant("EGFR", "L858R", "NSCLC")
    assert len(items) > 0
    therapies = [t for it in items for t in it.therapies]
    assert "Osimertinib" in therapies or "Gefitinib" in therapies or "Erlotinib" in therapies


def test_dgidb_parser_loading() -> None:
    parser = DGIdbParser()
    parser.load_data()
    assert parser.loaded
    interactions = parser.get_interactions_for_gene("EGFR")
    assert len(interactions) > 0

    osim = parser.get_interaction("EGFR", "Osimertinib")
    if osim:
        assert osim.drug_is_approved
