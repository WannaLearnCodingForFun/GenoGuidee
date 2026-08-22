"""
Pure-Python remote tabix region fetch -- no tabix binary, no WSL/Docker.
Reimplements the .tbi index lookup + BGZF block decompression tabix does
internally, using only requests/zlib/struct.

Usage:
    python remote_tabix_fetch.py

Fixes applied vs the first draft:
  - BASE corrected: ftp.1000genomes.org -> ftp.1000genomes.ebi.ac.uk (https)
    The old .org host returns a fake 200/HTML load-balancer stub instead of
    a real 404, which is why it failed with "incorrect header check" rather
    than a clear "file not found."
  - Per-chromosome version suffix: confirmed live via probe_versions.py --
    all chromosomes tried (7, 11, 12, 13) are v5b, not v5a as most
    secondhand 2015-era scripts assume.
  - User-Agent header added to both the index and range-data requests,
    since some EBI endpoints apply bot detection keyed off UA.
"""
from __future__ import annotations

import struct
import time
import zlib
from pathlib import Path

import requests

OUT_DIR = Path(__file__).resolve().parent.parent / "data" / "raw" / "trio_regions"
OUT_DIR.mkdir(parents=True, exist_ok=True)

BASE = "https://ftp.1000genomes.ebi.ac.uk/vol1/ftp/release/20130502"

HEADERS_COMMON = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) genochain-research-script",
}

# gene: (chrom_in_file, start, end, version_suffix)  -- GRCh37, ~unverified
# coordinates, sanity-check against a known variant before trusting results.
# Version suffix CONFIRMED LIVE via probe_versions.py: all four chromosomes
# are v5b. Secondhand scripts/mirrors from ~2015-2020 consistently claim
# v5a for chr11/12/13 -- that's stale. EBI appears to have reissued the
# entire autosome set as v5b at some point after those snapshots were
# taken; chr7 wasn't a special case, it was just the first one hit.
REGIONS = {
    "CFTR": ("7", 117118000, 117312000, "v5b"),
    "HBB": ("11", 5246000, 5250000, "v5b"),
    "GJB2": ("13", 20760000, 20765000, "v5b"),
    "PAH": ("12", 102836000, 102958000, "v5b"),
}

FETCH_CAP_BYTES = 6_000_000  # shrunk from 20MB -- gene regions here are small (tens-hundreds of kb
                              # of genomic sequence), so a smaller compressed-range request is both
                              # faster and less likely to hit a mid-transfer connection drop


def vcf_url(chrom: str, version: str) -> str:
    return f"{BASE}/ALL.chr{chrom}.phase3_shapeit2_mvncall_integrated_{version}.20130502.genotypes.vcf.gz"


def _get_with_retry(url: str, headers: dict, range_header: str | None = None) -> requests.Response:
    """Shared retry wrapper -- used by the index fetch, header fetch, and
    range fetch alike, since PAH's failure showed the index/header calls
    needed the same protection fetch_range already had."""
    req_headers = dict(headers)
    if range_header:
        req_headers["Range"] = range_header
    last_error = None
    for attempt in range(4):
        try:
            resp = requests.get(url, headers=req_headers, timeout=120)
            resp.raise_for_status()
            return resp
        except (requests.exceptions.Timeout,
                requests.exceptions.ConnectionError,
                requests.exceptions.ChunkedEncodingError) as e:
            last_error = e
            if attempt < 3:
                wait = 2 * (attempt + 1)
                print(f"  connection issue ({type(e).__name__}), retrying in {wait}s ({attempt + 1}/4) ...")
                time.sleep(wait)
    raise last_error


def fetch_range(url: str, start: int, end: int) -> bytes:
    resp = _get_with_retry(url, HEADERS_COMMON, range_header=f"bytes={start}-{end}")
    return resp.content


def parse_tbi(raw_tbi_bytes: bytes):
    """
    .tbi index files are BGZF-compressed (same wrapper as the .vcf.gz data
    files), and can span multiple concatenated BGZF blocks. A plain single
    zlib.decompress() only reads the first block and silently truncates.
    Route through the same bgzf_blocks() reader used for VCF data so
    multi-block indexes decompress fully.
    """
    index_bytes = b"".join(bgzf_blocks(raw_tbi_bytes))

    magic = index_bytes[0:4]
    assert magic == b"TBI\x01", f"unexpected tbi magic: {magic!r}"
    off = 4
    n_ref, fmt, col_seq, col_beg, col_end, meta, skip, l_nm = struct.unpack_from("<8i", index_bytes, off)
    off += 32
    names_blob = index_bytes[off: off + l_nm]
    off += l_nm
    names = [n for n in names_blob.split(b"\x00") if n]
    name_to_idx = {n.decode(): i for i, n in enumerate(names)}

    linear_indexes = [None] * n_ref
    for ref_i in range(n_ref):
        n_bin, = struct.unpack_from("<i", index_bytes, off)
        off += 4
        for _ in range(n_bin):
            _bin, n_chunk = struct.unpack_from("<Ii", index_bytes, off)
            off += 8
            off += 16 * n_chunk  # skip chunk_beg/chunk_end pairs -- using linear index only
        n_intv, = struct.unpack_from("<i", index_bytes, off)
        off += 4
        intervals = struct.unpack_from(f"<{n_intv}Q", index_bytes, off) if n_intv else ()
        off += 8 * n_intv
        linear_indexes[ref_i] = intervals

    return name_to_idx, linear_indexes


def min_virtual_offset(linear_index: tuple, beg: int) -> int:
    bucket = beg >> 14  # tabix linear index bin size = 16384 bp
    if not linear_index:
        return 0
    bucket = min(bucket, len(linear_index) - 1)
    # walk back to the first non-zero entry at or before bucket, tabix
    # sometimes leaves empty (0) buckets for regions with no records
    while bucket > 0 and linear_index[bucket] == 0:
        bucket -= 1
    return linear_index[bucket]


def bgzf_blocks(data: bytes):
    i = 0
    n = len(data)
    while i < n:
        if i + 18 > n or data[i:i + 2] != b"\x1f\x8b":
            break
        xlen, = struct.unpack_from("<H", data, i + 10)
        extra = data[i + 12: i + 12 + xlen]
        bsize = None
        j = 0
        while j + 4 <= len(extra):
            si1, si2 = extra[j], extra[j + 1]
            slen, = struct.unpack_from("<H", extra, j + 2)
            if si1 == 66 and si2 == 67:  # 'B','C'
                bsize, = struct.unpack_from("<H", extra, j + 4)
            j += 4 + slen
        if bsize is None:
            break
        block_size = bsize + 1
        if i + block_size > n:
            break  # incomplete trailing block -- stop, we fetched enough
        block = data[i:i + block_size]
        isize, = struct.unpack_from("<I", block, len(block) - 4)
        if isize > 0:
            yield zlib.decompress(block[12 + xlen: -8], -15)
        i += block_size


def fetch_vcf_header_line(url: str) -> str:
    """
    The #CHROM header line (with all sample names) lives at the very start
    of the file -- the region fetch below deliberately jumps past it via
    the tabix index to avoid downloading the whole file, so it NEVER
    includes the header. Without this, parse_region_vcf() silently finds
    no header, sets header_cols = None, and skips every row -- which is
    exactly why the trio fetch was returning 0 variants for every sample
    despite the region data itself being real and present.
    """
    headers = dict(HEADERS_COMMON)
    headers["Range"] = "bytes=0-2000000"  # header is a few KB to ~20KB even with 2500+ samples; generous margin
    resp = _get_with_retry(url, HEADERS_COMMON, range_header="bytes=0-2000000")
    for chunk in bgzf_blocks(resp.content):
        text = chunk.decode("utf-8", errors="replace")
        for line in text.splitlines():
            if line.startswith("#CHROM"):
                return line
    raise RuntimeError("Could not find #CHROM header line in first 2MB of file -- header may be larger than expected")


def fetch_region(gene: str, chrom: str, start: int, end: int, version: str) -> str:
    url = vcf_url(chrom, version)
    tbi_url = url + ".tbi"

    print(f"[{gene}] downloading index ({version}) ...")
    tbi_resp = _get_with_retry(tbi_url, HEADERS_COMMON)
    name_to_idx, linear_indexes = parse_tbi(tbi_resp.content)

    if chrom not in name_to_idx:
        raise RuntimeError(f"chrom '{chrom}' not found in index; names present: {list(name_to_idx)[:5]}...")
    ref_i = name_to_idx[chrom]
    vo = min_virtual_offset(linear_indexes[ref_i], start)
    coffset, uoffset = vo >> 16, vo & 0xFFFF
    print(f"[{gene}] starting compressed fetch at byte {coffset} (uoffset {uoffset})")

    print(f"[{gene}] fetching sample header ...")
    header_line = fetch_vcf_header_line(url)

    raw = fetch_range(url, coffset, coffset + FETCH_CAP_BYTES)

    decompressed_parts = list(bgzf_blocks(raw))
    full = b"".join(decompressed_parts)
    full = full[uoffset:]  # trim to the exact start point within the first block

    text = full.decode("utf-8", errors="replace")
    out_lines = [header_line]
    for line in text.splitlines():
        if line.startswith("#"):
            continue  # region fetch shouldn't contain header lines, but skip defensively if it does
        fields = line.split("\t", 2)
        if len(fields) < 2:
            continue
        c, pos_s = fields[0], fields[1]
        if c != chrom:
            continue
        pos = int(pos_s)
        if pos > end:
            break  # sorted by position -- safe to stop
        if pos >= start:
            out_lines.append(line)

    return "\n".join(out_lines)


if __name__ == "__main__":
    for gene, (chrom, start, end, version) in REGIONS.items():
        try:
            content = fetch_region(gene, chrom, start, end, version)
            out_path = OUT_DIR / f"{gene}.vcf"
            out_path.write_text(content, encoding="utf-8")
            n_records = sum(1 for l in content.splitlines() if not l.startswith("#"))
            print(f"[{gene}] wrote {n_records} record(s) -> {out_path}\n")
        except Exception as e:
            print(f"[{gene}] FAILED: {e}\n")
