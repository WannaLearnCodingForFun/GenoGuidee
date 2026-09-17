"""Phenotype-first analysis + evolution. Never changes ACMG classification."""
from __future__ import annotations

import re
from functools import lru_cache
from typing import Any, Optional

from . import store

_HP = re.compile(r"^HP:\d{7}$")


@lru_cache(maxsize=1)
def _synonym_index() -> dict[str, str]:
    from ..phenotype.ontology import HPO_DIR
    obo = HPO_DIR / "hp.obo"
    idx: dict[str, str] = {}
    if not obo.exists():
        return idx
    current: Optional[str] = None
    with open(obo) as f:
        for line in f:
            line = line.strip()
            if line.startswith("id: HP:"):
                current = line[4:].strip()
            elif line.startswith("name: ") and current:
                idx[line[6:].strip().lower()] = current
            elif line.startswith("synonym: ") and current:
                # synonym: "Seizure" EXACT []
                q1 = line.find('"')
                q2 = line.find('"', q1 + 1) if q1 >= 0 else -1
                if q1 >= 0 and q2 > q1:
                    idx[line[q1 + 1:q2].lower()] = current
            elif line.startswith("alt_id: ") and current:
                idx[line[8:].strip().upper()] = current
    return idx


def normalize_one(raw: str, *, negated: bool = False) -> dict[str, Any]:
    text = (raw or "").strip()
    excluded = negated or text.upper().startswith("NOT ") or text.startswith("-")
    if text.upper().startswith("NOT "):
        text = text[4:].strip()
    if text.startswith("-"):
        text = text[1:].strip()
    hpo_id = None
    label = text
    source = "unresolved"
    try:
        from ..phenotype.ontology import load_ontology
        onto = load_ontology()
        if _HP.match(text.upper()):
            resolved = onto.resolve(text.upper())
            if resolved:
                hpo_id = resolved
                label = onto.terms.get(resolved, resolved)
                source = "hpo_id"
        if hpo_id is None:
            hit = _synonym_index().get(text.lower())
            if hit:
                resolved = onto.resolve(hit) or hit
                hpo_id = resolved
                label = onto.terms.get(resolved, resolved)
                source = "synonym"
    except FileNotFoundError:
        if _HP.match(text.upper()):
            hpo_id = text.upper()
            source = "hpo_id_offline"
    return {
        "input": raw,
        "hpo_id": hpo_id,
        "label": label,
        "negated": excluded,
        "resolved": hpo_id is not None,
        "match_type": source,
    }


def normalize(terms: list[Any]) -> dict[str, Any]:
    out = []
    for t in terms:
        if isinstance(t, dict):
            out.append(normalize_one(str(t.get("id") or t.get("term") or t.get("label") or ""),
                                     negated=bool(t.get("excluded") or t.get("negated"))))
            if t.get("onset"):
                out[-1]["onset"] = t["onset"]
            if t.get("severity"):
                out[-1]["severity"] = t["severity"]
            if t.get("temporality"):
                out[-1]["temporality"] = t["temporality"]
        else:
            out.append(normalize_one(str(t)))
    return {
        "terms": out,
        "positive_hpo": [t["hpo_id"] for t in out if t["hpo_id"] and not t["negated"]],
        "negated_hpo": [t["hpo_id"] for t in out if t["hpo_id"] and t["negated"]],
        "unresolved": [t["input"] for t in out if not t["resolved"]],
        "note": "Free-text is only resolved via HPO names/synonyms/IDs — never as ACMG evidence.",
    }


def match(terms: list[Any], gene: Optional[str] = None) -> dict[str, Any]:
    n = normalize(terms)
    if not n["positive_hpo"]:
        return {"availability": "NOT_AVAILABLE", "reason": "no resolved positive HPO terms", **n}
    from ..phenotype.similarity import match_patient_to_gene, rank_diseases, rank_genes
    result: dict[str, Any] = {"availability": "AVAILABLE", "normalized": n}
    if gene:
        result["gene"] = match_patient_to_gene(n["positive_hpo"], gene)
    result["genes"] = rank_genes(n["positive_hpo"], top=15)
    result["diseases"] = rank_diseases(n["positive_hpo"], top=15)
    return result


def rank_genes_ep(terms: list[Any], top: int = 20) -> dict[str, Any]:
    n = normalize(terms)
    from ..phenotype.similarity import rank_genes
    ranked = rank_genes(n["positive_hpo"], top=top) if n["positive_hpo"] else {"ranked": []}
    ranked["normalized"] = n
    ranked["acmg_altered"] = False
    return ranked


def rank_diseases_ep(terms: list[Any], top: int = 20) -> dict[str, Any]:
    n = normalize(terms)
    from ..phenotype.similarity import rank_diseases
    ranked = rank_diseases(n["positive_hpo"], top=top) if n["positive_hpo"] else {"ranked": []}
    ranked["normalized"] = n
    ranked["acmg_altered"] = False
    return ranked


def add_evolution(patient_id: int, phenotype: str, *, status: str = "observed",
                  onset: Optional[str] = None, observed_at: Optional[float] = None,
                  source: str = "evolution", confidence: Optional[str] = None,
                  negated: bool = False, temporality: Optional[str] = None,
                  severity: Optional[str] = None) -> dict[str, Any]:
    n = normalize_one(phenotype, negated=negated)
    ts = observed_at if observed_at is not None else store.now()
    store.execute(
        """INSERT INTO patient_phenotypes
           (patient_id, phenotype, hpo_id, source, created_at, status, onset, observed_at,
            confidence, negated, temporality, severity)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?)""",
        (patient_id, n["label"], n["hpo_id"], source, ts, status, onset, ts,
         confidence, 1 if n["negated"] else 0, temporality, severity),
    )
    return {"patient_id": patient_id, "term": n, "acmg_altered": False,
            "recalculated": True, "note": "Phenotype changes reprioritize genes/diseases; ACMG is unchanged."}


def profile(patient_id: int) -> dict[str, Any]:
    rows = store.execute(
        """SELECT phenotype, hpo_id, source, created_at, status, onset, observed_at,
                  confidence, negated, temporality, severity
           FROM patient_phenotypes WHERE patient_id=? ORDER BY COALESCE(observed_at, created_at) ASC""",
        (patient_id,), fetch="all",
    ) or []
    terms = [{
        "phenotype": r[0], "hpo_id": r[1], "source": r[2], "created_at": r[3],
        "status": r[4], "onset": r[5], "observed_at": r[6], "confidence": r[7],
        "negated": bool(r[8]), "temporality": r[9], "severity": r[10],
    } for r in rows]
    positive = [t["hpo_id"] for t in terms if t["hpo_id"] and not t["negated"]]
    ranking = None
    if positive:
        try:
            ranking = rank_genes_ep(positive, top=10)
        except FileNotFoundError:
            ranking = {"availability": "SOURCE_NOT_CONFIGURED"}
    return {"patient_id": patient_id, "timeline": terms, "gene_ranking": ranking, "acmg_altered": False}
