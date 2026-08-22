import json

from app.provenance2 import ledger


def test_v2_chain_roundtrip(tmp_path, monkeypatch):
    db = tmp_path / "ledger.db"
    monkeypatch.setattr(ledger, "DB_PATH", db)
    rec = ledger.record_interpretation(
        input_hash="a" * 64,
        output_hash="b" * 64,
        annotation_version="test",
        model_version=None,
        model_hash=None,
        acmg_rule_version="acmg-test",
        knowledge_graph_version="kg-test",
        phenotype_version=None,
        evidence_snapshot={"variant_id": "GRCh38:1:1:A>T"},
        operator="pytest",
    )
    assert rec["interpretation_id"].startswith("INT-")
    v = ledger.verify_interpretation(rec["interpretation_id"])
    assert v["verified"] is True
    chain = ledger.verify_chain()
    assert chain["valid"] is True
    assert chain["blocks"] >= 1
    fetched = ledger.get_record(rec["interpretation_id"])
    assert fetched is not None
    assert rec["evidence_snapshot_hash"]
    assert rec["input_hash"] == "a" * 64
    assert "ATCT" not in json.dumps(fetched)  # raw alleles from snapshot must not be stored
