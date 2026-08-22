"""
Definitive live check for which version suffix actually exists RIGHT NOW
on the EBI server, for chromosomes where secondhand sources disagree.

Multiple 2015-era scripts/mirrors all say v5a for chr11/12/13 -- but a
live request against these exact URLs returned 404 earlier this session.
Rather than guess a third time, this issues a lightweight HEAD request
(no data download) against every plausible candidate and reports which
ones actually resolve on the live server today.

Usage:
    python probe_versions.py
"""
from __future__ import annotations

import requests

BASE = "https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) genochain-research-script",
}

CANDIDATES = {
    "7": ["v5a", "v5b"],       # v5b already confirmed working this session
    "11": ["v5a", "v5b", "v5c"],
    "12": ["v5a", "v5b", "v5c"],
    "13": ["v5a", "v5b", "v5c"],
}


def probe(chrom: str, version: str) -> tuple[bool, int]:
    url = f"{BASE}/ALL.chr{chrom}.phase3_shapeit2_mvncall_integrated_{version}.20130502.genotypes.vcf.gz.tbi"
    try:
        resp = requests.head(url, headers=HEADERS, timeout=20, allow_redirects=True)
        return resp.status_code == 200, resp.status_code
    except requests.RequestException as e:
        return False, -1


if __name__ == "__main__":
    print("Probing live EBI server for real filenames (HEAD requests only, no download)...\n")
    confirmed = {}
    for chrom, versions in CANDIDATES.items():
        for v in versions:
            ok, status = probe(chrom, v)
            mark = "FOUND" if ok else f"no ({status})"
            print(f"  chr{chrom} / {v}: {mark}")
            if ok and chrom not in confirmed:
                confirmed[chrom] = v
        if chrom not in confirmed:
            print(f"  -> chr{chrom}: NONE of the tried candidates exist -- filename pattern may have changed entirely, not just the version token")
        print()

    print("=" * 50)
    print("CONFIRMED (paste these into REGIONS in remote_tabix_fetch.py):")
    for chrom, v in confirmed.items():
        print(f"  chr{chrom} -> {v}")
