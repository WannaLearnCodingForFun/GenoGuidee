"""
gnomad_client.py — direct gnomAD GraphQL API fallback for population allele
frequency, used when VEP's colocated_variants doesn't carry a gnomAD AF for
a given variant (common — VEP's frequency annotation coverage isn't complete
even with af_gnomad params requested).

Free, no auth, no download needed — per the guide's suggestion to query
gnomAD live rather than download the full dataset.

API docs: https://gnomad.broadinstitute.org/api
"""

from __future__ import annotations

from typing import Optional

import requests

GNOMAD_API = "https://gnomad.broadinstitute.org/api"
REQUEST_TIMEOUT = 15

# gnomAD variant IDs use the format "chrom-pos-ref-alt", chrom without "chr" prefix
_QUERY = """
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


def _normalize_chrom(chrom: str) -> str:
    return chrom[3:] if chrom.lower().startswith("chr") else chrom


def fetch_gnomad_af(
    chrom: str, pos: int, ref: str, alt: str, dataset: str = "gnomad_r4"
) -> Optional[float]:
    """
    Query gnomAD directly for a variant's population allele frequency.
    Prefers genome AF, falls back to exome AF. Returns None if the variant
    isn't found in gnomAD at all (e.g. never observed in any sequenced sample).
    """
    variant_id = f"{_normalize_chrom(chrom)}-{pos}-{ref}-{alt}"
    try:
        resp = requests.post(
            GNOMAD_API,
            json={"query": _QUERY, "variables": {"variantId": variant_id, "dataset": dataset}},
            timeout=REQUEST_TIMEOUT,
        )
        resp.raise_for_status()
        payload = resp.json()
    except requests.RequestException:
        return None

    variant_data = (payload.get("data") or {}).get("variant")
    if not variant_data:
        return None

    genome = variant_data.get("genome")
    if genome and genome.get("af") is not None:
        return float(genome["af"])

    exome = variant_data.get("exome")
    if exome and exome.get("af") is not None:
        return float(exome["af"])

    return None


if __name__ == "__main__":
    # Smoke test with a variant likely to have gnomAD coverage.
    test = fetch_gnomad_af("chr7", 117559590, "G", "A")
    print(f"gnomAD AF for chr7:117559590 G>A: {test}")
