"""
gnomad_client.py — direct gnomAD GraphQL API client.

fetch_gnomad_af(): overall population AF (original behavior, unchanged).
fetch_gnomad_population_af(): per-ancestry AF breakdown, for building
    synthetic multi-ancestral cohorts (Option B).

Free, no auth, no download needed.
API docs: https://gnomad.broadinstitute.org/api
"""

from __future__ import annotations

from typing import Optional

import requests

GNOMAD_API = "https://gnomad.broadinstitute.org/api"
REQUEST_TIMEOUT = 15

# gnomAD v4 population codes (genomes). See:
# https://gnomad.broadinstitute.org/help/what-populations-are-represented-in-the-gnomad-data
POPULATION_LABELS = {
    "afr": "African/African American",
    "amr": "Admixed American",
    "asj": "Ashkenazi Jewish",
    "eas": "East Asian",
    "fin": "Finnish",
    "mid": "Middle Eastern",
    "nfe": "Non-Finnish European",
    "sas": "South Asian",
    "remaining": "Remaining/Other",
}

_QUERY_OVERALL = """
query VariantFrequency($variantId: String!, $dataset: DatasetId!) {
  variant(variantId: $variantId, dataset: $dataset) {
    variant_id
    genome {
      af
      ac
      an
    }
    exome {
      af
      ac
      an
    }
  }
}
"""

_QUERY_BY_POPULATION = """
query VariantFrequencyByPopulation($variantId: String!, $dataset: DatasetId!) {
  variant(variantId: $variantId, dataset: $dataset) {
    variant_id
    genome {
      af
      ac
      an
      populations {
        id
        ac
        an
      }
    }
    exome {
      af
      ac
      an
      populations {
        id
        ac
        an
      }
    }
  }
}
"""


def _normalize_chrom(chrom: str) -> str:
    return chrom[3:] if chrom.lower().startswith("chr") else chrom


def _post(query: str, variant_id: str, dataset: str) -> Optional[dict]:
    try:
        resp = requests.post(
            GNOMAD_API,
            json={"query": query, "variables": {"variantId": variant_id, "dataset": dataset}},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException:
        return None
    return (payload.get("data") or {}).get("variant")


def fetch_gnomad_af(
    chrom: str, pos: int, ref: str, alt: str, dataset: str = "gnomad_r4"
) -> Optional[float]:
    """Overall population AF. Prefers genome AF, falls back to exome AF.
    Returns None if the variant isn't found in gnomAD at all."""
    variant_id = f"{_normalize_chrom(chrom)}-{pos}-{ref}-{alt}"
    variant_data = _post(_QUERY_OVERALL, variant_id, dataset)
    if not variant_data:
        return None

    genome = variant_data.get("genome")
    if genome and genome.get("af") is not None:
        return float(genome["af"])

    exome = variant_data.get("exome")
    if exome and exome.get("af") is not None:
        return float(exome["af"])

    return None


def fetch_gnomad_population_af(
    chrom: str, pos: int, ref: str, alt: str, dataset: str = "gnomad_r4"
) -> Optional[dict]:
    """
    Per-ancestry AF breakdown for a variant. Returns a dict like:
        {"afr": 0.0012, "eas": 0.0, "nfe": 0.031, "sas": 0.0045, ...}
    Prefers genome populations, falls back to exome populations if genome
    has no population breakdown. Returns None if the variant isn't found.

    Use this to seed synthetic multi-ancestral cohorts: sample carrier
    status per synthetic individual using Hardy-Weinberg (q^2 for
    homozygous, 2pq for heterozygous/carrier) with population-specific
    allele frequency q, rather than one flat overall AF for everyone.
    """
    variant_id = f"{_normalize_chrom(chrom)}-{pos}-{ref}-{alt}"
    variant_data = _post(_QUERY_BY_POPULATION, variant_id, dataset)
    if not variant_data:
        return None

    def extract(block):
        if not block or not block.get("populations"):
            return None
        out = {}
        for pop in block["populations"]:
            pid = pop.get("id")
            ac = pop.get("ac")
            an = pop.get("an")
            # gnomAD's VariantPopulation type exposes ac/an, not af directly
            # — compute it ourselves. gnomAD returns both top-level pop
            # codes (e.g. "afr") and sex-stratified subgroups (e.g.
            # "afr_XX", "afr_XY") in the same list — keep only the
            # top-level codes we care about.
            if pid in POPULATION_LABELS and ac is not None and an:
                out[pid] = ac / an
        return out or None

    result = extract(variant_data.get("genome"))
    if result:
        return result
    return extract(variant_data.get("exome"))


if __name__ == "__main__":
    # Smoke test with a variant confirmed present in gnomAD r4 (pulled via
    # a live gene query against CFTR, not guessed).
    overall = fetch_gnomad_af("chr7", 117480021, "C", "A")
    print(f"Overall AF for chr7:117480021 C>A: {overall}")

    by_pop = fetch_gnomad_population_af("chr7", 117480021, "C", "A")
    print(f"By-population AF for chr7:117480021 C>A: {by_pop}")
