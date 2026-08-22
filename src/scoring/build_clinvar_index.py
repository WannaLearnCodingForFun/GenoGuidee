"""
build_clinvar_index.py — filter and load ClinVar's variant_summary.txt.gz
into a queryable DuckDB table.

Source file: https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz
(~250MB compressed, contains both GRCh37 and GRCh38 rows for every submitted variant)

What this does:
  1. Streams the gzip file directly into DuckDB (no need to fully unzip to disk first)
  2. Filters to Assembly == 'GRCh38' (matches VEP's default / our pipeline)
  3. Filters to ReviewStatus with >=2 gold stars (clean, reliable labels) —
     'criteria provided, multiple submitters, no conflicts',
     'reviewed by expert panel', 'practice guideline'
  4. Saves the filtered result into data/processed/clinvar.duckdb for fast querying
     by xgb_classifier.py (training) and build_index.py (RAG chunking) later.

Usage:
    python -m src.scoring.build_clinvar_index
    (expects data/raw/variant_summary.txt.gz to already exist)
"""

from __future__ import annotations

from pathlib import Path

import duckdb

RAW_PATH = "data/raw/variant_summary.txt.gz"
DB_PATH = "data/processed/clinvar.duckdb"
TABLE_NAME = "clinvar_variants"

# 2+ star review statuses, per ClinVar's own star-rating scheme.
# https://www.ncbi.nlm.nih.gov/clinvar/docs/review_status/
TWO_STAR_PLUS_STATUSES = [
    "criteria provided, multiple submitters, no conflicts",
    "reviewed by expert panel",
    "practice guideline",
]


def build_clinvar_index(
    raw_path: str = RAW_PATH,
    db_path: str = DB_PATH,
    assembly: str = "GRCh38",
) -> str:
    if not Path(raw_path).exists():
        raise FileNotFoundError(
            f"{raw_path} not found — download it first:\n"
            "  https://ftp.ncbi.nlm.nih.gov/pub/clinvar/tab_delimited/variant_summary.txt.gz"
        )

    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)

    status_list = ", ".join(f"'{s}'" for s in TWO_STAR_PLUS_STATUSES)

    print(f"Reading {raw_path} (this streams, doesn't load fully into memory)...")
    con.execute(f"""
        CREATE OR REPLACE TABLE {TABLE_NAME} AS
        SELECT
            "#AlleleID"        AS allele_id,
            "Type"             AS variant_type,
            "Name"             AS name,
            "GeneSymbol"       AS gene_symbol,
            "ClinicalSignificance" AS clinical_significance,
            "ReviewStatus"     AS review_status,
            "Chromosome"       AS chrom,
            "Start"            AS pos,
            "ReferenceAllele"  AS ref,
            "AlternateAllele"  AS alt,
            "Assembly"         AS assembly,
            "PhenotypeList"    AS phenotype_list,
            "OriginSimple"     AS origin
        FROM read_csv_auto(?, delim='\t', header=true, ignore_errors=true)
        WHERE "Assembly" = ?
          AND "ReviewStatus" IN ({status_list})
    """, [raw_path, assembly])

    con.execute(f"CREATE INDEX IF NOT EXISTS idx_gene ON {TABLE_NAME} (gene_symbol)")
    con.execute(f"CREATE INDEX IF NOT EXISTS idx_variant_key ON {TABLE_NAME} (chrom, pos, ref, alt)")

    total = con.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}").fetchone()[0]
    by_sig = con.execute(f"""
        SELECT clinical_significance, COUNT(*) AS n
        FROM {TABLE_NAME}
        GROUP BY clinical_significance
        ORDER BY n DESC
        LIMIT 10
    """).fetchall()

    con.close()

    print(f"\nLoaded {total:,} filtered (GRCh38, 2+ star) ClinVar variants into {db_path}")
    print("\nTop clinical significance categories:")
    for sig, n in by_sig:
        print(f"  {n:>8,}  {sig}")

    return db_path


if __name__ == "__main__":
    build_clinvar_index()
