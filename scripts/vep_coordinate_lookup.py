# scripts/vep_coordinate_lookup.py
r"""
Resolves the ClinVar panel's HGVS coding notation (from fetch_clinvar_panel.py)
into real genomic coordinates (chrom, pos, ref, alt) via Ensembl VEP, so
run_real_data_test.py can build a TRUE position-exact pathogenic_lookup
instead of the gene-level watchlist fallback.

CRITICAL ASSEMBLY NOTE:
Your 1000 Genomes trio VCF data (data/raw/trio_regions/*.vcf) is GRCh37/hg19.
Ensembl's default REST server (rest.ensembl.org) returns GRCh38 coordinates.
Comparing GRCh38 ClinVar positions against GRCh37 trio positions would be
silently wrong -- same variant, different position numbers, no match despite
being the same physical spot in the genome, or worse, a coincidental wrong
match. This script uses Ensembl's GRCh37-specific mirror
(grch37.rest.ensembl.org) instead, so everything stays on the same build.

WHY THIS MATTERS: this is the one thing that makes the "gene-level watch"
caveat in run_real_data_test.py obsolete -- once this runs successfully,
de novo variants can be checked against an EXACT known-pathogenic position,
not just "same gene as something pathogenic somewhere".

fetch_clinvar_panel.py wrote variant_id as bare c. notation (e.g.
"c.2620-10_2621del") with no transcript -- VEP can't resolve that alone.
The full transcript-qualified HGVS lives in the 'title' column instead,
e.g. "NM_000492.4(CFTR):c.2620-10_2621del" -- this script extracts and
strips it to "NM_000492.4:c.2620-10_2621del" before querying VEP.

Not every row will resolve:
  - Some rows are structural/CNV variants (e.g. "GRCh38/hg38 7q31.2(chr7:...)x3"),
    not point HGVS -- these have no c. notation and are skipped outright.
  - Some may have a transcript version VEP doesn't recognize, or use HGVS
    syntax VEP's parser rejects (e.g. certain complex intronic deletions).
  - Some genes may not exist in the older GRCh37 transcript set at all.
This script logs and counts failures rather than silently dropping them,
so you know exactly how much of the panel actually got position-exact
coordinates versus how much stayed gene-level-only.

Usage:
    python -m scripts.vep_coordinate_lookup
Output:
    data/knowledge/clinvar_panel_with_coords.csv
    (adds chrom, pos, ref, alt columns; blank for unresolved rows)
"""
from __future__ import annotations

import csv
import re
import sys
import time
from pathlib import Path
from typing import Any, Optional

import requests

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

# GRCh37 mirror -- NOT the default rest.ensembl.org, see module docstring.
VEP_BASE = "https://rest.ensembl.org"
DEFAULT_HEADERS = {"Content-Type": "application/json"}
REQUEST_TIMEOUT = 40
MAX_RETRIES = 3
RETRY_BACKOFF_SECS = 1.5
BATCH_SIZE = 100  # VEP's POST endpoint supports up to 200; stay conservative

IN_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "clinvar_panel.csv"
OUT_PATH = Path(__file__).resolve().parent.parent / "data" / "knowledge" / "clinvar_panel_with_coords.csv"

# Matches "NM_000492.4(CFTR):c.2620-10_2621del" -> transcript + c. notation,
# dropping the "(CFTR)" gene-name parenthetical VEP's HGVS parser doesn't want.
_FULL_HGVS_RE = re.compile(r"([A-Z]{2}_\d+\.\d+)\([A-Z0-9]+\):(c\.[^\s]+?)(?:\s|$)")


def extract_full_hgvs(title: str) -> Optional[str]:
    m = _FULL_HGVS_RE.search(title)
    if not m:
        return None
    transcript, c_notation = m.groups()
    return f"{transcript}:{c_notation}"


class VepConnectionError(RuntimeError):
    """DNS failure, connection refused/reset, or timeout -- a network-level
    problem, not a bad variant. Bisecting a batch does nothing to fix this;
    the same batch just needs to be retried once connectivity is back."""
    pass


class VepServerError(RuntimeError):
    """VEP actually processed the request and returned an error (usually a
    malformed/unresolvable HGVS entry somewhere in the batch). Bisection is
    the right move here -- it isolates which specific entry is bad."""
    pass


def _post_batch_with_retry(hgvs_list: list[str], max_retries: int = 2) -> list[dict[str, Any]]:
    url = f"{VEP_BASE}/vep/human/hgvs"
    last_exc: Optional[Exception] = None
    last_body: str = ""
    is_connection_issue = False

    for attempt in range(1, max_retries + 1):
        try:
            resp = requests.post(
                url,
                headers=DEFAULT_HEADERS,
                json={"hgvs_notations": hgvs_list},
                timeout=REQUEST_TIMEOUT,
            )
            if resp.status_code == 429:
                wait = float(resp.headers.get("Retry-After", RETRY_BACKOFF_SECS * attempt))
                time.sleep(wait)
                continue
            resp.raise_for_status()
            return resp.json()
        except requests.exceptions.ConnectionError as exc:
            # DNS failure, connection refused/reset -- network-level, not data-level.
            last_exc = exc
            is_connection_issue = True
            time.sleep(RETRY_BACKOFF_SECS * attempt)
        except requests.RequestException as exc:
            last_exc = exc
            try:
                last_body = exc.response.text[:300] if exc.response is not None else ""
            except Exception:
                last_body = ""
            time.sleep(RETRY_BACKOFF_SECS * attempt)

    msg = f"VEP batch request failed after {max_retries} attempts: {last_exc} | body: {last_body}"
    if is_connection_issue:
        raise VepConnectionError(msg)
    raise VepServerError(msg)


def _extract_coords(entry: dict[str, Any]) -> Optional[tuple[str, int, str, str]]:
    """Same extraction logic as reconcile.py's _extract_variant_key."""
    chrom = entry.get("seq_region_name")
    pos = entry.get("start")
    allele_string = entry.get("allele_string")
    if chrom and pos and allele_string and "/" in allele_string:
        ref, alt = allele_string.split("/", 1)
        return (f"chr{chrom}", int(pos), ref, alt)
    return None


def main():
    if not IN_PATH.exists():
        raise FileNotFoundError(f"{IN_PATH} not found -- run fetch_clinvar_panel.py first")

    rows = []
    with open(IN_PATH, encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)

    # Build hgvs strings, tracking which row each maps to. Rows with no
    # extractable full HGVS (CNVs, malformed titles) are marked skipped
    # up front and never sent to VEP.
    hgvs_by_row_idx: dict[int, str] = {}
    skipped_no_hgvs = 0
    for i, row in enumerate(rows):
        hgvs = extract_full_hgvs(row.get("title", ""))
        if hgvs is None:
            skipped_no_hgvs += 1
            continue
        hgvs_by_row_idx[i] = hgvs

    print(f"Total rows: {len(rows)}")
    print(f"Skipped (no resolvable HGVS, e.g. CNV/structural entries): {skipped_no_hgvs}")
    print(f"Sending {len(hgvs_by_row_idx)} variants to VEP ({VEP_BASE}) in batches of {BATCH_SIZE} ...\n")

    # Query VEP in batches, matching results back by the 'input' field VEP
    # echoes in each response entry -- safer than assuming order is preserved.
    #
    # A single malformed HGVS string in a batch can crash the ENTIRE batch
    # with a 500 (VEP's bulk endpoint doesn't isolate bad entries), so on
    # failure we bisect the batch and retry each half recursively until the
    # bad entr(y/ies) are isolated down to single items -- everything else
    # in the batch still resolves instead of being lost to one bad row.
    resolved_by_hgvs: dict[str, tuple[str, int, str, str]] = {}
    failed_hgvs: list[str] = []

    def resolve_chunk(hgvs_list: list[str], depth: int = 0, network_retry: int = 0):
        if not hgvs_list:
            return
        indent = "  " * (depth + 1)
        retries = 2 if depth == 0 else 1

        try:
            results = _post_batch_with_retry(hgvs_list, max_retries=retries)
        except VepConnectionError as e:
            # Network/DNS problem, not a bad variant -- bisecting won't help.
            # Pause and retry the SAME batch (not split) a few times, since
            # this usually means the connection dropped and may come back.
            if network_retry < 3:
                print(f"{indent}network/DNS error, pausing 5s and retrying "
                      f"same batch of {len(hgvs_list)} (attempt {network_retry + 1}/3): {e}")
                time.sleep(5)
                resolve_chunk(hgvs_list, depth, network_retry + 1)
            else:
                print(f"{indent}network still unreachable after retries -- leaving "
                      f"this batch of {len(hgvs_list)} unresolved for now (rerun the "
                      f"script later to pick these up once connectivity is back)")
                failed_hgvs.extend(hgvs_list)
            return
        except VepServerError as e:
            if len(hgvs_list) == 1:
                print(f"{indent}FAILED (single variant): {hgvs_list[0]} -- {e}")
                failed_hgvs.append(hgvs_list[0])
                return
            mid = len(hgvs_list) // 2
            print(f"{indent}batch of {len(hgvs_list)} failed (server error), "
                  f"bisecting into {mid} + {len(hgvs_list) - mid} ...")
            time.sleep(0.5)
            resolve_chunk(hgvs_list[:mid], depth + 1)
            resolve_chunk(hgvs_list[mid:], depth + 1)
            return

        returned_inputs = set()
        for entry in results:
            if "error" in entry:
                continue
            input_str = entry.get("input", "")
            returned_inputs.add(input_str)
            coords = _extract_coords(entry)
            if coords:
                resolved_by_hgvs[input_str] = coords

        for h in hgvs_list:
            if h not in returned_inputs or h not in resolved_by_hgvs:
                failed_hgvs.append(h)

    idx_list = list(hgvs_by_row_idx.items())
    for batch_start in range(0, len(idx_list), BATCH_SIZE):
        batch = idx_list[batch_start:batch_start + BATCH_SIZE]
        batch_hgvs = [h for _, h in batch]
        print(f"  batch {batch_start // BATCH_SIZE + 1}: {len(batch_hgvs)} variants ...")
        resolve_chunk(batch_hgvs)

    print(f"\nResolved: {len(resolved_by_hgvs)} / {len(hgvs_by_row_idx)} sent")
    print(f"Failed to resolve: {len(failed_hgvs)}")
    if failed_hgvs:
        print("First few failures (for debugging):")
        for h in failed_hgvs[:10]:
            print(f"  {h}")

    # Write augmented CSV
    fieldnames = ["gene", "variant_id", "classification", "raw_clinsig", "review_status", "title",
                  "conditions", "disease_db_xrefs", "chrom", "pos", "ref", "alt"]
    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        for i, row in enumerate(rows):
            hgvs = hgvs_by_row_idx.get(i)
            coords = resolved_by_hgvs.get(hgvs) if hgvs else None
            out_row = dict(row)
            if coords:
                out_row["chrom"], out_row["pos"], out_row["ref"], out_row["alt"] = coords
            else:
                out_row["chrom"] = out_row["pos"] = out_row["ref"] = out_row["alt"] = ""
            writer.writerow(out_row)

    print(f"\nWrote {len(rows)} rows ({len(resolved_by_hgvs)} with real coordinates) -> {OUT_PATH}")


if __name__ == "__main__":
    main()
