# scripts/fetch_clinvar_panel.py
r"""
Pulls real ClinVar pathogenic/likely-pathogenic variants for your recessive
gene panel via NCBI E-utilities (no multi-GB download needed -- this queries
per-gene, not the full ClinVar dump).

Respects NCBI's rate limit (max 3 req/sec without an API key) -- if you have
an NCBI API key, set it below to go faster and more reliably.

IMPORTANT BUG FIX (confirmed via direct raw esummary inspection): earlier
versions of this script read classification/review data from
entry["clinical_significance"], a key that DOES NOT EXIST in ClinVar's
actual esummary response -- the real key is "germline_classification".
Reading a nonexistent key via .get() silently returns {}, so clinsig and
review_status were always empty strings, and EVERY variant's classification
column silently defaulted to "Likely Pathogenic" regardless of what ClinVar
actually reported (see the classification ternary below: an empty clinsig
string always fails the "Pathogenic" check and falls through). This is now
fixed -- classification, review_status, and conditions are all read from
germline_classification's real nested structure.

BONUS: the same trait_set nodes that hold condition names also carry
trait_xrefs -- cross-reference IDs into OMIM, MedGen, and Orphanet, already
present in this same response with no extra API calls. These are now
captured in a "disease_db_xrefs" column, giving a head start on any
ClinVar-to-external-disease-database mapping work.

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
    "SMN1", "MEFV", "ASPA", "GBA1", "G6PD", "BTD",
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


def extract_conditions_and_xrefs(entry: dict) -> tuple[str, str, str, str]:
    """
    IMPORTANT FIX: ClinVar's real esummary structure nests classification data
    under "germline_classification", NOT "clinical_significance" (which does
    not exist in the response at all -- confirmed via direct inspection of a
    raw esummary call). The previous version of this script read
    entry.get("clinical_significance", {}), which silently always returned {},
    meaning clinsig/review_status were always empty strings and EVERY variant
    was mislabeled "Likely Pathogenic" regardless of its real ClinVar status
    (see main()'s classification logic -- an empty clinsig string always
    falls through to the "Likely Pathogenic" branch). This function reads the
    correct location.

    Also extracts real OMIM/MedGen/Orphanet cross-reference IDs from
    "trait_xrefs", which were already present in every response and unused --
    this gives direct disease-database mapping (Options 1/2/4 from the
    condition-mapping plan) with NO additional API calls needed.

    Returns: (clinsig_description, review_status, conditions_str, xrefs_str)
    """
    gc = entry.get("germline_classification", {})
    clinsig = gc.get("description", "")
    review = gc.get("review_status", "")

    trait_set = gc.get("trait_set", [])
    condition_names = []
    xref_parts = []
    seen_names = set()
    seen_xrefs = set()
    for trait in trait_set:
        name = (trait.get("trait_name") or "").strip()
        if name and name not in seen_names:
            seen_names.add(name)
            condition_names.append(name)
        for xref in trait.get("trait_xrefs", []):
            db = xref.get("db_source", "")
            db_id = xref.get("db_id", "")
            if db and db_id:
                tag = f"{db}:{db_id}"
                if tag not in seen_xrefs:
                    seen_xrefs.add(tag)
                    xref_parts.append(tag)

    return clinsig, review, "; ".join(condition_names), "; ".join(xref_parts)


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

        no_condition_count = 0
        for uid, entry in summaries.items():
            if uid == "uids":
                continue
            title = entry.get("title", "")
            clinsig, review, conditions, xrefs = extract_conditions_and_xrefs(entry)
            variant_id = extract_c_notation(title) or title
            # keep only variants with at least some review support -- skip
            # "no assertion criteria provided" to avoid low-confidence noise
            if "no assertion criteria" in review.lower():
                continue
            if not conditions:
                no_condition_count += 1
            rows.append({
                "gene": gene,
                "variant_id": variant_id,
                "classification": "Pathogenic" if "pathogenic" in clinsig.lower()
                                   and "likely" not in clinsig.lower() else "Likely Pathogenic",
                "raw_clinsig": clinsig,
                "review_status": review,
                "title": title,
                "conditions": conditions,
                "disease_db_xrefs": xrefs,
            })
        kept = len([r for r in rows if r['gene'] == gene])
        print(f"  {kept} variant(s) kept"
              + (f" ({no_condition_count} with no resolved condition name)" if no_condition_count else ""))

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=["gene", "variant_id", "classification", "raw_clinsig",
                        "review_status", "title", "conditions", "disease_db_xrefs"],
        )
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nWrote {len(rows)} real ClinVar variants (with condition names) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
