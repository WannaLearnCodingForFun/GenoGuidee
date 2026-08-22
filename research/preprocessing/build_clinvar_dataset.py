"""
ClinVar variant_summary → labeled GRCh38 variant table (parquet).

Design decisions (documented, not hidden):

* The aggregate ClinVar germline classification is NOT used blindly:
  - ReviewStatus is mapped to an ordinal confidence tier and preserved.
  - Conflicting records are kept with label=None + conflict flag — they are
    excluded from training but never deleted.
  - VariationID (VCV), RCV accessions, submitter counts, conditions and
    LastEvaluated dates are preserved per row.
* Consequence is derived from the ClinVar `Name` HGVS string with an explicit
  heuristic (consequence_source column records this). This is a stopgap until
  offline VEP annotation is configured; the heuristic only assigns a class
  when the pattern is unambiguous, otherwise `unknown`.
* Only germline-origin records are kept (OriginSimple contains 'germline').
* SNVs and small indels with valid VCF alleles are kept; symbolic/large
  events are out of scope for this table (CNV/SV extension point).

Outputs:
    research/data/processed/clinvar_grch38.parquet
    research/reports/clinvar_build_report.json   (stage-by-stage counts)
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import duckdb

REPO = Path(__file__).resolve().parents[2]
RAW = REPO / "research/data/raw/clinvar/variant_summary_2026-08.txt.gz"
OUT = REPO / "research/data/processed/clinvar_grch38.parquet"
REPORT = REPO / "research/reports/clinvar_build_report.json"

# --- label maps -------------------------------------------------------------

LABEL_MAP = {
    "Pathogenic": "pathogenic",
    "Likely pathogenic": "likely_pathogenic",
    "Pathogenic/Likely pathogenic": "likely_pathogenic",
    "Uncertain significance": "vus",
    "Likely benign": "likely_benign",
    "Benign/Likely benign": "likely_benign",
    "Benign": "benign",
}

# ordinal confidence tiers from ReviewStatus (higher = more trustworthy)
REVIEW_TIERS = {
    "practice guideline": 4,
    "reviewed by expert panel": 3,
    "criteria provided, multiple submitters, no conflicts": 2,
    "criteria provided, single submitter": 1,
    "criteria provided, conflicting classifications": 0,
    "no assertion criteria provided": 0,
    "no classification provided": 0,
    "no classification for the single variant": 0,
}

_P_MISSENSE = re.compile(r"\(p\.[A-Z][a-z]{2}\d+[A-Z][a-z]{2}\)")
_P_TER = re.compile(r"\(p\.[A-Z][a-z]{2}\d+(Ter|\*)\)")
_P_FS = re.compile(r"fs\)?\s*$|fs(Ter|\*)?\d*\)")
_P_SYN = re.compile(r"\(p\.[A-Z][a-z]{2}\d+=\)|\(p\.=\)")
_C_SPLICE = re.compile(r"c\.[\d*+-]+[+-][12](?![0-9])[ACGT]?>")
_C_DEL = re.compile(r"c\.[\d_+*-]+del")
_C_DUP = re.compile(r"c\.[\d_+*-]+dup")
_C_INS = re.compile(r"c\.[\d_+*-]+ins")


def derive_consequence(name: str) -> str:
    """Heuristic consequence from the ClinVar Name HGVS string."""
    if not name:
        return "unknown"
    if _P_FS.search(name):
        return "frameshift_variant"
    if _P_TER.search(name):
        return "stop_gained"
    if _P_SYN.search(name):
        return "synonymous_variant"
    if _P_MISSENSE.search(name):
        return "missense_variant"
    if _C_SPLICE.search(name):
        return "splice_donor_or_acceptor"
    if "p.Met1" in name and ("?" in name or "ext" not in name):
        return "start_lost"
    if _C_DEL.search(name) or _C_DUP.search(name) or _C_INS.search(name):
        return "coding_indel_unspecified"
    return "unknown"


def build(sample_limit: int | None = None) -> dict:
    if not RAW.exists():
        raise FileNotFoundError(
            f"{RAW} missing — run: python -m cli.genoguide data download clinvar_variant_summary")
    OUT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.parent.mkdir(parents=True, exist_ok=True)

    con = duckdb.connect()
    con.execute(f"SET threads TO 4")
    stages: dict[str, int] = {}

    con.execute(f"""
        CREATE VIEW raw AS
        SELECT * FROM read_csv('{RAW}', delim='\t', header=true, quote='',
                               all_varchar=true, ignore_errors=true)
    """)
    stages["raw_rows_both_builds"] = con.sql("SELECT COUNT(*) FROM raw").fetchone()[0]

    con.execute("""
        CREATE VIEW grch38 AS
        SELECT
            "VariationID"          AS variation_id,
            "#AlleleID"            AS allele_id,
            "GeneSymbol"           AS gene,
            "GeneID"               AS gene_id,
            "Type"                 AS clinvar_type,
            "Name"                 AS name,
            "Chromosome"           AS chrom,
            TRY_CAST("PositionVCF" AS BIGINT)  AS pos,
            "ReferenceAlleleVCF"   AS ref,
            "AlternateAlleleVCF"   AS alt,
            "ClinicalSignificance" AS clinsig_raw,
            "ReviewStatus"         AS review_status,
            TRY_CAST("NumberSubmitters" AS INTEGER) AS n_submitters,
            "RCVaccession"         AS rcv_accessions,
            "PhenotypeList"        AS phenotype_list,
            "OriginSimple"         AS origin_simple,
            "LastEvaluated"        AS last_evaluated
        FROM raw
        WHERE "Assembly" = 'GRCh38'
    """)
    stages["grch38_rows"] = con.sql("SELECT COUNT(*) FROM grch38").fetchone()[0]

    limit_clause = f"LIMIT {sample_limit}" if sample_limit else ""
    df = con.sql(f"""
        SELECT * FROM grch38
        WHERE origin_simple ILIKE '%germline%'
          AND chrom IN ('1','2','3','4','5','6','7','8','9','10','11','12','13',
                        '14','15','16','17','18','19','20','21','22','X','Y','MT')
          AND pos IS NOT NULL AND pos > 0
          AND ref SIMILAR TO '[ACGT]+' AND alt SIMILAR TO '[ACGT]+'
          AND ref != alt
          AND length(ref) <= 100 AND length(alt) <= 100
        {limit_clause}
    """).df()
    stages["germline_valid_alleles"] = len(df)

    # --- python-side enrichment (labels, tiers, consequence) ----------------
    df["label"] = df["clinsig_raw"].map(LABEL_MAP)
    df["label_conflict"] = df["clinsig_raw"].str.contains("Conflicting", case=False, na=False)
    df["confidence_tier"] = (
        df["review_status"].str.lower().map({k.lower(): v for k, v in REVIEW_TIERS.items()}).fillna(0).astype(int)
    )
    df["consequence_derived"] = df["name"].fillna("").map(derive_consequence)
    df["consequence_source"] = "clinvar_name_heuristic"
    df["variant_type"] = df.apply(
        lambda r: "SNV" if len(r["ref"]) == 1 and len(r["alt"]) == 1
        else ("MNV" if len(r["ref"]) == len(r["alt"])
              else ("insertion" if len(r["ref"]) < len(r["alt"]) else "deletion")),
        axis=1,
    )
    df["last_evaluated_year"] = (
        df["last_evaluated"].str.extract(r"(\d{4})", expand=False).astype("Int64")
    )
    df["genome_build"] = "GRCh38"
    df["variant_key"] = (
        df["chrom"].astype(str) + ":" + df["pos"].astype(str) + ":" + df["ref"] + ">" + df["alt"]
    )

    # deduplicate exact coordinate duplicates, preferring higher-confidence rows
    before = len(df)
    df = (
        df.sort_values(["confidence_tier", "n_submitters"], ascending=False)
          .drop_duplicates(subset=["variant_key"], keep="first")
    )
    stages["after_coordinate_dedup"] = len(df)
    stages["coordinate_duplicates_removed"] = before - len(df)

    stages["labeled_rows"] = int(df["label"].notna().sum())
    stages["conflicting_rows_preserved_unlabeled"] = int(df["label_conflict"].sum())

    df.to_parquet(OUT, index=False)

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "source_file": str(RAW.name),
        "output": str(OUT.relative_to(REPO)),
        "stages": stages,
        "class_distribution": df["label"].value_counts(dropna=False).to_dict(),
        "confidence_tier_distribution": df["confidence_tier"].value_counts().to_dict(),
        "consequence_distribution": df["consequence_derived"].value_counts().to_dict(),
        "variant_type_distribution": df["variant_type"].value_counts().to_dict(),
        "n_genes": int(df["gene"].nunique()),
        "chromosome_distribution": df["chrom"].value_counts().to_dict(),
        "missingness": {c: int(df[c].isna().sum()) for c in
                        ["label", "gene", "pos", "last_evaluated_year"]},
        "notes": [
            "labels are ClinVar germline aggregate classifications with review-status tiers",
            "conflicting classifications preserved with label=NULL, excluded from training",
            "consequence derived from Name HGVS heuristic until offline VEP is configured",
        ],
    }
    REPORT.write_text(json.dumps(report, indent=2, default=str))
    return report


if __name__ == "__main__":
    r = build()
    print(json.dumps(r["stages"], indent=2))
