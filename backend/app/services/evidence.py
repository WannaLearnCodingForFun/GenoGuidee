"""
Evidence assembly for a canonical variant.

Sources (all real, all local, availability always explicit):
  * ClinVar processed parquet — variant identity, curated PS1/PM5 lookups
    (same amino-acid change / same residue, EXCLUDING the query variant
    itself), and data-driven gene mechanism statistics.
  * gnomAD v4.1 constraint — gene-level LOEUF/pLI/mis-z (PP2 proxy).
  * AlphaMissense parquet store — missense functional score (when converted).
  * gnomAD per-variant AF — SOURCE_NOT_CONFIGURED (TB-scale; see manifest):
    population criteria (PM2/BA1/BS1) are NOT_EVALUABLE, never guessed.

Honesty notes recorded in outputs:
  * gene mechanism flags are DATA-DRIVEN PROXIES from ClinVar counts, not
    curated VCEP assertions; thresholds are documented in `mechanism_policy`.
"""
from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

import duckdb

from ..interpretation.acmg_v2 import (
    ComputationalEvidence, EvidenceInputs, FunctionalEvidence, GeneContext,
    PopulationEvidence)
from ..schemas.variant import CanonicalVariant

REPO = Path(__file__).resolve().parents[3]
CLINVAR = REPO / "research/data/processed/clinvar_grch38.parquet"
GENES = REPO / "research/data/processed/gene_features.parquet"
AM_STORE = REPO / "research/data/interim/alphamissense_hg38.parquet"
POP_AF = REPO / "research/data/processed/population_af.parquet"
POPULATION_SOURCE = ("ExAC/1000G/ESP allele frequencies via ClinVar VCF "
                     "(legacy cohorts, not gnomAD v4)")

ANNOTATION_VERSION = "clinvar-2026-08+gnomad-constraint-4.1+hpo-2026-06-23"

_P_CHANGE = re.compile(r"\((p\.([A-Z][a-z]{2})(\d+)([A-Za-z=*]+))\)")

MECHANISM_POLICY = {
    "lof_is_disease_mechanism": "≥5 distinct pathogenic/likely-pathogenic LOF variants (tier ≥2) in ClinVar",
    "missense_is_common_mechanism": "≥25% of pathogenic-spectrum variants are missense (≥10 total)",
    "truncating_only_mechanism": "≥10 pathogenic-spectrum variants and ≤2% missense",
    "note": "data-driven proxies from ClinVar aggregate counts — not curated VCEP assertions",
}

LOF_CONSEQUENCES = {"frameshift_variant", "stop_gained", "splice_donor_or_acceptor", "start_lost"}


class EvidenceService:
    def __init__(self) -> None:
        self._con: Optional[duckdb.DuckDBPyConnection] = None

    def _db(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            self._con = duckdb.connect()
        return self._con

    # -- source availability --------------------------------------------------
    def source_summary(self) -> dict[str, str]:
        return {
            "clinvar": "AVAILABLE" if CLINVAR.exists() else "SOURCE_NOT_CONFIGURED",
            "gene_constraint": "AVAILABLE" if GENES.exists() else "SOURCE_NOT_CONFIGURED",
            "alphamissense": "AVAILABLE" if AM_STORE.exists() else "SOURCE_NOT_CONFIGURED",
            "population_af": ("AVAILABLE (legacy ExAC/1000G/ESP)" if POP_AF.exists()
                              else "SOURCE_NOT_CONFIGURED"),
            "gnomad_population_af": "SOURCE_NOT_CONFIGURED",
            "revel": "SOURCE_NOT_CONFIGURED",
            "spliceai": "SOURCE_NOT_CONFIGURED",
            "cadd": "SOURCE_NOT_CONFIGURED",
            "annotation_version": ANNOTATION_VERSION,
        }

    # -- lookups ---------------------------------------------------------------
    @lru_cache(maxsize=4096)
    def _gene_features(self, gene: str) -> Optional[dict[str, Any]]:
        if not GENES.exists() or not gene:
            return None
        row = self._db().execute(
            f"SELECT loeuf, pli, mis_z, clingen_validity, clingen_moi, clingen_n_diseases "
            f"FROM '{GENES}' WHERE gene = ?", [gene]).fetchone()
        if row is None:
            return None
        return {"loeuf": row[0], "pli": row[1], "mis_z": row[2],
                "clingen_validity": row[3], "clingen_moi": row[4],
                "clingen_n_diseases": row[5], "source": "gnomAD v4.1 constraint + ClinGen"}

    def clinvar_variant(self, v: CanonicalVariant) -> Optional[dict[str, Any]]:
        if not CLINVAR.exists():
            return None
        row = self._db().execute(
            f"SELECT gene, name, clinsig_raw, review_status, confidence_tier, "
            f"consequence_derived, variation_id, phenotype_list FROM '{CLINVAR}' "
            f"WHERE chrom=? AND pos=? AND ref=? AND alt=? LIMIT 1",
            [v.chromosome, v.position, v.reference, v.alternate]).fetchone()
        if row is None:
            return None
        return {"gene": row[0], "name": row[1], "clinical_significance": row[2],
                "review_status": row[3], "confidence_tier": row[4],
                "consequence_derived": row[5], "variation_id": row[6],
                "conditions": (row[7] or "")[:300], "source": "ClinVar 2026-08"}

    @lru_cache(maxsize=1024)
    def _gene_mechanism(self, gene: str) -> Optional[dict[str, Any]]:
        """Data-driven gene mechanism statistics from ClinVar (tier ≥2)."""
        if not CLINVAR.exists() or not gene:
            return None
        rows = self._db().execute(
            f"SELECT consequence_derived, COUNT(*) FROM '{CLINVAR}' "
            f"WHERE gene=? AND confidence_tier>=2 "
            f"AND label IN ('pathogenic','likely_pathogenic') "
            f"GROUP BY consequence_derived", [gene]).fetchall()
        counts = {r[0]: r[1] for r in rows}
        n_lof = sum(counts.get(c, 0) for c in LOF_CONSEQUENCES)
        n_mis = counts.get("missense_variant", 0)
        total = sum(counts.values())
        if total == 0:
            return {"available": False, "total_pathogenic": 0}
        return {
            "available": True,
            "total_pathogenic": total,
            "n_pathogenic_lof": n_lof,
            "n_pathogenic_missense": n_mis,
            "lof_is_disease_mechanism": n_lof >= 5,
            "missense_is_common_mechanism": total >= 10 and (n_mis / total) >= 0.25,
            "truncating_only_mechanism": total >= 10 and (n_mis / total) <= 0.02,
            "policy": MECHANISM_POLICY,
        }

    def _protein_lookup(self, gene: str, name: Optional[str],
                        exclude_key: str) -> dict[str, Optional[bool]]:
        """PS1/PM5 curated lookups. Requires the query variant's protein
        change (from its own ClinVar name or provided HGVS.p)."""
        out: dict[str, Optional[bool]] = {"same_aa": None, "same_residue": None}
        if not CLINVAR.exists() or not gene or not name:
            return out
        m = _P_CHANGE.search(name)
        if not m:
            return out
        full_change, _ref_aa, residue, alt_aa = m.groups()
        if alt_aa in ("=",):
            return out
        rows = self._db().execute(
            f"SELECT name, variant_key FROM '{CLINVAR}' "
            f"WHERE gene=? AND confidence_tier>=2 "
            f"AND label IN ('pathogenic','likely_pathogenic') "
            f"AND consequence_derived='missense_variant' AND name LIKE ?",
            [gene, f"%p.%{residue}%"]).fetchall()
        same_aa = same_residue = False
        for other_name, other_key in rows:
            if other_key == exclude_key:
                continue  # never count the query variant as its own evidence
            om = _P_CHANGE.search(other_name or "")
            if not om or om.group(3) != residue:
                continue
            if om.group(1) == full_change:
                same_aa = True
            elif om.group(4) != alt_aa:
                same_residue = True
        out["same_aa"] = same_aa
        out["same_residue"] = same_residue and not same_aa
        return out

    def population_af(self, v: CanonicalVariant) -> Optional[dict[str, Any]]:
        """Legacy-cohort AF lookup. Returns None when the store is missing;
        returns {'af_max': None, ...} when the store exists but the variant
        is absent (a meaningful 'absent from population data' signal)."""
        if not POP_AF.exists():
            return None
        row = self._db().execute(
            f"SELECT af_exac, af_tgp, af_esp, af_max FROM '{POP_AF}' "
            f"WHERE chrom=? AND pos=? AND ref=? AND alt=? LIMIT 1",
            [v.chromosome, v.position, v.reference, v.alternate]).fetchone()
        if row is None:
            return {"af_exac": None, "af_tgp": None, "af_esp": None,
                    "af_max": None, "absent": True, "source": POPULATION_SOURCE}
        return {"af_exac": row[0], "af_tgp": row[1], "af_esp": row[2],
                "af_max": row[3], "absent": False, "source": POPULATION_SOURCE}

    def alphamissense(self, v: CanonicalVariant) -> Optional[dict[str, Any]]:
        if not AM_STORE.exists():
            return None
        row = self._db().execute(
            f"SELECT am_pathogenicity, am_class, protein_variant FROM '{AM_STORE}' "
            f"WHERE chrom=? AND pos=? AND ref=? AND alt=? LIMIT 1",
            [f"chr{v.chromosome}", v.position, v.reference, v.alternate]).fetchone()
        if row is None:
            return None
        return {"am_pathogenicity": row[0], "am_class": row[1],
                "protein_variant": row[2],
                "source": "AlphaMissense precomputed (CC BY-NC-SA 4.0)"}

    # -- assembly ---------------------------------------------------------------
    def annotate(self, v: CanonicalVariant) -> dict[str, Any]:
        clinvar = self.clinvar_variant(v)
        gene = v.gene or (clinvar or {}).get("gene")
        genef = self._gene_features(gene) if gene else None
        mech = self._gene_mechanism(gene) if gene else None
        am = self.alphamissense(v)
        consequence = (v.consequence.value if v.consequence else None) or \
            (clinvar or {}).get("consequence_derived") or "unknown"
        prot = self._protein_lookup(gene, v.hgvs_p or (clinvar or {}).get("name"),
                                    f"{v.chromosome}:{v.position}:{v.reference}>{v.alternate}")
        return {
            "variant_id": v.variant_id,
            "gene": gene,
            "consequence": consequence,
            "clinvar": clinvar,
            "gene_features": genef,
            "gene_mechanism": mech,
            "alphamissense": am,
            "population": self.population_af(v),
            "protein_lookup": prot,
            "sources": self.source_summary(),
        }

    def to_evidence_inputs(self, annotation: dict[str, Any]) -> EvidenceInputs:
        csq = annotation["consequence"]
        # normalize splice consequence naming between VCF/enum and heuristic
        if csq in ("splice_donor_variant", "splice_acceptor_variant"):
            csq = "splice_donor_or_acceptor"
        # Allele-length in-frame call (REF/ALT only — not a VEP consequence).
        inframe_from_alleles = None
        vid = annotation.get("variant_id") or ""
        if ">" in vid:
            try:
                alleles = vid.rsplit(":", 1)[-1]
                ref, alt = alleles.split(">")
                delta = abs(len(ref) - len(alt))
                if delta > 0 and delta % 3 == 0 and "frameshift" not in (csq or ""):
                    inframe_from_alleles = True
                    if csq in ("unknown", "coding_indel_unspecified", None):
                        csq = "inframe_deletion" if len(ref) > len(alt) else "inframe_insertion"
            except ValueError:
                inframe_from_alleles = None
        mech = annotation.get("gene_mechanism") or {}
        genef = annotation.get("gene_features") or {}
        am = annotation.get("alphamissense") or {}
        prot = annotation.get("protein_lookup") or {}

        mis_z = genef.get("mis_z")
        return EvidenceInputs(
            consequence=csq,
            variant_type=None,
            protein_length_changing=(
                True if inframe_from_alleles else
                csq in ("inframe_insertion", "inframe_deletion", "stop_lost")),
            is_synonymous=(csq == "synonymous_variant") if csq != "unknown" else None,
            population=(
                PopulationEvidence(
                    source_available=True,
                    af=(annotation.get("population") or {}).get("af_max"),
                    af_popmax=(annotation.get("population") or {}).get("af_max"),
                ) if annotation.get("population") is not None
                else PopulationEvidence(source_available=False)
            ),
            computational=ComputationalEvidence(
                alphamissense=am.get("am_pathogenicity"),
                n_sources=1 if am else 0),
            functional=FunctionalEvidence(),  # no curated functional-study source configured
            gene_context=GeneContext(
                gene=annotation.get("gene"),
                lof_is_disease_mechanism=mech.get("lof_is_disease_mechanism")
                    if mech.get("available") else None,
                missense_constrained=(float(mis_z) > 3.09) if mis_z is not None else None,
                missense_is_common_mechanism=mech.get("missense_is_common_mechanism")
                    if mech.get("available") else None,
                truncating_only_mechanism=mech.get("truncating_only_mechanism")
                    if mech.get("available") else None,
                known_pathogenic_same_aa=prot.get("same_aa"),
                known_pathogenic_same_residue=prot.get("same_residue"),
            ),
        )
