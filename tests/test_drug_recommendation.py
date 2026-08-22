"""Somatic therapy connector — mapper, safety isolation, mocked remote."""
from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from app.schemas.variant import CanonicalVariant, GenomeBuild, VariantContext
from app.services import drug_recommendation as DR

FIXTURE = json.loads(
    (Path(__file__).parent / "fixtures/egfr_l858r_nsclc.json").read_text())


@pytest.fixture(autouse=True)
def _reset():
    DR.reset_runtime_state()
    yield
    DR.reset_runtime_state()


def test_protein_shorthand_maps_hgvs_and_compact():
    assert DR.protein_shorthand("p.Leu858Arg") == "L858R"
    assert DR.protein_shorthand("NP_005228.4:p.Leu858Arg") == "L858R"
    assert DR.protein_shorthand("L858R") == "L858R"
    assert DR.protein_shorthand("p.L858R") == "L858R"
    assert DR.protein_shorthand("p.Val600Glu") == "V600E"
    assert DR.protein_shorthand("p.leu858arg") == "L858R"


def test_protein_shorthand_refuses_to_guess():
    assert DR.protein_shorthand("c.2573T>G") is None
    assert DR.protein_shorthand("GRCh38:7:55191822:T>G") is None
    assert DR.protein_shorthand("p.Gln1756fs") is None
    assert DR.protein_shorthand("p.Phe508del") is None
    assert DR.protein_shorthand("p.Leu858=") is None
    assert DR.protein_shorthand(None) is None
    assert DR.protein_shorthand("") is None


def test_disease_aliases_are_conservative():
    assert DR.normalize_indication("non-small cell lung cancer") == "NSCLC"
    assert DR.normalize_indication("lung adenocarcinoma") == "NSCLC"
    assert DR.normalize_indication("Melanoma") == "Melanoma"
    assert DR.normalize_indication("Hereditary breast and ovarian cancer") is None
    assert DR.normalize_indication("Cystic fibrosis") is None
    assert DR.normalize_indication("Li-Fraumeni syndrome spectrum") is None
    assert DR.normalize_indication("NSCLC") == "NSCLC"
    assert DR.normalize_indication("weird tumor", passthrough=True) == "weird tumor"
    assert DR.normalize_indication("weird tumor", passthrough=False) is None


def test_connector_disabled_by_default(monkeypatch):
    monkeypatch.delenv("GENOGUIDE_DRUG_API_ENABLED", raising=False)
    monkeypatch.delenv("GENOGUIDE_DRUG_API_URL", raising=False)
    st = DR.recommend("EGFR", "L858R", "NSCLC")
    assert st.availability.value == "SOURCE_NOT_CONFIGURED"
    assert st.recommendations == []


def test_mocked_egfr_ranking(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_DRUG_API_ENABLED", "true")
    monkeypatch.setenv("GENOGUIDE_DRUG_API_URL", "https://example.test")

    def fake_post(url, payload, timeout):
        assert payload == {"gene": "EGFR", "variant": "L858R", "disease": "NSCLC"}
        assert "example.test" in url
        return FIXTURE

    monkeypatch.setattr(DR, "_post_json", fake_post)
    st = DR.recommend("EGFR", "p.Leu858Arg", "lung adenocarcinoma")
    assert st.availability.value == "AVAILABLE"
    assert st.recommendations[0].drug == "Sunvozertinib"
    assert st.human_review_status == "required"
    assert "not a prescription" in st.disclaimer.lower()
    assert st.request_hash and st.response_hash
    # second call hits cache
    st2 = DR.recommend("EGFR", "L858R", "NSCLC")
    assert st2.cached is True


def test_timeout_does_not_raise(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_DRUG_API_ENABLED", "true")
    monkeypatch.setenv("GENOGUIDE_DRUG_API_URL", "https://example.test")

    def boom(*_a, **_k):
        raise httpx.TimeoutException("timeout")

    monkeypatch.setattr(DR, "_post_json", boom)
    st = DR.recommend("EGFR", "L858R", "NSCLC")
    assert st.availability.value == "SOURCE_UNAVAILABLE"
    assert st.recommendations == []


def test_germline_resolve_does_not_call_http(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_DRUG_API_ENABLED", "true")
    monkeypatch.setenv("GENOGUIDE_DRUG_API_URL", "https://example.test")
    called = {"n": 0}

    def fake_post(*_a, **_k):
        called["n"] += 1
        return FIXTURE

    monkeypatch.setattr(DR, "_post_json", fake_post)
    st = DR.resolve_somatic_therapy(
        gene="BRCA1", hgvs_p="p.Gln1756fs",
        variant_context=VariantContext.GERMLINE, include=False,
        oncology_indication=None, human_review_required=True)
    assert st.availability.value == "NOT_APPLICABLE"
    assert called["n"] == 0


def test_somatic_without_mappable_protein_skips(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_DRUG_API_ENABLED", "true")
    monkeypatch.setenv("GENOGUIDE_DRUG_API_URL", "https://example.test")
    called = {"n": 0}
    monkeypatch.setattr(DR, "_post_json", lambda *_a, **_k: called.__setitem__("n", 1) or FIXTURE)
    st = DR.resolve_somatic_therapy(
        gene="EGFR", hgvs_p=None,
        variant_context=VariantContext.SOMATIC, include=True,
        oncology_indication="NSCLC", human_review_required=True)
    assert st.availability.value == "SKIPPED"
    assert called["n"] == 0


def test_interpret_timeout_still_returns_acmg(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_DRUG_API_ENABLED", "true")
    monkeypatch.setenv("GENOGUIDE_DRUG_API_URL", "https://example.test")
    monkeypatch.setattr(DR, "_post_json", lambda *_a, **_k: (_ for _ in ()).throw(httpx.TimeoutException("t")))

    from app.services.interpret import InterpretationService
    v = CanonicalVariant.from_vcf_fields(
        GenomeBuild.GRCH38, "7", 55191822, "T", "G",
        gene="EGFR", hgvs_p="p.Leu858Arg",
        variant_context=VariantContext.SOMATIC)
    obj = InterpretationService().interpret(
        v, record_provenance=False, include_somatic_therapy=True,
        oncology_indication="NSCLC")
    assert obj.acmg_interpretation.classification  # still classified
    assert obj.reconciliation.final_classification == obj.acmg_interpretation.classification
    assert obj.somatic_therapy.availability.value == "SOURCE_UNAVAILABLE"


def test_drug_scores_do_not_enter_acmg_or_ml_features(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_DRUG_API_ENABLED", "true")
    monkeypatch.setenv("GENOGUIDE_DRUG_API_URL", "https://example.test")
    monkeypatch.setattr(DR, "_post_json", lambda *_a, **_k: FIXTURE)

    from app.interpretation.acmg_v2 import EvidenceInputs
    from app.services.interpret import InterpretationService, _feature_vector, _load_ml_model

    v = CanonicalVariant.from_vcf_fields(
        GenomeBuild.GRCH38, "7", 55191822, "T", "G",
        gene="EGFR", hgvs_p="p.Leu858Arg",
        variant_context=VariantContext.SOMATIC)
    obj = InterpretationService().interpret(
        v, record_provenance=False, include_somatic_therapy=True,
        oncology_indication="NSCLC")
    assert obj.somatic_therapy.availability.value == "AVAILABLE"
    assert obj.somatic_therapy.recommendations[0].drug == "Sunvozertinib"
    # ACMG evidence dataclass has no drug field
    assert not hasattr(EvidenceInputs(), "drug")
    assert not hasattr(EvidenceInputs(), "therapy_score")
    # feature schema has no drug keys
    bundle = _load_ml_model()
    if bundle is not None:
        feats = bundle["features"]
        assert not any("drug" in f or "therapy" in f for f in feats)
        X = _feature_vector(
            InterpretationService().evidence.annotate(v), feats)
        assert X.shape[1] == len(feats)
    # considerations must not say "prescribe" / "start"
    blob = " ".join(c.text.lower() for c in obj.clinical_considerations)
    assert "prescribe" not in blob
    assert "start this" not in blob
    assert obj.reconciliation.final_classification == obj.acmg_interpretation.classification


def test_therapy_edges_are_not_pgx():
    from app.knowledge_graph.graph import build_gene_graph
    g = build_gene_graph("EGFR", max_phenotypes=0, therapy_ranks={
        "variant": "L858R",
        "recommendations": [
            {"drug": "Osimertinib", "rank": 3, "score": 0.94,
             "response": "Sensitivity", "evidence_level": "A", "evidence_count": 25},
        ],
    })
    types = {e["type"] for e in g["edges"]}
    assert "THERAPY_RANKED_FOR" in types
    assert "metabolized_via" not in types
    assert all(e.get("source") != "CPIC" for e in g["edges"] if e["type"] == "THERAPY_RANKED_FOR")


def test_placeholder_url_is_rejected_without_dns(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_DRUG_API_ENABLED", "true")
    monkeypatch.setenv("GENOGUIDE_DRUG_API_URL", "https://your-host.example")
    called = {"n": 0}
    monkeypatch.setattr(DR, "_post_json", lambda *_a, **_k: called.__setitem__("n", called["n"] + 1))
    st = DR.recommend("EGFR", "L858R", "NSCLC")
    assert st.availability.value == "SOURCE_NOT_CONFIGURED"
    assert "placeholder" in (st.reason or "")
    assert called["n"] == 0


def test_explicit_base_url_overrides_placeholder_env(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_DRUG_API_ENABLED", "true")
    monkeypatch.setenv("GENOGUIDE_DRUG_API_URL", "https://your-host.example")
    monkeypatch.setattr(DR, "_post_json", lambda *_a, **_k: FIXTURE)
    st = DR.recommend("EGFR", "L858R", "NSCLC", base_url="https://example.test")
    assert st.availability.value == "AVAILABLE"
    assert st.recommendations[0].drug == "Sunvozertinib"


def test_dns_error_names_the_host(monkeypatch):
    monkeypatch.setenv("GENOGUIDE_DRUG_API_ENABLED", "true")
    monkeypatch.setenv("GENOGUIDE_DRUG_API_URL", "https://example.test")

    def boom(*_a, **_k):
        raise httpx.ConnectError("[Errno 8] nodename nor servname provided, or not known")

    monkeypatch.setattr(DR, "_post_json", boom)
    st = DR.recommend("EGFR", "L858R", "NSCLC")
    assert st.availability.value == "SOURCE_UNAVAILABLE"
    assert "example.test" in (st.reason or "")
    assert "DNS failed" in (st.reason or "")
