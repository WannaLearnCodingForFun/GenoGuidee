"""
Population allele frequencies from the ClinVar GRCh38 VCF INFO fields.

ClinVar's VCF carries AF_EXAC / AF_TGP (1000 Genomes) / AF_ESP annotations.
These are REAL population frequencies but from LEGACY cohorts (ExAC n≈60k,
1000G, ESP) — not gnomAD v4. This is recorded as the source everywhere.
gnomAD v4 per-variant AF remains a separate connector (TB-scale; manifest).

Output: research/data/processed/population_af.parquet
        (chrom, pos, ref, alt, af_exac, af_tgp, af_esp, af_max, log10_af)
"""
from __future__ import annotations

import gzip
import json
import math
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
VCF = REPO / "research/data/raw/clinvar/clinvar_grch38.vcf.gz"
OUT = REPO / "research/data/processed/population_af.parquet"
REPORT = REPO / "research/reports/population_af_report.json"

POPULATION_SOURCE = "ExAC/1000G/ESP allele frequencies via ClinVar VCF (legacy cohorts, not gnomAD v4)"


def build() -> dict:
    if not VCF.exists():
        raise FileNotFoundError("run: python -m cli.genoguide data download clinvar_vcf_grch38")
    rows = []
    n_records = 0
    with gzip.open(VCF, "rt") as f:
        for line in f:
            if line.startswith("#"):
                continue
            n_records += 1
            fields = line.rstrip("\n").split("\t")
            info = fields[7]
            if "AF_" not in info:
                continue
            kv = dict(p.split("=", 1) for p in info.split(";") if "=" in p)
            def fget(key):
                try:
                    return float(kv[key]) if key in kv else None
                except ValueError:
                    return None
            af_exac, af_tgp, af_esp = fget("AF_EXAC"), fget("AF_TGP"), fget("AF_ESP")
            if af_exac is None and af_tgp is None and af_esp is None:
                continue
            af_max = max(x for x in (af_exac, af_tgp, af_esp) if x is not None)
            rows.append((fields[0], int(fields[1]), fields[3], fields[4],
                         af_exac, af_tgp, af_esp, af_max,
                         math.log10(af_max) if af_max > 0 else None))
    df = pd.DataFrame(rows, columns=["chrom", "pos", "ref", "alt",
                                     "af_exac", "af_tgp", "af_esp", "af_max", "log10_af"])
    OUT.parent.mkdir(parents=True, exist_ok=True)
    df.to_parquet(OUT, index=False)
    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "source": POPULATION_SOURCE,
        "vcf_records_scanned": n_records,
        "variants_with_af": len(df),
        "af_distribution": {
            "common_gt_5pct": int((df["af_max"] > 0.05).sum()),
            "rare_lt_1e4": int((df["af_max"] < 1e-4).sum()),
        },
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2))
    return report


if __name__ == "__main__":
    print(json.dumps(build(), indent=2))
