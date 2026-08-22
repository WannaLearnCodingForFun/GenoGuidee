from research.training.esm_representation import represent


def test_esm_without_sequence_is_not_configured():
    out = represent(None, None)
    assert out["availability"] == "SOURCE_NOT_CONFIGURED"


def test_esm_demo_hash_is_labeled():
    out = represent("MKT" * 20, "MKT" * 19 + "A", allow_demo_hash=True)
    assert out["availability"] in {"DEMO_HASH", "INTERFACE_READY", "NOT_INSTALLED"}
    if out["availability"] == "DEMO_HASH":
        assert "SYNTHETIC" in out["warning"]
