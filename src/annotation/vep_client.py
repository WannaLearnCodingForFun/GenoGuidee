"""
vep_client.py — thin client for Ensembl VEP REST API.

Given a variant (chrom, pos, ref, alt) or an HGVS notation string, fetch
consequence, gene, and existing annotations from VEP.

Docs: https://rest.ensembl.org/documentation/info/vep_hgvs_get
      https://rest.ensembl.org/documentation/info/vep_region_get
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any, Optional

import requests

VEP_BASE = "https://rest.ensembl.org"
DEFAULT_HEADERS = {"Content-Type": "application/json"}
REQUEST_TIMEOUT = 40
MAX_RETRIES = 3
RETRY_BACKOFF_SECS = 1.5


class VEPError(RuntimeError):
    pass


@dataclass
class VEPAnnotation:
    input_variant: str
    gene_symbol: Optional[str] = None
    gene_id: Optional[str] = None
    most_severe_consequence: Optional[str] = None
    transcript_consequences: list[dict[str, Any]] = field(default_factory=list)
    existing_variation: list[str] = field(default_factory=list)  # e.g. rsIDs
    colocated_variants: list[dict[str, Any]] = field(default_factory=list)
    raw: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_vep_json(cls, entry: dict[str, Any]) -> "VEPAnnotation":
        tx_conseqs = entry.get("transcript_consequences", []) or []
        # Prefer the canonical/most-severe transcript for a top-line gene symbol.
        gene_symbol = None
        gene_id = None
        for tx in tx_conseqs:
            if tx.get("canonical") == 1:
                gene_symbol = tx.get("gene_symbol")
                gene_id = tx.get("gene_id")
                break
        if gene_symbol is None and tx_conseqs:
            gene_symbol = tx_conseqs[0].get("gene_symbol")
            gene_id = tx_conseqs[0].get("gene_id")

        return cls(
            input_variant=entry.get("input", ""),
            gene_symbol=gene_symbol,
            gene_id=gene_id,
            most_severe_consequence=entry.get("most_severe_consequence"),
            transcript_consequences=tx_conseqs,
            existing_variation=entry.get("existing_variation", []) or [],
            colocated_variants=entry.get("colocated_variants", []) or [],
            raw=entry,
        )

    def gnomad_af(self) -> Optional[float]:
        """Best-effort extraction of a gnomAD (genomes) allele frequency, if present."""
        for cv in self.colocated_variants:
            for key in ("gnomad_af", "gnomade_af", "gnomadg_af"):
                if key in cv:
                    try:
                        return float(cv[key])
                    except (TypeError, ValueError):
                        continue
        return None


def _request_with_retry(url: str, params: Optional[dict[str, Any]] = None) -> Any:
    last_exc: Optional[Exception] = None
    for attempt in range(1, MAX_RETRIES + 1):
        try:
            resp = requests.get(
                url, headers=DEFAULT_HEADERS, params=params, timeout=REQUEST_TIMEOUT
            )
            if resp.status_code == 429:
                # Honor Retry-After if VEP sends it, else backoff.
                wait = float(resp.headers.get("Retry-After", RETRY_BACKOFF_SECS * attempt))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            last_exc = exc
            time.sleep(RETRY_BACKOFF_SECS * attempt)
    raise VEPError(f"VEP request failed after {MAX_RETRIES} attempts: {last_exc}")


# VEP doesn't return population frequency data by default — these params must
# be explicitly requested or gnomad_af() will almost always come back None.
FREQUENCY_PARAMS = {
    "content-type": "application/json",
    "af_gnomade": 1,
    "af_gnomadg": 1,
    "af": 1,
}


def annotate_hgvs(hgvs_notation: str, species: str = "human") -> VEPAnnotation:
    """
    Annotate a single variant given in HGVS notation, e.g.
    'NM_000492.3:c.1521_1523delCTT' (CFTR delF508) or 'ENST00000003084:c.1431_1433delTTC'.
    """
    url = f"{VEP_BASE}/vep/{species}/hgvs/{hgvs_notation}"
    data = _request_with_retry(url, params=FREQUENCY_PARAMS)
    if not data:
        raise VEPError(f"VEP returned no annotation for {hgvs_notation}")
    return VEPAnnotation.from_vep_json(data[0])


def annotate_region(
    chrom: str, pos: int, ref: str, alt: str, species: str = "human"
) -> VEPAnnotation:
    """
    Annotate a single variant given as chrom/pos/ref/alt (VCF-style, 1-based).
    Builds the region string VEP expects: "chrom start end allele strand".
    For a SNV, start == end == pos.
    """
    end = pos + len(ref) - 1
    region = f"{chrom}:{pos}-{end}"
    allele_string = f"{ref}/{alt}"
    url = f"{VEP_BASE}/vep/{species}/region/{region}/{allele_string}"
    data = _request_with_retry(url, params=FREQUENCY_PARAMS)
    if not data:
        raise VEPError(f"VEP returned no annotation for {chrom}:{pos} {ref}>{alt}")
    return VEPAnnotation.from_vep_json(data[0])


def annotate_batch(variants: list[str], species: str = "human") -> list[VEPAnnotation]:
    """
    Batch-annotate multiple HGVS notations in one POST call (VEP supports up to 200/request).
    Falls back to per-variant GET calls on failure so one bad variant doesn't kill the batch.
    """
    url = f"{VEP_BASE}/vep/{species}/hgvs"
    try:
        resp = requests.post(
            url,
            headers=DEFAULT_HEADERS,
            json={"hgvs_notations": variants},
            timeout=REQUEST_TIMEOUT * 2,
        )
        resp.raise_for_status()
        return [VEPAnnotation.from_vep_json(entry) for entry in resp.json()]
    except requests.RequestException:
        results = []
        for v in variants:
            try:
                results.append(annotate_hgvs(v, species=species))
            except VEPError:
                continue
        return results


if __name__ == "__main__":
    # Sanity check with a well-characterized pathogenic CFTR variant (delta-F508),
    # per the guide's instruction to validate VEP end-to-end before building on top.
    test_variant = "ENST00000003084:c.1521_1523delCTT"
    print(f"Querying VEP for {test_variant} ...")
    try:
        ann = annotate_hgvs(test_variant)
        print(f"  gene: {ann.gene_symbol} ({ann.gene_id})")
        print(f"  most_severe_consequence: {ann.most_severe_consequence}")
        print(f"  existing_variation: {ann.existing_variation}")
        print(f"  gnomAD AF: {ann.gnomad_af()}")
        print(f"  # transcript_consequences: {len(ann.transcript_consequences)}")
    except VEPError as e:
        print(f"  FAILED: {e}")
