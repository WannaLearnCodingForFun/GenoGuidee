# scripts/fetch_clinvar_panel.py
r"""
Pulls real ClinVar pathogenic/likely-pathogenic variants for your recessive
gene panel via NCBI E-utilities (no multi-GB download needed -- this queries
per-gene, not the full ClinVar dump).

Respects NCBI's rate limit (max 3 req/sec without an API key) -- if you have
an NCBI API key, set it below to go faster and more reliably.

Usage:
    python scripts/fetch_clinvar_panel.py
Output:
    data/knowledge/clinvar_panel.csv
"""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path

import requests

EUTILS = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
API_KEY = None  # optional: paste your NCBI API key here to raise rate limit to 10/sec
TOOL = "genochain"
EMAIL = "smerarawal@gmail.com"  # NCBI asks you to identify yourself -- fill this in

PANEL_GENES = [
    "CFTR", "HBB", "GJB2", "HEXA", "PAH", "ATP7B",
    "SMN1", "MEFV", "ASPA", "GBA", "G6PD", "BTD",
]

OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "clinvar_panel.csv"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

RATE_DELAY = 0.11 if API_KEY else 0.35  # stay under NCBI's per-second cap


def _params(extra: dict) -> dict:
    p = {"tool": TOOL, "email": EMAIL, "retmode": "json"}
    if API_KEY:
        p["api_key"] = API_KEY
    p.update(extra)
    return p


def esearch_gene(gene: str) -> list[str]:
    """Returns ClinVar UIDs for pathogenic/likely-pathogenic variants in this gene."""
    term = (
        f'{gene}[gene] AND '
        f'("clinsig pathogenic"[Properties] OR "clinsig likely pathogenic"[Properties])'
    )
    resp = requests.get(
        f"{EUTILS}/esearch.fcgi",
        params=_params({"db": "clinvar", "term": term, "retmax": 50}),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["esearchresult"].get("idlist", [])


def esummary_batch(uids: list[str]) -> dict:
    if not uids:
        return {}
    resp = requests.get(
        f"{EUTILS}/esummary.fcgi",
        params=_params({"db": "clinvar", "id": ",".join(uids)}),
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json().get("result", {})


_HGVS_C_RE = re.compile(r":(c\.[^\s(]+)")


def extract_c_notation(title: str) -> str | None:
    """e.g. 'NM_000492.4(CFTR):c.1521_1523delCTT (p.Phe508del)' -> 'c.1521_1523delCTT'"""
    m = _HGVS_C_RE.search(title)
    return m.group(1) if m else None


def main():
    rows = []
    for gene in PANEL_GENES:
        print(f"Querying ClinVar for {gene} ...")
        try:
            uids = esearch_gene(gene)
            time.sleep(RATE_DELAY)
            if not uids:
                print(f"  no hits for {gene}")
                continue
            summaries = esummary_batch(uids)
            time.sleep(RATE_DELAY)
        except requests.RequestException as e:
            print(f"  FAILED for {gene}: {e}", file=sys.stderr)
            continue

        for uid, entry in summaries.items():
            if uid == "uids":
                continue
            title = entry.get("title", "")
            clinsig = entry.get("clinical_significance", {}).get("description", "")
            review = entry.get("clinical_significance", {}).get("review_status", "")
            variant_id = extract_c_notation(title) or title
            # keep only variants with at least some review support -- skip
            # "no assertion criteria provided" to avoid low-confidence noise
            if "no assertion criteria" in review.lower():
                continue
            rows.append({
                "gene": gene,
                "variant_id": variant_id,
                "classification": "Pathogenic" if "pathogenic" in clinsig.lower()
                                   and "likely" not in clinsig.lower() else "Likely Pathogenic",
                "raw_clinsig": clinsig,
                "review_status": review,
                "title": title,
            })
        print(f"  {len([r for r in rows if r['gene'] == gene])} variant(s) kept")

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["gene", "variant_id", "classification", "raw_clinsig", "review_status", "title"])
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} real ClinVar variants -> {OUT_PATH}")


if __name__ == "__main__":
    main()