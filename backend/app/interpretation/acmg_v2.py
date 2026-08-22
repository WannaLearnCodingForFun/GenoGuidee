"""
ACMG/AMP evidence engine v2.

All 28 criteria of Richards et al. 2015 (PMID 25741868) are implemented as
independent evaluators over a structured `EvidenceInputs` object, with three
non-negotiable safety semantics:

  1. MISSING EVIDENCE NEVER BECOMES POSITIVE EVIDENCE. If a criterion's
     required inputs are absent, its status is NOT_EVALUABLE — never MET,
     and (critically for benign criteria) never treated as support.
  2. The engine is fully deterministic. No ML model and no LLM can set,
     modify, or override any criterion or the final classification.
  3. Every decision records criterion, strength, rule version, inputs used,
     reason, sources, and timestamp.

Gene-specific behavior comes from the ClinGen specification layer
(`clingen_specs.py`): specs may re-weight strengths, disable criteria, or
override thresholds. Base thresholds follow the 2015 guideline and widely
used community values; they are versioned and overridable, never claimed to
be VCEP-approved unless a real VCEP spec file is installed.

PP5/BP6 (reputable-source assertions) are implemented but DISABLED by
default, following ClinGen's recommendation to discontinue them
(Biesecker et al. 2018); a specification may explicitly re-enable them.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from pydantic import BaseModel, Field

from ..schemas.interpretation import (
    AcmgCriterionResult, AcmgInterpretation, CriterionStatus, CriterionStrength)

ENGINE_VERSION = "2.0.0"
RULE_VERSION = f"acmg-amp-2015/engine-{ENGINE_VERSION}"

S = CriterionStrength
ST = CriterionStatus


class PopulationEvidence(BaseModel):
    source_available: bool = False       # is ANY population source configured?
    af: Optional[float] = None           # overall AF (None + source_available=True → absent)
    af_popmax: Optional[float] = None
    allele_count: Optional[int] = None
    homozygote_count: Optional[int] = None


class ComputationalEvidence(BaseModel):
    revel: Optional[float] = None
    alphamissense: Optional[float] = None
    cadd_phred: Optional[float] = None
    spliceai_max_delta: Optional[float] = None
    phylop: Optional[float] = None
    n_sources: int = 0


class FunctionalEvidence(BaseModel):
    functional_studies_pathogenic: Optional[bool] = None  # None = no studies known
    functional_studies_benign: Optional[bool] = None
    study_sources: list[str] = Field(default_factory=list)


class SegregationEvidence(BaseModel):
    cosegregation_observed: Optional[bool] = None
    n_informative_meioses: Optional[int] = None
    nonsegregation_observed: Optional[bool] = None
    de_novo_confirmed: Optional[bool] = None     # maternity+paternity confirmed
    de_novo_assumed: Optional[bool] = None
    in_trans_pathogenic: Optional[bool] = None   # recessive gene, phase known
    in_cis_pathogenic: Optional[bool] = None
    alternate_cause_found: Optional[bool] = None
    healthy_adult_observation: Optional[bool] = None  # relevant zygosity for disease


class GeneContext(BaseModel):
    gene: Optional[str] = None
    lof_is_disease_mechanism: Optional[bool] = None   # None = unknown → PVS1 NOT_EVALUABLE
    missense_constrained: Optional[bool] = None       # e.g. gnomAD mis_z > 3
    missense_is_common_mechanism: Optional[bool] = None
    truncating_only_mechanism: Optional[bool] = None
    in_mutational_hotspot: Optional[bool] = None
    in_repeat_region: Optional[bool] = None
    known_pathogenic_same_aa: Optional[bool] = None       # PS1
    known_pathogenic_same_residue: Optional[bool] = None  # PM5
    case_control_enrichment: Optional[bool] = None        # PS4
    phenotype_highly_specific: Optional[bool] = None      # PP4
    last_exon_or_nmd_escape: Optional[bool] = None        # PVS1 caveat


class EvidenceInputs(BaseModel):
    consequence: Optional[str] = None
    variant_type: Optional[str] = None
    protein_length_changing: Optional[bool] = None
    is_synonymous: Optional[bool] = None
    population: PopulationEvidence = Field(default_factory=PopulationEvidence)
    computational: ComputationalEvidence = Field(default_factory=ComputationalEvidence)
    functional: FunctionalEvidence = Field(default_factory=FunctionalEvidence)
    segregation: SegregationEvidence = Field(default_factory=SegregationEvidence)
    gene_context: GeneContext = Field(default_factory=GeneContext)


# base thresholds — versioned, overridable by specifications
DEFAULT_THRESHOLDS: dict[str, float] = {
    "BA1_af": 0.05,
    "BS1_af": 0.01,
    "PM2_af_max": 1e-4,
    "PP3_revel": 0.644,          # Pejaver et al. 2022 calibration (supporting)
    "PP3_alphamissense": 0.564,  # AlphaMissense 'likely pathogenic' cut
    "PP3_cadd": 25.3,
    "PP3_spliceai": 0.2,
    "BP4_revel": 0.29,
    "BP4_alphamissense": 0.34,
    "BP4_spliceai": 0.1,
    "BP7_phylop_max": 2.0,
    "PP1_min_meioses": 3,
}

NULL_CONSEQUENCES = {"stop_gained", "frameshift_variant", "splice_donor_variant",
                     "splice_acceptor_variant", "splice_donor_or_acceptor", "start_lost"}


@dataclass
class Criterion:
    id: str
    name: str
    category: str            # pathogenic | benign
    default_strength: CriterionStrength
    evaluate: Callable[[EvidenceInputs, dict[str, float]], tuple[CriterionStatus, str, dict, list[str]]]
    enabled_by_default: bool = True


def _need(*pairs: tuple[str, Any]) -> Optional[str]:
    missing = [name for name, value in pairs if value is None]
    return ", ".join(missing) if missing else None


# ---------------------------------------------------------------------------
# Pathogenic criteria
# ---------------------------------------------------------------------------

def _pvs1(ev: EvidenceInputs, th):
    gc = ev.gene_context
    if ev.consequence is None or gc.lof_is_disease_mechanism is None:
        return ST.NOT_EVALUABLE, "requires consequence and knowledge of whether LOF is the disease mechanism", \
            {"consequence": ev.consequence, "lof_mechanism": gc.lof_is_disease_mechanism}, []
    if ev.consequence not in NULL_CONSEQUENCES:
        return ST.NOT_MET, f"{ev.consequence} is not a null variant", {"consequence": ev.consequence}, []
    if not gc.lof_is_disease_mechanism:
        return ST.NOT_MET, "LOF is not an established disease mechanism for this gene", \
            {"lof_mechanism": False}, []
    if gc.last_exon_or_nmd_escape:
        return ST.NOT_MET, "null variant in last exon / predicted NMD escape — PVS1 caveat applies", \
            {"nmd_escape": True}, []
    return ST.MET, "null variant in a gene where LOF is a known disease mechanism", \
        {"consequence": ev.consequence}, ["Richards 2015 Table 3; PVS1 caveats simplified — Abou Tayoun 2018 decision tree is an extension point"]


def _ps1(ev, th):
    v = ev.gene_context.known_pathogenic_same_aa
    if v is None:
        return ST.NOT_EVALUABLE, "no curated data on identical amino-acid changes", {}, []
    return (ST.MET if v else ST.NOT_MET,
            "same amino-acid change as an established pathogenic variant" if v
            else "no established pathogenic variant with this amino-acid change",
            {"known_pathogenic_same_aa": v}, [])


def _ps2(ev, th):
    v = ev.segregation.de_novo_confirmed
    if v is None:
        return ST.NOT_EVALUABLE, "parental testing data not provided", {}, []
    return (ST.MET if v else ST.NOT_MET,
            "confirmed de novo (maternity and paternity verified)" if v else "not confirmed de novo",
            {"de_novo_confirmed": v}, [])


def _ps3(ev, th):
    f = ev.functional.functional_studies_pathogenic
    if f is None:
        return ST.NOT_EVALUABLE, "no well-established functional studies available", {}, []
    return (ST.MET if f else ST.NOT_MET,
            "well-established functional studies show a deleterious effect" if f
            else "functional studies do not show a deleterious effect",
            {"functional_pathogenic": f}, ev.functional.study_sources)


def _ps4(ev, th):
    v = ev.gene_context.case_control_enrichment
    if v is None:
        return ST.NOT_EVALUABLE, "no case-control / prevalence data provided", {}, []
    return (ST.MET if v else ST.NOT_MET,
            "prevalence in affected individuals significantly increased over controls" if v
            else "no significant case enrichment", {"case_control_enrichment": v}, [])


def _pm1(ev, th):
    v = ev.gene_context.in_mutational_hotspot
    if v is None:
        return ST.NOT_EVALUABLE, "hotspot/domain annotation not available", {}, []
    return (ST.MET if v else ST.NOT_MET,
            "located in a mutational hotspot or well-established functional domain" if v
            else "not in a known hotspot or critical domain", {"in_hotspot": v}, [])


def _pm2(ev, th):
    pop = ev.population
    if not pop.source_available:
        return ST.NOT_EVALUABLE, "no population frequency source configured — absence cannot be asserted", {}, []
    af = pop.af_popmax if pop.af_popmax is not None else pop.af
    if af is None:
        return ST.MET, "absent from population databases", {"af": None}, ["population source: configured"]
    if af < th["PM2_af_max"]:
        return ST.MET, f"extremely rare (AF={af:.2e} < {th['PM2_af_max']:.0e})", {"af": af}, []
    return ST.NOT_MET, f"allele frequency {af:.2e} above PM2 threshold", {"af": af}, []


def _pm3(ev, th):
    v = ev.segregation.in_trans_pathogenic
    if v is None:
        return ST.NOT_EVALUABLE, "phase/trans data not provided", {}, []
    return (ST.MET if v else ST.NOT_MET,
            "detected in trans with a pathogenic variant (recessive disorder)" if v
            else "no in-trans pathogenic variant observed", {"in_trans_pathogenic": v}, [])


def _pm4(ev, th):
    if ev.protein_length_changing is None:
        return ST.NOT_EVALUABLE, "protein length consequence unknown", {}, []
    if not ev.protein_length_changing:
        return ST.NOT_MET, "variant does not change protein length", {}, []
    if ev.gene_context.in_repeat_region:
        return ST.NOT_MET, "length change lies in a repeat region (PM4 exclusion; consider BP3)", \
            {"in_repeat": True}, []
    return ST.MET, "protein length change in a non-repeat region", {}, []


def _pm5(ev, th):
    v = ev.gene_context.known_pathogenic_same_residue
    if v is None:
        return ST.NOT_EVALUABLE, "no curated data on other missense changes at this residue", {}, []
    return (ST.MET if v else ST.NOT_MET,
            "novel missense at a residue where a different missense change is established pathogenic" if v
            else "no established pathogenic missense at this residue", {"same_residue": v}, [])


def _pm6(ev, th):
    v = ev.segregation.de_novo_assumed
    if v is None:
        return ST.NOT_EVALUABLE, "assumed de novo status not provided", {}, []
    return (ST.MET if v else ST.NOT_MET,
            "assumed de novo (parentage not confirmed)" if v else "not assumed de novo",
            {"de_novo_assumed": v}, [])


def _pp1(ev, th):
    seg = ev.segregation
    if seg.cosegregation_observed is None:
        return ST.NOT_EVALUABLE, "segregation data not provided", {}, []
    if not seg.cosegregation_observed:
        return ST.NOT_MET, "cosegregation not observed", {}, []
    n = seg.n_informative_meioses or 0
    if n < th["PP1_min_meioses"]:
        return ST.NOT_MET, f"cosegregation reported but only {n} informative meioses (<{int(th['PP1_min_meioses'])})", \
            {"meioses": n}, []
    return ST.MET, f"cosegregation with disease across {n} informative meioses", {"meioses": n}, []


def _pp2(ev, th):
    gc = ev.gene_context
    if ev.consequence != "missense_variant":
        return ST.NOT_MET, "not a missense variant", {"consequence": ev.consequence}, []
    if gc.missense_constrained is None or gc.missense_is_common_mechanism is None:
        return ST.NOT_EVALUABLE, "gene missense constraint / mechanism unknown", {}, []
    ok = gc.missense_constrained and gc.missense_is_common_mechanism
    return (ST.MET if ok else ST.NOT_MET,
            "missense in a missense-constrained gene where missense is a common mechanism"
            if ok else "gene is not missense-constrained or missense is not the mechanism",
            {"missense_constrained": gc.missense_constrained,
             "missense_mechanism": gc.missense_is_common_mechanism},
            ["gnomAD v4.1 missense z-score used as constraint proxy"])


def _pp3(ev, th):
    c = ev.computational
    votes, inputs = [], {}
    if c.revel is not None:
        votes.append(c.revel >= th["PP3_revel"]); inputs["revel"] = c.revel
    if c.alphamissense is not None:
        votes.append(c.alphamissense >= th["PP3_alphamissense"]); inputs["alphamissense"] = c.alphamissense
    if c.cadd_phred is not None:
        votes.append(c.cadd_phred >= th["PP3_cadd"]); inputs["cadd_phred"] = c.cadd_phred
    if c.spliceai_max_delta is not None:
        votes.append(c.spliceai_max_delta >= th["PP3_spliceai"]); inputs["spliceai"] = c.spliceai_max_delta
    if not votes:
        return ST.NOT_EVALUABLE, "no in-silico predictors available for this variant", {}, []
    if all(votes) and len(votes) >= 1:
        return ST.MET, f"{len(votes)} computational line(s) support a deleterious effect", inputs, \
            ["thresholds: Pejaver 2022 / AlphaMissense 2023 calibrations (supporting level)"]
    return ST.NOT_MET, "computational evidence not consistently deleterious", inputs, []


def _pp4(ev, th):
    v = ev.gene_context.phenotype_highly_specific
    if v is None:
        return ST.NOT_EVALUABLE, "patient phenotype specificity not assessed", {}, []
    return (ST.MET if v else ST.NOT_MET,
            "patient phenotype highly specific for this gene's disease" if v
            else "phenotype not specific for this gene", {"phenotype_specific": v}, [])


def _pp5(ev, th):
    return ST.NOT_EVALUABLE, "PP5 disabled by default per ClinGen recommendation (Biesecker 2018); " \
                             "a specification may re-enable it explicitly", {}, []


# ---------------------------------------------------------------------------
# Benign criteria
# ---------------------------------------------------------------------------

def _ba1(ev, th):
    pop = ev.population
    if not pop.source_available:
        return ST.NOT_EVALUABLE, "no population frequency source configured", {}, []
    af = pop.af_popmax if pop.af_popmax is not None else pop.af
    if af is None:
        return ST.NOT_MET, "variant absent from population data — BA1 cannot apply", {"af": None}, []
    if af > th["BA1_af"]:
        return ST.MET, f"allele frequency {af:.3f} > {th['BA1_af']} (stand-alone benign)", {"af": af}, []
    return ST.NOT_MET, f"allele frequency {af:.2e} below BA1 threshold", {"af": af}, []


def _bs1(ev, th):
    pop = ev.population
    if not pop.source_available:
        return ST.NOT_EVALUABLE, "no population frequency source configured", {}, []
    af = pop.af_popmax if pop.af_popmax is not None else pop.af
    if af is None:
        return ST.NOT_MET, "variant absent from population data", {"af": None}, []
    if af > th["BS1_af"]:
        return ST.MET, f"allele frequency {af:.4f} greater than expected for the disorder " \
                       f"(default threshold {th['BS1_af']}; refine per gene specification)", {"af": af}, []
    return ST.NOT_MET, f"allele frequency {af:.2e} not above BS1 threshold", {"af": af}, []


def _bs2(ev, th):
    v = ev.segregation.healthy_adult_observation
    if v is None:
        return ST.NOT_EVALUABLE, "no healthy-individual observation data", {}, []
    return (ST.MET if v else ST.NOT_MET,
            "observed in healthy adult(s) with full penetrance expected at the relevant zygosity" if v
            else "no qualifying healthy-adult observations", {"healthy_adult": v}, [])


def _bs3(ev, th):
    f = ev.functional.functional_studies_benign
    if f is None:
        return ST.NOT_EVALUABLE, "no well-established functional studies available", {}, []
    return (ST.MET if f else ST.NOT_MET,
            "well-established functional studies show no damaging effect" if f
            else "functional studies do not support benign impact",
            {"functional_benign": f}, ev.functional.study_sources)


def _bs4(ev, th):
    v = ev.segregation.nonsegregation_observed
    if v is None:
        return ST.NOT_EVALUABLE, "segregation data not provided", {}, []
    return (ST.MET if v else ST.NOT_MET,
            "lack of segregation in affected family members" if v else "no non-segregation observed",
            {"nonsegregation": v}, [])


def _bp1(ev, th):
    gc = ev.gene_context
    if ev.consequence != "missense_variant":
        return ST.NOT_MET, "not a missense variant", {}, []
    if gc.truncating_only_mechanism is None:
        return ST.NOT_EVALUABLE, "gene mechanism (truncating-only?) unknown", {}, []
    return (ST.MET if gc.truncating_only_mechanism else ST.NOT_MET,
            "missense variant in a gene where only truncating variants cause disease"
            if gc.truncating_only_mechanism else "gene mechanism not truncating-only",
            {"truncating_only": gc.truncating_only_mechanism}, [])


def _bp2(ev, th):
    v = ev.segregation.in_cis_pathogenic
    if v is None:
        return ST.NOT_EVALUABLE, "phase data not provided", {}, []
    return (ST.MET if v else ST.NOT_MET,
            "observed in cis with a pathogenic variant (or in trans in a dominant gene)" if v
            else "no qualifying cis/trans observation", {"in_cis_pathogenic": v}, [])


def _bp3(ev, th):
    if ev.protein_length_changing is None or ev.gene_context.in_repeat_region is None:
        return ST.NOT_EVALUABLE, "length-change/repeat-region annotation unavailable", {}, []
    ok = ev.protein_length_changing and ev.gene_context.in_repeat_region
    return (ST.MET if ok else ST.NOT_MET,
            "in-frame indel in a repetitive region without known function" if ok
            else "not an in-frame indel in a repeat region", {}, [])


def _bp4(ev, th):
    c = ev.computational
    votes, inputs = [], {}
    if c.revel is not None:
        votes.append(c.revel <= th["BP4_revel"]); inputs["revel"] = c.revel
    if c.alphamissense is not None:
        votes.append(c.alphamissense <= th["BP4_alphamissense"]); inputs["alphamissense"] = c.alphamissense
    if c.spliceai_max_delta is not None:
        votes.append(c.spliceai_max_delta <= th["BP4_spliceai"]); inputs["spliceai"] = c.spliceai_max_delta
    if not votes:
        return ST.NOT_EVALUABLE, "no in-silico predictors available for this variant", {}, []
    if all(votes):
        return ST.MET, f"{len(votes)} computational line(s) suggest no impact", inputs, []
    return ST.NOT_MET, "computational evidence not consistently benign", inputs, []


def _bp5(ev, th):
    v = ev.segregation.alternate_cause_found
    if v is None:
        return ST.NOT_EVALUABLE, "no data on alternate molecular cause", {}, []
    return (ST.MET if v else ST.NOT_MET,
            "found in a case with an alternate molecular basis for disease" if v
            else "no alternate molecular cause identified", {"alternate_cause": v}, [])


def _bp6(ev, th):
    return ST.NOT_EVALUABLE, "BP6 disabled by default per ClinGen recommendation (Biesecker 2018); " \
                             "a specification may re-enable it explicitly", {}, []


def _bp7(ev, th):
    if ev.is_synonymous is None:
        return ST.NOT_EVALUABLE, "synonymous status unknown", {}, []
    if not ev.is_synonymous:
        return ST.NOT_MET, "not a synonymous variant", {}, []
    c = ev.computational
    if c.spliceai_max_delta is None and c.phylop is None:
        return ST.NOT_EVALUABLE, "synonymous, but no splice prediction or conservation data available", {}, []
    splice_ok = c.spliceai_max_delta is None or c.spliceai_max_delta <= th["BP4_spliceai"]
    cons_ok = c.phylop is None or c.phylop < th["BP7_phylop_max"]
    if splice_ok and cons_ok:
        return ST.MET, "synonymous variant with no predicted splice impact and low conservation", \
            {"spliceai": c.spliceai_max_delta, "phylop": c.phylop}, []
    return ST.NOT_MET, "synonymous but predicted splice impact or high conservation", \
        {"spliceai": c.spliceai_max_delta, "phylop": c.phylop}, []


CRITERIA_REGISTRY: dict[str, Criterion] = {c.id: c for c in [
    Criterion("PVS1", "Null variant, LOF mechanism", "pathogenic", S.VERY_STRONG, _pvs1),
    Criterion("PS1", "Same amino-acid change as pathogenic", "pathogenic", S.STRONG, _ps1),
    Criterion("PS2", "Confirmed de novo", "pathogenic", S.STRONG, _ps2),
    Criterion("PS3", "Functional studies deleterious", "pathogenic", S.STRONG, _ps3),
    Criterion("PS4", "Case-control enrichment", "pathogenic", S.STRONG, _ps4),
    Criterion("PM1", "Mutational hotspot/critical domain", "pathogenic", S.MODERATE, _pm1),
    Criterion("PM2", "Absent/extremely rare in population", "pathogenic", S.MODERATE, _pm2),
    Criterion("PM3", "In trans with pathogenic (recessive)", "pathogenic", S.MODERATE, _pm3),
    Criterion("PM4", "Protein length change", "pathogenic", S.MODERATE, _pm4),
    Criterion("PM5", "Different pathogenic missense at residue", "pathogenic", S.MODERATE, _pm5),
    Criterion("PM6", "Assumed de novo", "pathogenic", S.MODERATE, _pm6),
    Criterion("PP1", "Cosegregation with disease", "pathogenic", S.SUPPORTING, _pp1),
    Criterion("PP2", "Missense in constrained gene", "pathogenic", S.SUPPORTING, _pp2),
    Criterion("PP3", "Computational evidence deleterious", "pathogenic", S.SUPPORTING, _pp3),
    Criterion("PP4", "Phenotype specific for gene", "pathogenic", S.SUPPORTING, _pp4),
    Criterion("PP5", "Reputable source (legacy)", "pathogenic", S.SUPPORTING, _pp5, enabled_by_default=False),
    Criterion("BA1", "AF > 5% stand-alone", "benign", S.STAND_ALONE, _ba1),
    Criterion("BS1", "AF greater than expected", "benign", S.STRONG, _bs1),
    Criterion("BS2", "Observed in healthy adults", "benign", S.STRONG, _bs2),
    Criterion("BS3", "Functional studies benign", "benign", S.STRONG, _bs3),
    Criterion("BS4", "Lack of segregation", "benign", S.STRONG, _bs4),
    Criterion("BP1", "Missense where truncating is mechanism", "benign", S.SUPPORTING, _bp1),
    Criterion("BP2", "Cis/trans phase inconsistent", "benign", S.SUPPORTING, _bp2),
    Criterion("BP3", "In-frame indel in repeat region", "benign", S.SUPPORTING, _bp3),
    Criterion("BP4", "Computational evidence benign", "benign", S.SUPPORTING, _bp4),
    Criterion("BP5", "Alternate molecular cause", "benign", S.SUPPORTING, _bp5),
    Criterion("BP6", "Reputable source benign (legacy)", "benign", S.SUPPORTING, _bp6, enabled_by_default=False),
    Criterion("BP7", "Synonymous, no splice impact", "benign", S.SUPPORTING, _bp7),
]}


# ---------------------------------------------------------------------------
# Combining rules (Richards 2015, Table 5 — implemented strictly)
# ---------------------------------------------------------------------------

def combine(met: list[tuple[str, CriterionStrength, str]]) -> tuple[str, str]:
    """met: list of (criterion_id, applied_strength, category). Returns
    (classification, rationale)."""
    pvs = sum(1 for _, s, c in met if c == "pathogenic" and s == S.VERY_STRONG)
    ps = sum(1 for _, s, c in met if c == "pathogenic" and s == S.STRONG)
    pm = sum(1 for _, s, c in met if c == "pathogenic" and s == S.MODERATE)
    pp = sum(1 for _, s, c in met if c == "pathogenic" and s == S.SUPPORTING)
    ba = sum(1 for _, s, c in met if c == "benign" and s == S.STAND_ALONE)
    bs = sum(1 for _, s, c in met if c == "benign" and s == S.STRONG)
    bp = sum(1 for _, s, c in met if c == "benign" and s == S.SUPPORTING)

    pathogenic = (
        (pvs >= 1 and (ps >= 1 or pm >= 2 or (pm >= 1 and pp >= 1) or pp >= 2))
        or ps >= 2
        or (ps == 1 and (pm >= 3 or (pm >= 2 and pp >= 2) or (pm >= 1 and pp >= 4)))
    )
    likely_pathogenic = (
        (pvs >= 1 and pm >= 1)
        or (ps == 1 and 1 <= pm <= 2)
        or (ps == 1 and pp >= 2)
        or pm >= 3
        or (pm == 2 and pp >= 2)
        or (pm == 1 and pp >= 4)
    )
    benign = ba >= 1 or bs >= 2
    likely_benign = (bs >= 1 and bp >= 1) or bp >= 2

    path_side = pathogenic or likely_pathogenic
    benign_side = benign or likely_benign
    counts = f"PVS={pvs} PS={ps} PM={pm} PP={pp} | BA={ba} BS={bs} BP={bp}"

    if path_side and benign_side:
        return "VUS", f"conflicting evidence ({counts}) — defaults to VUS per guideline"
    if pathogenic:
        return "PATHOGENIC", counts
    if likely_pathogenic:
        return "LIKELY_PATHOGENIC", counts
    if benign:
        return "BENIGN", counts
    if likely_benign:
        return "LIKELY_BENIGN", counts
    return "VUS", f"criteria insufficient for any assertion ({counts})"


# ---------------------------------------------------------------------------
# Engine
# ---------------------------------------------------------------------------

def evaluate(
    evidence: EvidenceInputs,
    specification: Optional["GeneSpecification"] = None,
) -> AcmgInterpretation:
    from .clingen_specs import GeneSpecification  # local import to avoid cycle

    thresholds = dict(DEFAULT_THRESHOLDS)
    spec_name = None
    if specification is not None:
        thresholds.update(specification.threshold_overrides)
        spec_name = specification.name

    now = datetime.now(timezone.utc).isoformat()
    results: list[AcmgCriterionResult] = []
    met: list[tuple[str, CriterionStrength, str]] = []

    for crit in CRITERIA_REGISTRY.values():
        enabled = crit.enabled_by_default
        if specification is not None:
            enabled = specification.criterion_enabled(crit.id, enabled)
        if not enabled:
            status, reason, inputs, sources = ST.NOT_EVALUABLE, \
                f"{crit.id} disabled ({'by specification' if specification else 'by default policy'})", {}, []
        else:
            status, reason, inputs, sources = crit.evaluate(evidence, thresholds)

        applied = crit.default_strength
        if specification is not None and status == ST.MET:
            applied = specification.applied_strength(crit.id, crit.default_strength)

        results.append(AcmgCriterionResult(
            id=crit.id, name=crit.name, category=crit.category,
            default_strength=crit.default_strength,
            applied_strength=applied if status == ST.MET else None,
            status=status, reason=reason, inputs=inputs, sources=sources,
            rule_version=RULE_VERSION, gene_specification=spec_name, timestamp=now,
        ))
        if status == ST.MET:
            met.append((crit.id, applied, crit.category))

    classification, rationale = combine(met)
    not_evaluable = [r.id for r in results if r.status == ST.NOT_EVALUABLE]
    n_met = len(met)

    if classification == "VUS":
        confidence = "low" if n_met == 0 else "moderate"
    else:
        confidence = "high" if n_met >= 3 else "moderate"
    human_review_required = (
        classification == "VUS"
        or "conflicting" in rationale
        or n_met <= 1
        or len(not_evaluable) >= 20
    )

    return AcmgInterpretation(
        classification=classification,
        criteria=results,
        met_criteria=[m[0] for m in met],
        not_evaluable=not_evaluable,
        rule_version=RULE_VERSION,
        gene_specification=spec_name,
        combining_rationale=rationale,
        confidence=confidence,
        human_review_required=human_review_required,
    )
