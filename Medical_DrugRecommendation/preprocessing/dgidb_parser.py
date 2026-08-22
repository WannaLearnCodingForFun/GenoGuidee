"""DGIdb (Drug-Gene Interaction Database) dataset parser.

Parses DGIdb TSV files (interactions, drugs, genes, categories) and indexes
gene-drug interactions and drug attributes. Optimized for fast vectorized loading.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import os
from typing import Any

import pandas as pd

from .normalizer import normalize_gene


@dataclass
class DGIdbInteraction:
    gene_name: str
    drug_name: str
    interaction_types: list[str]
    interaction_score: float
    drug_is_approved: bool
    drug_is_antineoplastic: bool
    drug_is_immunotherapy: bool
    evidence_score: int
    interaction_source_db_name: str


@dataclass
class DGIdbDrugInfo:
    drug_name: str
    approved: bool
    immunotherapy: bool
    anti_neoplastic: bool
    concept_id: str
    categories: list[str] = field(default_factory=list)


class DGIdbParser:
    """Parser and index for DGIdb datasets."""

    def __init__(self, data_dir: str | None = None) -> None:
        if data_dir is None:
            data_dir = os.path.join(os.path.dirname(__file__), "..", "Data")
        self.data_dir = os.path.abspath(data_dir)
        self.interactions_by_gene: dict[str, list[DGIdbInteraction]] = {}
        self.interactions_by_gene_drug: dict[tuple[str, str], DGIdbInteraction] = {}
        self.drugs_info: dict[str, DGIdbDrugInfo] = {}
        self.gene_categories: dict[str, list[str]] = {}
        self.loaded = False

    def load_data(self) -> None:
        """Load DGIdb TSV files rapidly into memory."""
        if self.loaded:
            return

        categories_file = os.path.join(self.data_dir, "categories.tsv")
        drugs_file = os.path.join(self.data_dir, "drugs.tsv")
        interactions_file = os.path.join(self.data_dir, "interactions.tsv")

        # 1. Parse categories
        if os.path.exists(categories_file):
            df_cat = pd.read_csv(categories_file, sep="\t", comment="#", usecols=["gene_claim_name", "gene_category_name"], low_memory=False)
            df_cat.dropna(inplace=True)
            for g_claim, cat_name in zip(df_cat["gene_claim_name"], df_cat["gene_category_name"]):
                norm_g = normalize_gene(str(g_claim))
                cat_str = str(cat_name).strip()
                if norm_g and cat_str:
                    if norm_g not in self.gene_categories:
                        self.gene_categories[norm_g] = []
                    if cat_str not in self.gene_categories[norm_g]:
                        self.gene_categories[norm_g].append(cat_str)

        # 2. Parse drugs info
        if os.path.exists(drugs_file):
            df_drugs = pd.read_csv(drugs_file, sep="\t", comment="#", usecols=["drug_name", "approved", "immunotherapy", "anti_neoplastic", "concept_id"], low_memory=False)
            df_drugs.dropna(subset=["drug_name"], inplace=True)
            for d_name, app, immu, anti, cid in zip(
                df_drugs["drug_name"], df_drugs["approved"], df_drugs["immunotherapy"], df_drugs["anti_neoplastic"], df_drugs["concept_id"]
            ):
                name_str = str(d_name).strip()
                if not name_str or name_str.lower() == "nan":
                    continue
                d_key = name_str.lower()
                if d_key not in self.drugs_info:
                    self.drugs_info[d_key] = DGIdbDrugInfo(
                        drug_name=name_str,
                        approved=str(app).lower() == "true",
                        immunotherapy=str(immu).lower() == "true",
                        anti_neoplastic=str(anti).lower() == "true",
                        concept_id=str(cid) if pd.notna(cid) else "",
                    )

        # 3. Parse interactions
        if os.path.exists(interactions_file):
            cols = [
                "gene_name", "drug_name", "interaction_types", "interaction_score",
                "drug_is_approved", "drug_is_antineoplastic", "drug_is_immunotherapy",
                "evidence_score", "interaction_source_db_name"
            ]
            df_int = pd.read_csv(interactions_file, sep="\t", comment="#", usecols=lambda c: c in cols, low_memory=False)
            df_int.dropna(subset=["gene_name", "drug_name"], inplace=True)

            g_names = df_int["gene_name"].astype(str).values
            d_names = df_int["drug_name"].astype(str).values
            int_types = df_int["interaction_types"].fillna("").astype(str).values
            int_scores = pd.to_numeric(df_int["interaction_score"], errors="coerce").fillna(0.0).values
            is_apps = (df_int["drug_is_approved"].astype(str).str.lower() == "true").values
            is_antis = (df_int["drug_is_antineoplastic"].astype(str).str.lower() == "true").values
            is_immus = (df_int["drug_is_immunotherapy"].astype(str).str.lower() == "true").values
            ev_scores = pd.to_numeric(df_int["evidence_score"], errors="coerce").fillna(0).astype(int).values
            source_dbs = df_int["interaction_source_db_name"].fillna("").astype(str).values

            for g_raw, d_raw, t_raw, score, is_app, is_anti, is_immu, ev_sc, src in zip(
                g_names, d_names, int_types, int_scores, is_apps, is_antis, is_immus, ev_scores, source_dbs
            ):
                if not g_raw or not d_raw or d_raw == "nan":
                    continue

                norm_g = normalize_gene(g_raw)
                d_key = d_raw.lower()

                types_list = [
                    t.strip()
                    for t in t_raw.split(",")
                    if t.strip() and t.strip().lower() != "nan"
                ]

                interaction = DGIdbInteraction(
                    gene_name=norm_g,
                    drug_name=d_raw,
                    interaction_types=types_list,
                    interaction_score=float(score),
                    drug_is_approved=bool(is_app),
                    drug_is_antineoplastic=bool(is_anti),
                    drug_is_immunotherapy=bool(is_immu),
                    evidence_score=int(ev_sc),
                    interaction_source_db_name=src,
                )

                if norm_g not in self.interactions_by_gene:
                    self.interactions_by_gene[norm_g] = []
                self.interactions_by_gene[norm_g].append(interaction)

                pair_key = (norm_g, d_key)
                if pair_key not in self.interactions_by_gene_drug:
                    self.interactions_by_gene_drug[pair_key] = interaction
                else:
                    if score > self.interactions_by_gene_drug[pair_key].interaction_score:
                        self.interactions_by_gene_drug[pair_key] = interaction

        self.loaded = True

    def get_interactions_for_gene(self, gene: str) -> list[DGIdbInteraction]:
        """Retrieve all DGIdb drug interactions for a gene."""
        if not self.loaded:
            self.load_data()
        norm_g = normalize_gene(gene)
        return self.interactions_by_gene.get(norm_g, [])

    def get_interaction(self, gene: str, drug_name: str) -> DGIdbInteraction | None:
        """Lookup specific gene-drug interaction."""
        if not self.loaded:
            self.load_data()
        norm_g = normalize_gene(gene)
        d_key = drug_name.strip().lower()
        return self.interactions_by_gene_drug.get((norm_g, d_key))

    def get_drug_info(self, drug_name: str) -> DGIdbDrugInfo | None:
        """Get general drug metadata (approval, antineoplastic, immunotherapy)."""
        if not self.loaded:
            self.load_data()
        d_key = drug_name.strip().lower()
        return self.drugs_info.get(d_key)
