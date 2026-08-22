"""
Functional prediction score connectors (feature_group='functional').

Each connector has an explicit availability state — SOURCE_NOT_CONFIGURED
until its data is present. Nothing is imputed silently; missingness is
returned as None and handled downstream with explicit missing-indicators.

AlphaMissense: public precomputed predictions (CC BY-NC-SA 4.0). We did NOT
train AlphaMissense; it is used strictly as an external feature/baseline/
ablation comparator. The raw 71M-row TSV is converted once into a
chromosome-partitioned parquet store for fast indexed lookups via DuckDB.

REVEL / SpliceAI / CADD: connectors implemented; data must be fetched per
manifest instructions (registration/size constraints). State is reported
honestly through `availability()`.
"""
from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import duckdb

REPO = Path(__file__).resolve().parents[2]
AM_RAW = REPO / "research/data/raw/alphamissense/AlphaMissense_hg38.tsv.gz"
AM_STORE = REPO / "research/data/interim/alphamissense_hg38.parquet"
REVEL_DIR = REPO / "research/data/raw/revel"
SPLICEAI_DIR = REPO / "research/data/raw/spliceai"
CADD_DIR = REPO / "research/data/raw/cadd"


# ---------------------------------------------------------------------------
# AlphaMissense
# ---------------------------------------------------------------------------

def alphamissense_available() -> str:
    if AM_STORE.exists():
        return "AVAILABLE"
    if AM_RAW.exists():
        return "RAW_PRESENT_NEEDS_CONVERSION"
    return "SOURCE_NOT_CONFIGURED"


def convert_alphamissense() -> dict[str, Any]:
    """One-time conversion: gzipped TSV → parquet (sorted by chrom,pos)."""
    if not AM_RAW.exists():
        raise FileNotFoundError(
            "AlphaMissense raw file missing — run: data download alphamissense_hg38")
    AM_STORE.parent.mkdir(parents=True, exist_ok=True)
    con = duckdb.connect()
    con.execute("SET threads TO 4; SET memory_limit='6GB'")
    con.execute(f"""
        COPY (
            SELECT "#CHROM" AS chrom, CAST(POS AS BIGINT) AS pos,
                   REF AS ref, ALT AS alt, genome,
                   uniprot_id, transcript_id, protein_variant,
                   CAST(am_pathogenicity AS DOUBLE) AS am_pathogenicity,
                   am_class
            FROM read_csv('{AM_RAW}', delim='\t', header=true, skip=3,
                          all_varchar=true, ignore_errors=true)
            ORDER BY chrom, pos
        ) TO '{AM_STORE}' (FORMAT PARQUET, ROW_GROUP_SIZE 500000)
    """)
    n = con.sql(f"SELECT COUNT(*) FROM '{AM_STORE}'").fetchone()[0]
    info = {
        "rows": n,
        "store": str(AM_STORE.relative_to(REPO)),
        "converted": datetime.now(timezone.utc).isoformat(),
        "license": "CC BY-NC-SA 4.0 (non-commercial)",
    }
    (AM_STORE.parent / "alphamissense_store_info.json").write_text(json.dumps(info, indent=2))
    return info


class AlphaMissenseStore:
    def __init__(self) -> None:
        self._con = None

    @property
    def state(self) -> str:
        return alphamissense_available()

    def _connection(self):
        if self._con is None:
            self._con = duckdb.connect()
        return self._con

    def lookup(self, chrom: str, pos: int, ref: str, alt: str) -> Optional[dict[str, Any]]:
        if self.state != "AVAILABLE":
            return None
        chrom_str = f"chr{chrom}" if not str(chrom).startswith("chr") else str(chrom)
        row = self._connection().execute(
            f"SELECT am_pathogenicity, am_class, transcript_id, protein_variant "
            f"FROM '{AM_STORE}' WHERE chrom=? AND pos=? AND ref=? AND alt=? LIMIT 1",
            [chrom_str, pos, ref, alt],
        ).fetchone()
        if row is None:
            return None
        return {
            "am_pathogenicity": row[0],
            "am_class": row[1],
            "transcript_id": row[2],
            "protein_variant": row[3],
            "source": "AlphaMissense (precomputed, CC BY-NC-SA 4.0)",
        }

    def batch_join_sql(self) -> str:
        """SQL fragment used by the training feature builder for a bulk join."""
        return str(AM_STORE)


# ---------------------------------------------------------------------------
# REVEL / SpliceAI / CADD — connectors with explicit availability
# ---------------------------------------------------------------------------

def revel_available() -> str:
    if REVEL_DIR.exists() and (any(REVEL_DIR.glob("*.csv*")) or any(REVEL_DIR.glob("*.zip"))):
        return "RAW_PRESENT_NEEDS_CONVERSION"
    return "SOURCE_NOT_CONFIGURED"


def spliceai_available() -> str:
    if SPLICEAI_DIR.exists() and any(SPLICEAI_DIR.glob("spliceai_scores*.vcf.gz")):
        return "RAW_PRESENT_NEEDS_CONVERSION"
    return "SOURCE_NOT_CONFIGURED"


def cadd_available() -> str:
    if CADD_DIR.exists() and any(CADD_DIR.glob("*.tsv.gz")):
        return "RAW_PRESENT_NEEDS_CONVERSION"
    return "SOURCE_NOT_CONFIGURED"


def availability() -> dict[str, str]:
    return {
        "alphamissense": alphamissense_available(),
        "revel": revel_available(),
        "spliceai": spliceai_available(),
        "cadd": cadd_available(),
        "gnomad_sites": "SOURCE_NOT_CONFIGURED",  # TB-scale; see manifest notes
    }


if __name__ == "__main__":
    state = alphamissense_available()
    print("alphamissense:", state)
    if state == "RAW_PRESENT_NEEDS_CONVERSION":
        print(json.dumps(convert_alphamissense(), indent=2))
    print(json.dumps(availability(), indent=2))
