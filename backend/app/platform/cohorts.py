"""De-identified cohort mode. Researchers never receive direct identity."""
from __future__ import annotations

import hashlib
import uuid
from collections import Counter, defaultdict
from typing import Any, Optional

from . import store


def _alias(patient_id: int, cohort_id: str) -> str:
    return "C-" + hashlib.sha256(f"{cohort_id}:{patient_id}".encode()).hexdigest()[:10].upper()


def create(name: str, created_by: Optional[int] = None) -> dict[str, Any]:
    cid = f"COH-{uuid.uuid4().hex[:8].upper()}"
    store.execute(
        "INSERT INTO cohorts (cohort_id, name, created_by, created_at) VALUES (?,?,?,?)",
        (cid, name, created_by, store.now()),
    )
    return {"cohort_id": cid, "name": name}


def add_case(cohort_id: str, case_id: str, patient_id: Optional[int]) -> dict[str, Any]:
    store.execute(
        "INSERT OR IGNORE INTO cohort_cases (cohort_id, case_id, patient_id) VALUES (?,?,?)",
        (cohort_id, case_id, patient_id),
    )
    return {"cohort_id": cohort_id, "case_id": case_id, "included": True}


def deidentify_bundle(cohort_id: str) -> dict[str, Any]:
    rows = store.execute(
        "SELECT case_id, patient_id FROM cohort_cases WHERE cohort_id=?",
        (cohort_id,), fetch="all",
    ) or []
    cases = []
    gene_counts: Counter[str] = Counter()
    variant_counts: Counter[str] = Counter()
    pheno_counts: Counter[str] = Counter()
    for case_id, pid in rows:
        alias = _alias(int(pid or 0), cohort_id)
        genes, variants, phenos = [], [], []
        if pid:
            vrows = store.execute(
                "SELECT gene, normalized_variant FROM variants WHERE patient_id=?",
                (pid,), fetch="all",
            ) or []
            for g, nv in vrows:
                if g:
                    genes.append(g); gene_counts[g] += 1
                if nv:
                    variants.append(nv); variant_counts[nv] += 1
            prows = store.execute(
                "SELECT hpo_id FROM patient_phenotypes WHERE patient_id=? AND COALESCE(negated,0)=0",
                (pid,), fetch="all",
            ) or []
            for (h,) in prows:
                if h:
                    phenos.append(h); pheno_counts[h] += 1
        cases.append({
            "case_alias": alias,
            "case_id": case_id,
            "genes": sorted(set(genes)),
            "variant_count": len(variants),
            "phenotypes": phenos,
            # identity fields deliberately omitted
        })
    return {
        "cohort_id": cohort_id,
        "n_cases": len(cases),
        "cases": cases,
        "gene_aggregation": gene_counts.most_common(50),
        "variant_aggregation": variant_counts.most_common(50),
        "phenotype_aggregation": pheno_counts.most_common(50),
        "identity_fields_present": False,
    }


def query_shared_variants(cohort_id: str) -> list[dict[str, Any]]:
    bundle = deidentify_bundle(cohort_id)
    shared = [{"variant": v, "n_cases": n} for v, n in bundle["variant_aggregation"] if n >= 2]
    return shared


def query_enriched_genes(cohort_id: str) -> list[dict[str, Any]]:
    bundle = deidentify_bundle(cohort_id)
    return [{"gene": g, "n_cases": n} for g, n in bundle["gene_aggregation"]]
