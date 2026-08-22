"""ACMG v2: missing evidence is never positive; combining rules; PVS1 caveats."""
from app.interpretation.acmg_v2 import (
    ComputationalEvidence,
    EvidenceInputs,
    GeneContext,
    PopulationEvidence,
    combine,
    evaluate,
)
from app.schemas.interpretation import CriterionStatus, CriterionStrength


def _by_id(result, cid):
    return next(c for c in result.criteria if c.id == cid)


def test_empty_inputs_nothing_met():
    r = evaluate(EvidenceInputs())
    assert r.classification == "VUS"
    assert r.met_criteria == []
    assert all(c.status != CriterionStatus.MET for c in r.criteria)
    assert "PVS1" in r.not_evaluable


def test_missing_population_does_not_assert_pm2_or_ba1():
    r = evaluate(EvidenceInputs(population=PopulationEvidence(source_available=False)))
    assert _by_id(r, "PM2").status == CriterionStatus.NOT_EVALUABLE
    assert _by_id(r, "BA1").status == CriterionStatus.NOT_EVALUABLE
    assert _by_id(r, "BS1").status == CriterionStatus.NOT_EVALUABLE


def test_common_af_is_ba1():
    r = evaluate(EvidenceInputs(
        population=PopulationEvidence(source_available=True, af=0.27)))
    assert _by_id(r, "BA1").status == CriterionStatus.MET
    assert r.classification == "BENIGN"


def test_pvs1_requires_lof_mechanism():
    ev = EvidenceInputs(
        consequence="frameshift_variant",
        gene_context=GeneContext(lof_is_disease_mechanism=None),
    )
    r = evaluate(ev)
    assert _by_id(r, "PVS1").status == CriterionStatus.NOT_EVALUABLE

    ev.gene_context.lof_is_disease_mechanism = True
    r = evaluate(ev)
    assert _by_id(r, "PVS1").status == CriterionStatus.MET


def test_pvs1_nmd_escape_blocks():
    r = evaluate(EvidenceInputs(
        consequence="stop_gained",
        gene_context=GeneContext(lof_is_disease_mechanism=True, last_exon_or_nmd_escape=True),
    ))
    assert _by_id(r, "PVS1").status == CriterionStatus.NOT_MET


def test_pp5_bp6_disabled():
    r = evaluate(EvidenceInputs())
    assert _by_id(r, "PP5").status == CriterionStatus.NOT_EVALUABLE
    assert _by_id(r, "BP6").status == CriterionStatus.NOT_EVALUABLE


def test_combine_pvs1_pm_is_likely_pathogenic():
    cls, _ = combine([
        ("PVS1", CriterionStrength.VERY_STRONG, "pathogenic"),
        ("PM2", CriterionStrength.MODERATE, "pathogenic"),
    ])
    assert cls == "LIKELY_PATHOGENIC"


def test_combine_conflict_is_vus():
    cls, rationale = combine([
        ("PVS1", CriterionStrength.VERY_STRONG, "pathogenic"),
        ("PS3", CriterionStrength.STRONG, "pathogenic"),
        ("BA1", CriterionStrength.STAND_ALONE, "benign"),
    ])
    assert cls == "VUS"
    assert "conflicting" in rationale


def test_pp3_needs_at_least_one_predictor():
    r = evaluate(EvidenceInputs(computational=ComputationalEvidence()))
    assert _by_id(r, "PP3").status == CriterionStatus.NOT_EVALUABLE
    r = evaluate(EvidenceInputs(computational=ComputationalEvidence(revel=0.9, n_sources=1)))
    assert _by_id(r, "PP3").status == CriterionStatus.MET
