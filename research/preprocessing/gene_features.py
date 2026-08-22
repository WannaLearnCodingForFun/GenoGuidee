"""
Gene-level feature table from gnomAD v4.1 constraint + ClinGen gene-disease
validity. Output: research/data/processed/gene_features.parquet

Features (feature_group='gene'):
    loeuf            lof.oe_ci.upper on the MANE/canonical transcript
    pli              lof.pLI
    mis_z            missense z-score
    syn_z            synonymous z-score (sanity feature)
    clingen_validity strongest ClinGen classification (ordinal 0-5)
    clingen_moi      most severe curated mode of inheritance (AD/AR/XL/…)
    clingen_n_diseases
"""
from __future__ import annotations

import csv
import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
CONSTRAINT = REPO / "research/data/raw/gnomad_constraint/gnomad.v4.1.constraint_metrics.tsv"
CLINGEN = REPO / "research/data/raw/clingen/gene_validity.csv"
OUT = REPO / "research/data/processed/gene_features.parquet"
REPORT = REPO / "research/reports/gene_features_report.json"

VALIDITY_ORDINAL = {
    "Definitive": 5, "Strong": 4, "Moderate": 3, "Limited": 2,
    "Disputed Evidence": 1, "Disputed": 1, "Refuted Evidence": 0, "Refuted": 0,
    "No Known Disease Relationship": 0, "Animal Model Only": 1,
}


def load_clingen() -> dict[str, dict]:
    genes: dict[str, dict] = {}
    if not CLINGEN.exists():
        return genes
    with open(CLINGEN, newline="") as f:
        rows = list(csv.reader(f))
    # header block: title lines + '+++' separators around the column row
    data_started = False
    for row in rows:
        if not row or not row[0]:
            continue
        if row[0].startswith("+++"):
            data_started = True
            continue
        if not data_started or row[0] in ("GENE SYMBOL",):
            continue
        gene, _hgnc, disease, _mondo, moi, _sop, classification = (row + [""] * 7)[:7]
        if not gene or gene == "GENE SYMBOL":
            continue
        g = genes.setdefault(gene, {"validity": 0, "moi": set(), "n_diseases": 0})
        g["validity"] = max(g["validity"], VALIDITY_ORDINAL.get(classification, 0))
        if moi:
            g["moi"].add(moi)
        g["n_diseases"] += 1
    return genes


def build() -> dict:
    if not CONSTRAINT.exists():
        raise FileNotFoundError("constraint metrics missing — run data download gnomad_constraint")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    df = con.sql(f"""
        SELECT gene,
               "lof.oe_ci.upper"  AS loeuf,
               "lof.pLI"          AS pli,
               "mis.z_score"      AS mis_z,
               "syn.z_score"      AS syn_z,
               canonical, mane_select
        FROM read_csv('{CONSTRAINT}', delim='\t', header=true, all_varchar=true,
                      ignore_errors=true)
        WHERE gene IS NOT NULL
    """).df()

    for col in ("loeuf", "pli", "mis_z", "syn_z"):
        df[col] = df[col].astype(float, errors="ignore")
        df[col] = df[col].apply(lambda x: None if x in ("NA", "") else float(x) if x is not None else None)

    # prefer MANE select transcript, then canonical, then first row per gene
    df["pref"] = (df["mane_select"].astype(str).str.lower() == "true").astype(int) * 2 + (
        df["canonical"].astype(str).str.lower() == "true").astype(int)
    df = df.sort_values("pref", ascending=False).drop_duplicates("gene", keep="first")
    df = df.drop(columns=["canonical", "mane_select", "pref"])

    clingen = load_clingen()
    df["clingen_validity"] = df["gene"].map(lambda g: clingen.get(g, {}).get("validity", 0))
    df["clingen_moi"] = df["gene"].map(
        lambda g: ",".join(sorted(clingen.get(g, {}).get("moi", []))) or None)
    df["clingen_n_diseases"] = df["gene"].map(lambda g: clingen.get(g, {}).get("n_diseases", 0))

    df.to_parquet(OUT, index=False)
    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "n_genes": len(df),
        "n_genes_with_clingen": int((df["clingen_validity"] > 0).sum()),
        "missingness": {c: int(df[c].isna().sum()) for c in ("loeuf", "pli", "mis_z")},
        "sources": {
            "constraint": "gnomAD v4.1 constraint_metrics.tsv (CC0)",
            "clingen": "ClinGen gene-validity CSV (CC0)" if CLINGEN.exists() else "NOT AVAILABLE",
        },
    }
    REPORT.write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
