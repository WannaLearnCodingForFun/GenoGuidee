"""
Duplicate & leakage audit (section 22).

Checks across train/test of every split:
    * exact duplicate variant_key (coordinate identity)
    * same ClinVar VariationID
    * same gene + protein change (parsed from ClinVar Name p. notation)

Severity policy (enforced by training):
    SEVERE   exact-coordinate or VariationID overlap > 0
    WARNING  gene+protein-change overlap fraction > 0.5% of test
    OK       otherwise

Outputs research/reports/leakage_report.json + .html.
Training MUST call `assert_no_severe_leakage` and fail on SEVERE.
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

REPO = Path(__file__).resolve().parents[2]
REPORT = REPO / "research/reports/leakage_report.json"

_P_CHANGE = re.compile(r"\((p\.[A-Za-z0-9=*?]+)\)")


class SevereLeakageError(RuntimeError):
    pass


def protein_change_key(df: pd.DataFrame) -> pd.Series:
    pc = df["meta_name"].fillna("").str.extract(_P_CHANGE, expand=False)
    key = df["gene"].fillna("") + "|" + pc.fillna("")
    key[pc.isna() | (df["gene"].isna())] = None
    return key


def audit_split(df: pd.DataFrame, split: dict) -> dict:
    tr, te = split["train"], split["test"]
    d_tr, d_te = df.iloc[tr], df.iloc[te]

    coord_overlap = len(set(d_tr["variant_key"]) & set(d_te["variant_key"]))
    vid_overlap = len(set(d_tr["meta_variation_id"]) & set(d_te["meta_variation_id"]))

    pk_tr = set(protein_change_key(d_tr).dropna())
    pk_te = protein_change_key(d_te).dropna()
    prot_overlap = int(pk_te.isin(pk_tr).sum())
    prot_frac = prot_overlap / max(len(d_te), 1)

    if coord_overlap or vid_overlap:
        severity = "SEVERE"
    elif prot_frac > 0.005:
        severity = "WARNING"
    else:
        severity = "OK"

    return {
        "strategy": split["meta"]["strategy"],
        "n_train": len(tr), "n_test": len(te),
        "exact_coordinate_overlap": coord_overlap,
        "variation_id_overlap": vid_overlap,
        "gene_protein_change_overlap": prot_overlap,
        "gene_protein_change_overlap_fraction": round(prot_frac, 5),
        "severity": severity,
        "note": ("gene+protein-change overlap across DIFFERENT genomic variants "
                 "is expected in random/temporal splits and is exactly why "
                 "gene-disjoint evaluation is the headline benchmark"),
    }


def run_audit(df: pd.DataFrame, splits: dict[str, dict]) -> dict:
    results = {name: audit_split(df, s) for name, s in splits.items()}
    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "n_rows": len(df),
        "splits": results,
        "policy": {"SEVERE": "training refuses to run",
                   "WARNING": "reported; gene-disjoint split unaffected"},
    }
    REPORT.parent.mkdir(parents=True, exist_ok=True)
    REPORT.write_text(json.dumps(report, indent=2))

    rows = "".join(
        f"<tr><td>{n}</td><td>{r['exact_coordinate_overlap']}</td>"
        f"<td>{r['variation_id_overlap']}</td>"
        f"<td>{r['gene_protein_change_overlap']} ({r['gene_protein_change_overlap_fraction']:.3%})</td>"
        f"<td><b>{r['severity']}</b></td></tr>"
        for n, r in results.items())
    REPORT.with_suffix(".html").write_text(
        "<html><body><h1>GenoGuide leakage audit</h1>"
        f"<p>{report['generated']} — {len(df):,} rows</p>"
        "<table border=1 cellpadding=6><tr><th>split</th><th>coord overlap</th>"
        "<th>VariationID overlap</th><th>gene+protein overlap</th><th>severity</th></tr>"
        f"{rows}</table></body></html>")
    return report


def assert_no_severe_leakage(df: pd.DataFrame, split: dict) -> dict:
    result = audit_split(df, split)
    if result["severity"] == "SEVERE":
        raise SevereLeakageError(
            f"SEVERE leakage in split {result['strategy']}: "
            f"coord={result['exact_coordinate_overlap']} vid={result['variation_id_overlap']}")
    return result
