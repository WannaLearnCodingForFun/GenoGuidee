"""Candidate drug generator.

Discovers drug candidates for a given genomic mutation and disease context by
combining direct variant evidence from CIViC with target interaction data from DGIdb.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from preprocessing.civic_parser import CIViCEvidenceItem, CIViCParser
from preprocessing.dgidb_parser import DGIdbDrugInfo, DGIdbInteraction, DGIdbParser
from preprocessing.normalizer import normalize_disease, normalize_gene, normalize_variant


@dataclass
class CandidateDrug:
    drug_name: str
    canonical_name: str
    sources: list[str] = field(default_factory=list)
    civic_evidence: list[CIViCEvidenceItem] = field(default_factory=list)
    dgidb_interaction: DGIdbInteraction | None = None
    dgidb_info: DGIdbDrugInfo | None = None


class CandidateGenerator:
    """Generates candidate drugs for mutation payloads."""

    def __init__(
        self, civic_parser: CIViCParser | None = None, dgidb_parser: DGIdbParser | None = None
    ) -> None:
        self.civic_parser = civic_parser or CIViCParser()
        self.dgidb_parser = dgidb_parser or DGIdbParser()

    def generate_candidates(
        self, gene: str, variant: str, disease: str
    ) -> dict[str, CandidateDrug]:
        """Discover candidate drugs from CIViC evidence and DGIdb interactions.

        Returns:
            dict mapping lowercase canonical drug name to CandidateDrug objects.
        """
        norm_g = normalize_gene(gene)
        norm_v = normalize_variant(variant)
        norm_d = normalize_disease(disease)

        if not self.civic_parser.loaded:
            self.civic_parser.load_data()
        if not self.dgidb_parser.loaded:
            self.dgidb_parser.load_data()

        candidates: dict[str, CandidateDrug] = {}

        # 1. Fetch CIViC evidence for gene + variant
        var_evidence = self.civic_parser.get_evidence_by_variant(norm_g, norm_v, norm_d)
        if not var_evidence:
            var_evidence = self.civic_parser.get_evidence_by_variant(norm_g, norm_v)

        for ev in var_evidence:
            for drug in ev.therapies:
                if not drug or drug.lower() == "nan":
                    continue
                d_key = drug.strip().lower()
                if d_key not in candidates:
                    candidates[d_key] = CandidateDrug(
                        drug_name=drug.strip(),
                        canonical_name=d_key,
                        sources=["CIViC_variant"],
                    )
                if "CIViC_variant" not in candidates[d_key].sources:
                    candidates[d_key].sources.append("CIViC_variant")
                candidates[d_key].civic_evidence.append(ev)

        # 2. Fetch gene-level CIViC evidence if candidate set is small
        gene_evidence = self.civic_parser.get_evidence_by_gene(norm_g, norm_d)
        for ev in gene_evidence:
            for drug in ev.therapies:
                if not drug or drug.lower() == "nan":
                    continue
                d_key = drug.strip().lower()
                if d_key not in candidates:
                    candidates[d_key] = CandidateDrug(
                        drug_name=drug.strip(),
                        canonical_name=d_key,
                        sources=["CIViC_gene"],
                    )
                if "CIViC_gene" not in candidates[d_key].sources:
                    candidates[d_key].sources.append("CIViC_gene")
                candidates[d_key].civic_evidence.append(ev)

        # 3. Enrich and discover candidates from DGIdb
        dgidb_interactions = self.dgidb_parser.get_interactions_for_gene(norm_g)
        for int_obj in dgidb_interactions:
            d_raw = int_obj.drug_name.strip()
            d_key = d_raw.lower()
            if d_key not in candidates:
                candidates[d_key] = CandidateDrug(
                    drug_name=d_raw,
                    canonical_name=d_key,
                    sources=["DGIdb_gene"],
                )
            if "DGIdb_gene" not in candidates[d_key].sources:
                candidates[d_key].sources.append("DGIdb_gene")
            candidates[d_key].dgidb_interaction = int_obj

        # 4. Attach general DGIdb drug info to all candidates
        for d_key, cand in candidates.items():
            if not cand.dgidb_interaction:
                cand.dgidb_interaction = self.dgidb_parser.get_interaction(norm_g, cand.drug_name)
            cand.dgidb_info = self.dgidb_parser.get_drug_info(cand.drug_name)

        return candidates
