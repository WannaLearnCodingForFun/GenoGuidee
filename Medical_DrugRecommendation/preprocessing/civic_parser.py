"""CIViC (Clinical Interpretation of Variants in Cancer) dataset parser.

Parses CIViC TSV summary files (evidence, assertions, variant summaries,
molecular profiles) and IntOGen driver genes from Medical_DrugRecommendation/Data.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
import re
from typing import Any

import pandas as pd

from .normalizer import normalize_disease, normalize_gene, normalize_variant


@dataclass
class CIViCEvidenceItem:
    evidence_id: str
    molecular_profile: str
    gene: str
    variant: str
    disease: str
    doid: str
    therapies: list[str]
    therapy_interaction_type: str
    evidence_type: str
    evidence_direction: str
    evidence_level: str
    significance: str
    rating: float
    citation: str
    nct_ids: str
    source: str = "Evidence"


@dataclass
class DriverGeneInfo:
    symbol: str
    mutations_count: int
    samples_count: int
    sample_percentage: float
    cohorts_count: int


class CIViCParser:
    """Parser and query index for CIViC and IntOGen datasets in Data folder."""

    def __init__(self, data_dir: str | None = None) -> None:
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), "..", "Data")
        self.data_dir = os.path.abspath(data_dir)
        self.evidence_items: list[CIViCEvidenceItem] = []
        self._by_gene_variant: dict[tuple[str, str], list[CIViCEvidenceItem]] = {}
        self._by_gene: dict[str, list[CIViCEvidenceItem]] = {}
        self.driver_genes: dict[str, DriverGeneInfo] = {}
        self.variant_aliases: dict[tuple[str, str], list[str]] = {}
        self.loaded = False

    def load_data(self) -> None:
        """Load CIViC and IntOGen TSV files from Medical_DrugRecommendation/Data."""
        if self.loaded:
            return

        # 1. Parse IntOGen Driver Genes
        intogen_file = os.path.join(self.data_dir, "IntOGen-DriverGenes.tsv")
        if os.path.exists(intogen_file):
            try:
                df_into = pd.read_csv(intogen_file, sep="\t", low_memory=False)
                for _, row in df_into.iterrows():
                    sym = str(row.get("Symbol", "") or "").strip()
                    if not sym:
                        continue
                    norm_sym = normalize_gene(sym)

                    muts_raw = str(row.get("Mutations", "0")).replace(",", "").strip()
                    samps_raw = str(row.get("Samples", "0")).replace(",", "").strip()
                    perc_raw = str(row.get("Samples (%)", "0")).replace(",", "").strip()
                    cohorts_raw = str(row.get("Cohorts", "0")).replace(",", "").strip()

                    try:
                        muts = int(float(muts_raw))
                        samps = int(float(samps_raw))
                        perc = float(perc_raw)
                        cohorts = int(float(cohorts_raw))
                    except ValueError:
                        muts = samps = cohorts = 0
                        perc = 0.0

                    self.driver_genes[norm_sym] = DriverGeneInfo(
                        symbol=norm_sym,
                        mutations_count=muts,
                        samples_count=samps,
                        sample_percentage=perc,
                        cohorts_count=cohorts,
                    )
            except Exception as e:
                print(f"Notice: Error loading IntOGen dataset: {e}")

        # 2. Parse CIViC Variant Summaries for aliases
        variant_summary_file = os.path.join(self.data_dir, "nightly-VariantSummaries.tsv")
        if os.path.exists(variant_summary_file):
            try:
                df_var = pd.read_csv(variant_summary_file, sep="\t", low_memory=False)
                for _, row in df_var.iterrows():
                    g_raw = str(row.get("gene", "") or "").strip()
                    v_raw = str(row.get("variant", "") or "").strip()
                    aliases_raw = str(row.get("variant_aliases", "") or "").strip()
                    if g_raw and v_raw:
                        norm_g = normalize_gene(g_raw)
                        norm_v = normalize_variant(v_raw)
                        aliases_list = [
                            normalize_variant(a)
                            for a in aliases_raw.split(",")
                            if a.strip() and a.strip().lower() != "nan"
                        ]
                        key = (norm_g, norm_v)
                        if key not in self.variant_aliases:
                            self.variant_aliases[key] = []
                        for al in aliases_list:
                            if al not in self.variant_aliases[key]:
                                self.variant_aliases[key].append(al)
            except Exception as e:
                print(f"Notice: Error loading VariantSummaries: {e}")

        # 3. Parse CIViC Accepted Clinical Evidence
        evidence_file = os.path.join(self.data_dir, "nightly-AcceptedClinicalEvidenceSummaries.tsv")
        if not os.path.exists(evidence_file):
            evidence_file = os.path.join(
                self.data_dir, "nightly-AcceptedAndSubmittedClinicalEvidenceSummaries.tsv"
            )

        if not os.path.exists(evidence_file):
            raise FileNotFoundError(f"CIViC evidence file not found in {self.data_dir}")

        df_ev = pd.read_csv(evidence_file, sep="\t", low_memory=False)

        items: list[CIViCEvidenceItem] = []
        for _, row in df_ev.iterrows():
            mol_prof = str(row.get("molecular_profile", "") or "").strip()
            disease_raw = str(row.get("disease", "") or "").strip()
            therapies_raw = str(row.get("therapies", "") or "").strip()

            if not mol_prof or not therapies_raw or therapies_raw == "nan":
                continue

            gene, variant = self._parse_molecular_profile(mol_prof)
            norm_gene = normalize_gene(gene)
            norm_var = normalize_variant(variant)
            norm_dis = normalize_disease(disease_raw)

            therapies_list = [
                t.strip()
                for t in therapies_raw.split(",")
                if t.strip() and t.strip().lower() != "nan"
            ]
            if not therapies_list:
                continue

            rating_val = 3.0
            try:
                if pd.notna(row.get("rating")):
                    rating_val = float(row.get("rating"))
            except (ValueError, TypeError):
                pass

            item = CIViCEvidenceItem(
                evidence_id=str(row.get("evidence_id", "")),
                molecular_profile=mol_prof,
                gene=norm_gene,
                variant=norm_var,
                disease=norm_dis,
                doid=str(row.get("doid", "") or ""),
                therapies=therapies_list,
                therapy_interaction_type=str(row.get("therapy_interaction_type", "") or ""),
                evidence_type=str(row.get("evidence_type", "") or "Predictive"),
                evidence_direction=str(row.get("evidence_direction", "") or "Supports"),
                evidence_level=str(row.get("evidence_level", "") or "B").upper(),
                significance=str(row.get("significance", "") or "Sensitivity/Response"),
                rating=rating_val,
                citation=str(row.get("citation", "") or ""),
                nct_ids=str(row.get("nct_ids", "") or ""),
                source="Evidence",
            )

            items.append(item)
            key_gv = (norm_gene, norm_var)
            if key_gv not in self._by_gene_variant:
                self._by_gene_variant[key_gv] = []
            self._by_gene_variant[key_gv].append(item)

            if norm_gene not in self._by_gene:
                self._by_gene[norm_gene] = []
            self._by_gene[norm_gene].append(item)

        # 4. Parse CIViC Clinical Assertions
        assertion_file = os.path.join(self.data_dir, "nightly-AcceptedAssertionSummaries.tsv")
        if not os.path.exists(assertion_file):
            assertion_file = os.path.join(
                self.data_dir, "nightly-AcceptedAndSubmittedAssertionSummaries.tsv"
            )

        if os.path.exists(assertion_file):
            try:
                df_ass = pd.read_csv(assertion_file, sep="\t", low_memory=False)
                for _, row in df_ass.iterrows():
                    mol_prof = str(row.get("molecular_profile", "") or "").strip()
                    disease_raw = str(row.get("disease", "") or "").strip()
                    therapies_raw = str(row.get("therapies", "") or "").strip()

                    if not mol_prof or not therapies_raw or therapies_raw == "nan":
                        continue

                    gene, variant = self._parse_molecular_profile(mol_prof)
                    norm_gene = normalize_gene(gene)
                    norm_var = normalize_variant(variant)
                    norm_dis = normalize_disease(disease_raw)

                    therapies_list = [
                        t.strip()
                        for t in therapies_raw.split(",")
                        if t.strip() and t.strip().lower() != "nan"
                    ]
                    if not therapies_list:
                        continue

                    amp_cat = str(row.get("amp_category", "") or "Tier I")
                    level = "A" if "tier i" in amp_cat.lower() else "B"

                    item = CIViCEvidenceItem(
                        evidence_id=str(row.get("assertion_id", "")),
                        molecular_profile=mol_prof,
                        gene=norm_gene,
                        variant=norm_var,
                        disease=norm_dis,
                        doid=str(row.get("doid", "") or ""),
                        therapies=therapies_list,
                        therapy_interaction_type="",
                        evidence_type=str(row.get("assertion_type", "") or "Predictive"),
                        evidence_direction=str(row.get("assertion_direction", "") or "Supports"),
                        evidence_level=level,
                        significance=str(row.get("significance", "") or "Sensitivity/Response"),
                        rating=5.0,  # Assertions represent high-confidence clinical guidelines
                        citation=str(row.get("nccn_guideline", "") or ""),
                        nct_ids="",
                        source="Assertion",
                    )

                    items.append(item)
                    key_gv = (norm_gene, norm_var)
                    if key_gv not in self._by_gene_variant:
                        self._by_gene_variant[key_gv] = []
                    self._by_gene_variant[key_gv].append(item)

                    if norm_gene not in self._by_gene:
                        self._by_gene[norm_gene] = []
                    self._by_gene[norm_gene].append(item)
            except Exception as e:
                print(f"Notice: Error loading AssertionSummaries: {e}")

        self.evidence_items = items
        self.loaded = True

    def _parse_molecular_profile(self, profile: str) -> tuple[str, str]:
        """Extract gene and variant from molecular profile string."""
        parts = profile.strip().split()
        if not parts:
            return ("", "")
        if len(parts) == 1:
            return (parts[0], "")
        gene = parts[0]
        variant = " ".join(parts[1:])
        return (gene, variant)

    def get_driver_info(self, gene: str) -> DriverGeneInfo | None:
        """Get IntOGen driver gene statistics for a gene."""
        if not self.loaded:
            self.load_data()
        norm_g = normalize_gene(gene)
        return self.driver_genes.get(norm_g)

    def get_evidence_by_variant(
        self, gene: str, variant: str, disease: str | None = None
    ) -> list[CIViCEvidenceItem]:
        """Lookup CIViC evidence items matching gene and variant."""
        if not self.loaded:
            self.load_data()
        norm_g = normalize_gene(gene)
        norm_v = normalize_variant(variant)

        items = self._by_gene_variant.get((norm_g, norm_v), [])
        if not items:
            # Fallback matching substring or variant alias
            items = [
                it
                for it in self._by_gene.get(norm_g, [])
                if norm_v and norm_v in it.variant
            ]

        if disease:
            norm_d = normalize_disease(disease)
            disease_filtered = [
                it
                for it in items
                if it.disease.lower() == norm_d.lower()
                or norm_d.lower() in it.disease.lower()
            ]
            if disease_filtered:
                return disease_filtered

        return items

    def get_evidence_by_gene(
        self, gene: str, disease: str | None = None
    ) -> list[CIViCEvidenceItem]:
        """Lookup all CIViC evidence items for a given gene."""
        if not self.loaded:
            self.load_data()
        norm_g = normalize_gene(gene)
        items = self._by_gene.get(norm_g, [])

        if disease:
            norm_d = normalize_disease(disease)
            disease_filtered = [
                it
                for it in items
                if it.disease.lower() == norm_d.lower()
                or norm_d.lower() in it.disease.lower()
            ]
            if disease_filtered:
                return disease_filtered

        return items
