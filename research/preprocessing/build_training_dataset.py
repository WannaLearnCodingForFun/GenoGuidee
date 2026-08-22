"""
Training dataset builder: labeled ClinVar variants ⨝ gene features
(⨝ AlphaMissense when its store is available).

Stage flow (section 67):   raw → clean → dedup → label → feature join →
quality filter → (splits happen later, in research.evaluation.splits)

LABEL LEAKAGE POLICY (enforced here, tested in tests/test_safety.py):
  * review_status / confidence_tier / n_submitters / clinsig text / phenotype
    lists are NEVER features — they are metadata columns prefixed `meta_`.
  * The label column and anything derived from it is excluded from FEATURES.

Output:
    research/data/processed/training_dataset.parquet
    research/reports/data_quality_report.json (+ .html)
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
CLINVAR = REPO / "research/data/processed/clinvar_grch38.parquet"
GENES = REPO / "research/data/processed/gene_features.parquet"
AM_STORE = REPO / "research/data/interim/alphamissense_hg38.parquet"
OUT = REPO / "research/data/processed/training_dataset.parquet"
QREPORT = REPO / "research/reports/data_quality_report.json"

LABELS = ["benign", "likely_benign", "vus", "likely_pathogenic", "pathogenic"]

CONSEQUENCES = [
    "missense_variant", "synonymous_variant", "stop_gained", "frameshift_variant",
    "splice_donor_or_acceptor", "start_lost", "coding_indel_unspecified", "unknown",
]
VARIANT_TYPES = ["SNV", "MNV", "insertion", "deletion"]

# columns that constitute the model input; everything else is metadata
FEATURE_COLUMNS: list[str] = (
    [f"csq_{c}" for c in CONSEQUENCES]
    + [f"vt_{t}" for t in VARIANT_TYPES]
    + ["ref_len", "alt_len", "len_delta",
       "loeuf", "pli", "mis_z", "syn_z", "gene_feat_missing",
       "clingen_validity", "clingen_n_diseases",
       "am_pathogenicity", "am_missing"]
)

FORBIDDEN_AS_FEATURES = {
    "label", "meta_confidence_tier", "meta_review_status", "meta_n_submitters",
    "meta_clinsig_raw", "meta_phenotype_list", "meta_variation_id",
}


def build(min_tier: int = 1) -> dict:
    if not CLINVAR.exists() or not GENES.exists():
        raise FileNotFoundError("run build_clinvar_dataset and gene_features first")
    con = duckdb.connect()
    con.execute("SET threads TO 4; SET memory_limit='6GB'")

    am_available = AM_STORE.exists()
    am_join = f"""
        LEFT JOIN '{AM_STORE}' am
          ON am.chrom = 'chr' || c.chrom AND am.pos = c.pos
         AND am.ref = c.ref AND am.alt = c.alt
    """ if am_available else ""
    am_select = "am.am_pathogenicity AS am_pathogenicity," if am_available else "NULL AS am_pathogenicity,"

    df = con.sql(f"""
        SELECT
            c.variant_key, c.gene, c.chrom, c.pos, c.ref, c.alt,
            c.variant_type, c.consequence_derived AS consequence,
            c.label,
            c.confidence_tier   AS meta_confidence_tier,
            c.review_status     AS meta_review_status,
            c.n_submitters      AS meta_n_submitters,
            c.variation_id      AS meta_variation_id,
            c.name              AS meta_name,
            c.last_evaluated_year AS meta_year,
            {am_select}
            g.loeuf, g.pli, g.mis_z, g.syn_z,
            g.clingen_validity, g.clingen_n_diseases
        FROM '{CLINVAR}' c
        LEFT JOIN '{GENES}' g ON g.gene = c.gene
        {am_join}
        WHERE c.label IS NOT NULL
          AND c.confidence_tier >= {min_tier}
    """).df()

    stages = {"labeled_min_tier_rows": len(df)}

    # ---- feature engineering (vectorized) -----------------------------------
    for c in CONSEQUENCES:
        df[f"csq_{c}"] = (df["consequence"] == c).astype(np.int8)
    for t in VARIANT_TYPES:
        df[f"vt_{t}"] = (df["variant_type"] == t).astype(np.int8)
    df["ref_len"] = df["ref"].str.len().astype(np.int32)
    df["alt_len"] = df["alt"].str.len().astype(np.int32)
    df["len_delta"] = (df["alt_len"] - df["ref_len"]).astype(np.int32)

    for c in ("loeuf", "pli", "mis_z", "syn_z"):
        df[c] = pd.to_numeric(df[c], errors="coerce")
    df["gene_feat_missing"] = df["loeuf"].isna().astype(np.int8)
    df["clingen_validity"] = pd.to_numeric(df["clingen_validity"], errors="coerce").fillna(0)
    df["clingen_n_diseases"] = pd.to_numeric(df["clingen_n_diseases"], errors="coerce").fillna(0)

    df["am_pathogenicity"] = pd.to_numeric(df["am_pathogenicity"], errors="coerce")
    df["am_missing"] = df["am_pathogenicity"].isna().astype(np.int8)

    df["y"] = df["label"].map({l: i for i, l in enumerate(LABELS)}).astype(np.int8)
    df["y_binary"] = df["label"].map(
        {"pathogenic": 1, "likely_pathogenic": 1, "benign": 0, "likely_benign": 0}
    )  # NaN for VUS — binary task excludes them

    assert not (set(FEATURE_COLUMNS) & FORBIDDEN_AS_FEATURES), "label leakage in feature list"

    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)

    # ---- quality report ------------------------------------------------------
    feat = df[FEATURE_COLUMNS]
    corr_pairs = []
    numeric = feat.select_dtypes(include=[np.number])
    corr = numeric.corr().abs()
    for i, a in enumerate(corr.columns):
        for b in corr.columns[i + 1:]:
            v = corr.loc[a, b]
            if pd.notna(v) and v > 0.85:
                corr_pairs.append({"a": a, "b": b, "abs_corr": round(float(v), 3)})

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "rows": len(df),
        "n_genes": int(df["gene"].nunique()),
        "alphamissense_joined": am_available,
        "am_coverage_of_missense": (
            float(1 - df.loc[df["csq_missense_variant"] == 1, "am_missing"].mean())
            if am_available and (df["csq_missense_variant"] == 1).any() else 0.0
        ),
        "class_distribution": df["label"].value_counts().to_dict(),
        "binary_task_rows": int(df["y_binary"].notna().sum()),
        "missingness": {c: float(df[c].isna().mean()) for c in
                        ("loeuf", "pli", "mis_z", "am_pathogenicity")},
        "duplicates_by_variant_key": int(df["variant_key"].duplicated().sum()),
        "high_correlation_pairs": corr_pairs,
        "feature_columns": FEATURE_COLUMNS,
        "forbidden_metadata_columns": sorted(FORBIDDEN_AS_FEATURES),
        "chromosome_distribution": df["chrom"].value_counts().to_dict(),
        "stages": stages,
    }
    QREPORT.parent.mkdir(parents=True, exist_ok=True)
    QREPORT.write_text(json.dumps(report, indent=2, default=str))

    html = ["<html><head><title>GenoGuide data quality</title></head><body>",
            f"<h1>Data quality report</h1><p>{report['generated']}</p>",
            f"<p>rows={report['rows']:,} genes={report['n_genes']:,} "
            f"AlphaMissense joined={am_available}</p>",
            "<h2>Class distribution</h2><ul>"]
    for k, v in report["class_distribution"].items():
        html.append(f"<li>{k}: {v:,}</li>")
    html.append("</ul><h2>Missingness</h2><ul>")
    for k, v in report["missingness"].items():
        html.append(f"<li>{k}: {v:.1%}</li>")
    html.append("</ul><h2>|r| &gt; 0.85 feature pairs</h2><ul>")
    for p in corr_pairs:
        html.append(f"<li>{p['a']} ↔ {p['b']}: {p['abs_corr']}</li>")
    html.append("</ul></body></html>")
    QREPORT.with_suffix(".html").write_text("\n".join(html))
    return report


if __name__ == "__main__":
    r = build()
    print(json.dumps({k: r[k] for k in
                      ("rows", "n_genes", "alphamissense_joined", "am_coverage_of_missense",
                       "class_distribution", "high_correlation_pairs")}, indent=2, default=str))
