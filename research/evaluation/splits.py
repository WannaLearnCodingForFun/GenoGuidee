"""
Leakage-safe evaluation splits (section 21).

Implemented strategies:
    random               stratified random variant split (the WEAK baseline —
                         reported, never used for model selection)
    gene_disjoint        genes in train never appear in val/test
    chromosome_disjoint  whole chromosomes held out
    temporal             train on variants last evaluated ≤ cutoff year,
                         test on later years (approximates release-time split;
                         caveat recorded: LastEvaluated ≠ submission date)
    expert_holdout       evaluation subset restricted to review tier ≥ 3
                         (expert panel / practice guideline) drawn from test

All functions return positional index arrays over the provided dataframe and
a metadata dict recording strategy, seed, sizes and disjointness proofs.
"""
from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd

SEED = 62

TEST_CHROMS = {"2", "9", "13", "20", "X"}
VAL_CHROMS = {"5", "11", "21"}
TEMPORAL_TRAIN_MAX_YEAR = 2022
TEMPORAL_VAL_YEAR = 2023  # val = 2023, test = 2024+


def _finalize(df: pd.DataFrame, train_idx, val_idx, test_idx, strategy: str,
              extra: dict | None = None) -> dict[str, Any]:
    meta = {
        "strategy": strategy,
        "seed": SEED,
        "n_train": int(len(train_idx)),
        "n_val": int(len(val_idx)),
        "n_test": int(len(test_idx)),
        **(extra or {}),
    }
    if strategy == "gene_disjoint":
        tg = set(df.iloc[train_idx]["gene"])
        vg = set(df.iloc[val_idx]["gene"])
        sg = set(df.iloc[test_idx]["gene"])
        meta["gene_overlap_train_test"] = len(tg & sg)
        meta["gene_overlap_train_val"] = len(tg & vg)
    if strategy == "chromosome_disjoint":
        meta["chrom_overlap_train_test"] = len(
            set(df.iloc[train_idx]["chrom"]) & set(df.iloc[test_idx]["chrom"]))
    return {"train": np.asarray(train_idx), "val": np.asarray(val_idx),
            "test": np.asarray(test_idx), "meta": meta}


def random_split(df: pd.DataFrame, val_frac=0.1, test_frac=0.15, seed=SEED) -> dict:
    rng = np.random.default_rng(seed)
    idx = rng.permutation(len(df))
    n_test = int(len(df) * test_frac)
    n_val = int(len(df) * val_frac)
    return _finalize(df, idx[n_test + n_val:], idx[n_test:n_test + n_val],
                     idx[:n_test], "random")


def gene_disjoint_split(df: pd.DataFrame, val_frac=0.1, test_frac=0.15, seed=SEED) -> dict:
    rng = np.random.default_rng(seed)
    genes = df["gene"].fillna("__NA__").to_numpy()
    uniq = rng.permutation(pd.unique(genes))
    # allocate genes to buckets proportionally to their variant counts
    counts = pd.Series(genes).value_counts()
    total = len(df)
    test_genes, val_genes = set(), set()
    acc = 0
    it = iter(uniq)
    for g in it:
        test_genes.add(g)
        acc += counts[g]
        if acc >= total * test_frac:
            break
    acc = 0
    for g in it:
        val_genes.add(g)
        acc += counts[g]
        if acc >= total * val_frac:
            break
    in_test = np.isin(genes, list(test_genes))
    in_val = np.isin(genes, list(val_genes))
    idx = np.arange(len(df))
    return _finalize(df, idx[~in_test & ~in_val], idx[in_val], idx[in_test],
                     "gene_disjoint",
                     {"n_test_genes": len(test_genes), "n_val_genes": len(val_genes)})


def chromosome_disjoint_split(df: pd.DataFrame) -> dict:
    chrom = df["chrom"].astype(str)
    in_test = chrom.isin(TEST_CHROMS).to_numpy()
    in_val = chrom.isin(VAL_CHROMS).to_numpy()
    idx = np.arange(len(df))
    return _finalize(df, idx[~in_test & ~in_val], idx[in_val], idx[in_test],
                     "chromosome_disjoint",
                     {"test_chroms": sorted(TEST_CHROMS), "val_chroms": sorted(VAL_CHROMS)})


def temporal_split(df: pd.DataFrame) -> dict:
    year = pd.to_numeric(df["meta_year"], errors="coerce")
    known = year.notna().to_numpy()
    train = (year <= TEMPORAL_TRAIN_MAX_YEAR).to_numpy() & known
    val = (year == TEMPORAL_VAL_YEAR).to_numpy() & known
    test = (year > TEMPORAL_VAL_YEAR).to_numpy() & known
    idx = np.arange(len(df))
    return _finalize(df, idx[train], idx[val], idx[test], "temporal",
                     {"train_max_year": TEMPORAL_TRAIN_MAX_YEAR,
                      "caveat": "LastEvaluated approximates but does not equal ClinVar release date",
                      "rows_without_year_excluded": int((~known).sum())})


def expert_holdout(df: pd.DataFrame, base_split: dict) -> np.ndarray:
    """Ultra-clean eval subset: tier ≥ 3 rows inside the base split's test set."""
    test_idx = base_split["test"]
    tiers = df.iloc[test_idx]["meta_confidence_tier"].to_numpy()
    return test_idx[tiers >= 3]


SPLITTERS = {
    "random": random_split,
    "gene_disjoint": gene_disjoint_split,
    "chromosome_disjoint": chromosome_disjoint_split,
    "temporal": temporal_split,
}
