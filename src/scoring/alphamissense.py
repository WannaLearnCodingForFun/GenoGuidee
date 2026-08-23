"""
alphamissense.py — lookup AlphaMissense pathogenicity scores for variants.

AlphaMissense publishes precomputed hg38 scores as gzipped TSVs, one row per
missense substitution:
  CHROM  POS  REF  ALT  genome  uniprot_id  transcript_id  protein_variant
  am_pathogenicity  am_class

Source: https://github.com/google-deepmind/alphamissense (Zenodo link in README)

Practical note (per the guide): don't download the whole ~600MB-2.5GB file.
Download only the chromosome(s) your demo variants are on. The per-chromosome
files are named like:
  AlphaMissense_hg38.tsv.gz          (all chromosomes, huge)
Since AlphaMissense doesn't ship pre-split per-chromosome files, the practical
approach is: download the full file once, then use `filter_to_chromosome()``
below to slice out just the chromosome(s) you need and discard the rest —
or use `zgrep '^chr7\t'` on the command line before ever loading it in Python.

This module builds a local DuckDB table from whatever TSV subset you have on
disk, indexed by (chrom, pos, ref, alt), and queries it directly — no need to
load the whole thing into a pandas DataFrame in memory.

BUG FIX (confirmed via real run): AlphaMissense's raw file has one or more
metadata/description comment lines starting with "#" BEFORE the real column
header line (which also starts with "#CHROM..."). The previous version of
filter_to_chromosome() treated the FIRST "#"-prefixed line it saw as the
header -- if that first line was a metadata comment rather than the real
header, the real header got silently dropped, and the first actual DATA row
was written as if it were the header instead. This surfaced downstream as
DuckDB creating a column literally named after a chromosome value (e.g.
"chr1") instead of "CHROM", causing build_index() to fail with a
BinderException. Fixed: only a "#"-line whose stripped content starts with
"CHROM" (case-insensitive) is treated as the header; any other comment line
is skipped entirely, not mistaken for the header.
"""

from __future__ import annotations

import gzip
import shutil
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import duckdb

DEFAULT_DB_PATH = "data/processed/alphamissense.duckdb"
TABLE_NAME = "alphamissense_scores"

EXPECTED_COLUMNS = [
    "CHROM", "POS", "REF", "ALT", "genome",
    "uniprot_id", "transcript_id", "protein_variant",
    "am_pathogenicity", "am_class",
]


@dataclass
class AlphaMissenseScore:
    chrom: str
    pos: int
    ref: str
    alt: str
    transcript_id: str
    protein_variant: str
    am_pathogenicity: float   # 0-1, higher = more likely pathogenic
    am_class: str             # "likely_benign" | "ambiguous" | "likely_pathogenic"


def filter_to_chromosome(raw_tsv_gz: str, chrom: str, out_tsv: str) -> str:
    """
    Slice a single chromosome out of the full AlphaMissense_hg38.tsv.gz without
    loading it all into memory. `chrom` should match the file's own format,
    e.g. 'chr7' (check the first few data rows if unsure).
    Returns the output path.

    Only the real column-header line (starts with "#CHROM", case-insensitive
    after stripping "#") is captured as the header. Any other "#"-prefixed
    metadata/description line is skipped -- see module docstring for why
    this matters (a previous version mistook the first comment line for the
    header and silently dropped the real one).
    """
    raw_path = Path(raw_tsv_gz)
    out_path = Path(out_tsv)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    with gzip.open(raw_path, "rt") as fin, open(out_path, "w") as fout:
        header_written = False
        for line in fin:
            if line.startswith("#"):
                stripped = line.lstrip("#")
                if not header_written and stripped.upper().startswith("CHROM"):
                    fout.write(stripped)
                    header_written = True
                continue  # any other '#' line (metadata/description) is skipped, not written
            if line.startswith(f"{chrom}\t"):
                fout.write(line)

    return str(out_path)


def build_index(
    tsv_paths: list[str],
    db_path: str = DEFAULT_DB_PATH,
    replace: bool = True,
) -> str:
    """
    Load one or more (already-filtered, small) AlphaMissense TSVs into a
    DuckDB table indexed for fast (chrom, pos, ref, alt) lookup.
    """
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect(db_path)

    for i, path in enumerate(tsv_paths):
        if not Path(path).exists():
            raise FileNotFoundError(f"AlphaMissense TSV not found: {path}")
        if i == 0 and replace:
            con.execute(f"""
                CREATE OR REPLACE TABLE {TABLE_NAME} AS
                SELECT * FROM read_csv_auto(?, delim='\t', header=true)
            """, [path])
        else:
            con.execute(f"""
                INSERT INTO {TABLE_NAME}
                SELECT * FROM read_csv_auto(?, delim='\t', header=true)
            """, [path])

    con.execute(f"""
        CREATE INDEX IF NOT EXISTS idx_variant_key
        ON {TABLE_NAME} (CHROM, POS, REF, ALT)
    """)
    con.close()
    return db_path


def lookup(
    chrom: str, pos: int, ref: str, alt: str, db_path: str = DEFAULT_DB_PATH
) -> Optional[AlphaMissenseScore]:
    """
    Query a single variant's AlphaMissense score from the DuckDB index.
    Returns None if not found (e.g. non-missense variant — AlphaMissense
    only scores missense substitutions, not indels/nonsense/synonymous).
    """
    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"No AlphaMissense index at {db_path} — run build_index() first."
        )
    con = duckdb.connect(db_path, read_only=True)
    row = con.execute(f"""
        SELECT CHROM, POS, REF, ALT, transcript_id, protein_variant,
               am_pathogenicity, am_class
        FROM {TABLE_NAME}
        WHERE CHROM = ? AND POS = ? AND REF = ? AND ALT = ?
        LIMIT 1
    """, [chrom, pos, ref, alt]).fetchone()
    con.close()

    if row is None:
        return None

    return AlphaMissenseScore(
        chrom=row[0], pos=row[1], ref=row[2], alt=row[3],
        transcript_id=row[4], protein_variant=row[5],
        am_pathogenicity=float(row[6]), am_class=row[7],
    )


def lookup_batch(
    variants: list[tuple[str, int, str, str]], db_path: str = DEFAULT_DB_PATH
) -> dict[tuple[str, int, str, str], Optional[AlphaMissenseScore]]:
    """Look up several variants in one connection (faster than repeated lookup())."""
    if not Path(db_path).exists():
        raise FileNotFoundError(
            f"No AlphaMissense index at {db_path} — run build_index() first."
        )
    con = duckdb.connect(db_path, read_only=True)
    results: dict[tuple[str, int, str, str], Optional[AlphaMissenseScore]] = {}
    for chrom, pos, ref, alt in variants:
        row = con.execute(f"""
            SELECT CHROM, POS, REF, ALT, transcript_id, protein_variant,
                   am_pathogenicity, am_class
            FROM {TABLE_NAME}
            WHERE CHROM = ? AND POS = ? AND REF = ? AND ALT = ?
            LIMIT 1
        """, [chrom, pos, ref, alt]).fetchone()
        key = (chrom, pos, ref, alt)
        results[key] = None if row is None else AlphaMissenseScore(
            chrom=row[0], pos=row[1], ref=row[2], alt=row[3],
            transcript_id=row[4], protein_variant=row[5],
            am_pathogenicity=float(row[6]), am_class=row[7],
        )
    con.close()
    return results


if __name__ == "__main__":
    import sys

    print(__doc__)
    print(
        "\nThis module needs a local AlphaMissense TSV before it can run.\n"
        "Steps:\n"
        "  1. Download AlphaMissense_hg38.tsv.gz from the Zenodo link in\n"
        "     https://github.com/google-deepmind/alphamissense\n"
        "  2. filter_to_chromosome('AlphaMissense_hg38.tsv.gz', 'chr7',\n"
        "                          'data/raw/alphamissense_chr7.tsv')\n"
        "  3. build_index(['data/raw/alphamissense_chr7.tsv'])\n"
        "  4. lookup('chr7', 117559590, 'C', 'T')   # example call, use your own variant\n"
    )
    sys.exit(0)
