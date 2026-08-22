"""
HPO semantic similarity + gene/disease ranking (section 16).

Term-pair measures: Resnik (IC of most-informative common ancestor),
Lin (2·IC(MICA) / (IC(a)+IC(b))), Jaccard on ancestor sets, and
IC-weighted Jaccard. Set-wise comparison uses symmetric best-match
average (BMA), the standard for phenotype profiles.

Phenotype matching NEVER feeds ACMG classification — it is a separate
context layer (enforced by the interpretation service).
"""
from __future__ import annotations

from typing import Any

from .ontology import Ontology, load_ontology


def mica_ic(onto: Ontology, a: str, b: str) -> float:
    common = onto.ancestors(a) & onto.ancestors(b)
    return max((onto.term_ic(t) for t in common), default=0.0)


def resnik(onto: Ontology, a: str, b: str) -> float:
    return mica_ic(onto, a, b)


def lin(onto: Ontology, a: str, b: str) -> float:
    denom = onto.term_ic(a) + onto.term_ic(b)
    return (2.0 * mica_ic(onto, a, b) / denom) if denom > 0 else 0.0


def jaccard(onto: Ontology, a: str, b: str) -> float:
    A, B = onto.ancestors(a), onto.ancestors(b)
    return len(A & B) / len(A | B) if A | B else 0.0


def ic_weighted_jaccard(onto: Ontology, a: str, b: str) -> float:
    A, B = onto.ancestors(a), onto.ancestors(b)
    inter = sum(onto.term_ic(t) for t in A & B)
    union = sum(onto.term_ic(t) for t in A | B)
    return inter / union if union > 0 else 0.0

_MEASURES = {"resnik": resnik, "lin": lin, "jaccard": jaccard,
             "ic_jaccard": ic_weighted_jaccard}


def profile_similarity(onto: Ontology, query: list[str], target: list[str],
                       measure: str = "lin") -> float:
    """Symmetric best-match average between two term sets."""
    fn = _MEASURES[measure]
    if not query or not target:
        return 0.0

    def bma(src, dst):
        return sum(max(fn(onto, q, t) for t in dst) for q in src) / len(src)

    return (bma(query, target) + bma(target, query)) / 2.0


def _resolve_terms(onto: Ontology, terms: list[str]) -> tuple[list[str], list[str]]:
    ok, unknown = [], []
    for t in terms:
        r = onto.resolve(t)
        (ok if r else unknown).append(r or t)
    return ok, unknown


def rank_genes(patient_terms: list[str], candidate_genes: list[str] | None = None,
               measure: str = "lin", top: int = 20) -> dict[str, Any]:
    onto = load_ontology()
    terms, unknown = _resolve_terms(onto, patient_terms)
    genes = candidate_genes or list(onto.gene_terms.keys())
    scored = []
    for g in genes:
        profile = onto.gene_terms.get(g)
        if profile:
            s = profile_similarity(onto, terms, list(profile), measure)
            scored.append({"gene": g, "phenotype_match_score": round(s, 4),
                           "n_profile_terms": len(profile)})
        elif candidate_genes:
            scored.append({"gene": g, "phenotype_match_score": None,
                           "note": "no HPO profile for gene"})
    scored.sort(key=lambda x: -(x["phenotype_match_score"] or -1))
    return {"measure": measure, "hpo_version": onto.version,
            "patient_terms_resolved": terms, "unknown_terms": unknown,
            "ranking": scored[:top]}


def rank_diseases(patient_terms: list[str], measure: str = "lin", top: int = 20) -> dict[str, Any]:
    onto = load_ontology()
    terms, unknown = _resolve_terms(onto, patient_terms)
    scored = []
    for d, profile in onto.disease_terms.items():
        s = profile_similarity(onto, terms, list(profile), measure)
        if s > 0:
            scored.append({"disease_id": d, "disease_name": onto.disease_names.get(d, d),
                           "phenotype_match_score": round(s, 4)})
    scored.sort(key=lambda x: -x["phenotype_match_score"])
    return {"measure": measure, "hpo_version": onto.version,
            "patient_terms_resolved": terms, "unknown_terms": unknown,
            "ranking": scored[:top]}


def match_patient_to_gene(patient_terms: list[str], gene: str,
                          measure: str = "lin") -> dict[str, Any]:
    onto = load_ontology()
    terms, unknown = _resolve_terms(onto, patient_terms)
    profile = onto.gene_terms.get(gene, set())
    score = profile_similarity(onto, terms, list(profile), measure) if profile else None
    return {
        "gene": gene,
        "phenotype_match_score": None if score is None else round(score, 4),
        "measure": measure,
        "hpo_version": onto.version,
        "patient_terms_resolved": terms,
        "unknown_terms": unknown,
        "gene_profile_size": len(profile),
        "gene_diseases": sorted(onto.gene_diseases.get(gene, set()))[:10],
        "availability": "AVAILABLE" if profile else "NOT_AVAILABLE",
        "note": "phenotype matching is contextual evidence; it never alters ACMG classification",
    }
