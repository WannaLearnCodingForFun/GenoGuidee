"""
VCF validation, normalization and parsing.

Established tools are preferred and never reimplemented when present:
if `bcftools` is on PATH and a reference FASTA is supplied, normalization is
delegated to `bcftools norm -f REF -m -both` (true left-alignment).

When bcftools is unavailable (the common case on a fresh laptop), a
pure-Python fallback performs the reference-free subset of normalization:

  * multiallelic decomposition (one ALT per record)
  * allele parsimony trimming (shared suffix, then shared prefix)

Pure-Python mode CANNOT left-align indels in repeat regions (that requires the
reference genome); reports state this explicitly rather than pretending.

Every operation produces a machine-readable JSON report.
"""
from __future__ import annotations

import gzip
import json
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any, Iterator, Optional

from ..schemas.variant import CanonicalVariant, GenomeBuild, Zygosity

VCF_FIXED_COLS = ["#CHROM", "POS", "ID", "REF", "ALT", "QUAL", "FILTER", "INFO"]
_VALID_ALT = set("ACGTNacgtn,*.")


def bcftools_available() -> bool:
    return shutil.which("bcftools") is not None


def _open(path: str | Path):
    p = Path(path)
    return gzip.open(p, "rt") if p.suffix == ".gz" else open(p)


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

def validate_vcf(path: str | Path, max_errors: int = 50) -> dict[str, Any]:
    """Structural validation. Returns a machine-readable report; never raises
    on malformed content (malformations are the findings)."""
    p = Path(path)
    report: dict[str, Any] = {
        "file": str(p),
        "valid": False,
        "fileformat": None,
        "n_header_lines": 0,
        "n_records": 0,
        "n_samples": 0,
        "samples": [],
        "contigs_seen": [],
        "filters_seen": [],
        "multiallelic_records": 0,
        "sorted": True,
        "errors": [],
        "warnings": [],
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S"),
    }
    if not p.exists():
        report["errors"].append("file does not exist")
        return report

    contigs: dict[str, int] = {}
    filters: set[str] = set()
    last_pos: dict[str, int] = {}
    saw_columns = False

    try:
        with _open(p) as f:
            for lineno, line in enumerate(f, 1):
                line = line.rstrip("\n")
                if not line:
                    continue
                if line.startswith("##"):
                    report["n_header_lines"] += 1
                    if line.startswith("##fileformat="):
                        report["fileformat"] = line.split("=", 1)[1]
                    continue
                if line.startswith("#CHROM"):
                    saw_columns = True
                    cols = line.split("\t")
                    if cols[:8] != VCF_FIXED_COLS:
                        report["errors"].append(f"line {lineno}: bad column header: {cols[:8]}")
                    if len(cols) > 9:
                        report["samples"] = cols[9:]
                        report["n_samples"] = len(cols) - 9
                    continue
                if not saw_columns:
                    report["errors"].append(f"line {lineno}: data before #CHROM header")
                    saw_columns = True  # report once
                fields = line.split("\t")
                if len(fields) < 8:
                    if len(report["errors"]) < max_errors:
                        report["errors"].append(f"line {lineno}: {len(fields)} columns (<8)")
                    continue
                chrom, pos_s, _id, ref, alt = fields[0], fields[1], fields[2], fields[3], fields[4]
                if not pos_s.isdigit():
                    report["errors"].append(f"line {lineno}: non-integer POS {pos_s!r}")
                    continue
                pos = int(pos_s)
                if not ref or any(c not in "ACGTNacgtn" for c in ref):
                    report["errors"].append(f"line {lineno}: invalid REF {ref!r}")
                if not alt or any(c not in _VALID_ALT for c in alt):
                    if "<" in alt:
                        report["warnings"].append(
                            f"line {lineno}: symbolic ALT {alt!r} (SV/CNV — not yet interpreted)")
                    else:
                        report["errors"].append(f"line {lineno}: invalid ALT {alt!r}")
                if "," in alt:
                    report["multiallelic_records"] += 1
                if chrom in last_pos and pos < last_pos[chrom]:
                    report["sorted"] = False
                last_pos[chrom] = pos
                contigs[chrom] = contigs.get(chrom, 0) + 1
                filt = fields[6]
                if filt not in (".", ""):
                    filters.add(filt)
                report["n_records"] += 1
    except (OSError, gzip.BadGzipFile) as e:
        report["errors"].append(f"unreadable file: {e}")
        return report

    if report["fileformat"] is None:
        report["errors"].append("missing ##fileformat header")
    if not saw_columns:
        report["errors"].append("missing #CHROM column header")
    report["contigs_seen"] = [{"contig": c, "records": n} for c, n in sorted(contigs.items())]
    report["filters_seen"] = sorted(filters)
    report["valid"] = not report["errors"]
    return report


# ---------------------------------------------------------------------------
# Normalization
# ---------------------------------------------------------------------------

def trim_alleles(pos: int, ref: str, alt: str) -> tuple[int, str, str]:
    """Parsimony trimming: shared suffix first, then shared prefix.
    Reference-free — does NOT left-align through repeat tracts."""
    ref, alt = ref.upper(), alt.upper()
    # suffix
    while len(ref) > 1 and len(alt) > 1 and ref[-1] == alt[-1]:
        ref, alt = ref[:-1], alt[:-1]
    # prefix
    while len(ref) > 1 and len(alt) > 1 and ref[0] == alt[0]:
        ref, alt = ref[1:], alt[1:]
        pos += 1
    return pos, ref, alt


def decompose_and_trim_line(fields: list[str]) -> list[list[str]]:
    """Split multiallelic records into per-ALT records, then trim alleles.
    Sample columns are carried through unchanged with a warning flag in INFO
    (correct GT re-mapping per allele requires bcftools; we do not fake it)."""
    out: list[list[str]] = []
    alts = fields[4].split(",")
    for i, alt in enumerate(alts):
        if alt in ("*", "."):
            continue
        new = list(fields)
        pos, ref, a = trim_alleles(int(fields[1]), fields[3], alt)
        new[1], new[3], new[4] = str(pos), ref, a
        if len(alts) > 1:
            info = new[7] if len(new) > 7 else "."
            tag = f"GG_DECOMPOSED=allele_{i + 1}_of_{len(alts)}"
            new[7] = tag if info in (".", "") else f"{info};{tag}"
        out.append(new)
    return out


def normalize_vcf(
    path: str | Path,
    output: str | Path | None = None,
    reference_fasta: str | Path | None = None,
) -> dict[str, Any]:
    p = Path(path)
    out = Path(output) if output else p.with_name(p.stem.replace(".vcf", "") + ".normalized.vcf")

    if bcftools_available() and reference_fasta:
        cmd = ["bcftools", "norm", "-f", str(reference_fasta), "-m", "-both",
               "-o", str(out), str(p)]
        res = subprocess.run(cmd, capture_output=True, text=True)
        return {
            "file": str(p), "output": str(out), "engine": "bcftools norm",
            "left_aligned": True, "command": " ".join(cmd),
            "returncode": res.returncode, "stderr": res.stderr[-2000:],
            "success": res.returncode == 0,
        }

    stats = {"records_in": 0, "records_out": 0, "decomposed": 0, "trimmed": 0}
    with _open(p) as fin, open(out, "w") as fout:
        for line in fin:
            if line.startswith("#"):
                fout.write(line)
                if line.startswith("##fileformat"):
                    fout.write('##GG_normalization="pure-python: decompose+trim; '
                               'NOT left-aligned (no reference genome available)"\n')
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 8:
                continue
            stats["records_in"] += 1
            was_multi = "," in fields[4]
            for new in decompose_and_trim_line(fields):
                if (new[1], new[3], new[4]) != (fields[1], fields[3], fields[4].split(",")[0]) and not was_multi:
                    stats["trimmed"] += 1
                stats["records_out"] += 1
                fout.write("\t".join(new) + "\n")
            if was_multi:
                stats["decomposed"] += 1

    return {
        "file": str(p), "output": str(out), "engine": "pure-python",
        "left_aligned": False,
        "left_alignment_note": "requires bcftools + reference FASTA; install to enable",
        **stats, "success": True,
    }


# ---------------------------------------------------------------------------
# Parsing to canonical variants
# ---------------------------------------------------------------------------

def _zygosity_from_gt(gt: str) -> Zygosity:
    alleles = gt.replace("|", "/").split("/")
    non_ref = [a for a in alleles if a not in ("0", ".")]
    if not non_ref:
        return Zygosity.UNKNOWN
    if len(alleles) == 1:
        return Zygosity.HEMIZYGOUS
    if len(set(non_ref)) == 1 and len(non_ref) == len(alleles):
        return Zygosity.HOMOZYGOUS
    return Zygosity.HETEROZYGOUS


def iter_canonical_variants(
    path: str | Path,
    build: GenomeBuild = GenomeBuild.GRCH38,
    sample_index: int = 0,
) -> Iterator[CanonicalVariant]:
    """Yield canonical variants from a (preferably normalized) VCF.
    Multiallelic records are decomposed on the fly; symbolic ALTs are skipped."""
    fmt_cols: list[str] = []
    with _open(path) as f:
        for line in f:
            if line.startswith("#"):
                continue
            fields = line.rstrip("\n").split("\t")
            if len(fields) < 8:
                continue
            qual: Optional[float] = None
            if fields[5] not in (".", ""):
                try:
                    qual = float(fields[5])
                except ValueError:
                    qual = None
            zyg, ad, dp, vaf = Zygosity.UNKNOWN, None, None, None
            if len(fields) > 9 + sample_index:
                fmt_cols = fields[8].split(":")
                sample = fields[9 + sample_index].split(":")
                fmt = dict(zip(fmt_cols, sample))
                if "GT" in fmt:
                    zyg = _zygosity_from_gt(fmt["GT"])
                if "DP" in fmt and fmt["DP"].isdigit():
                    dp = int(fmt["DP"])
                if "AD" in fmt:
                    parts = [x for x in fmt["AD"].split(",") if x.isdigit()]
                    if len(parts) >= 2:
                        ad = int(parts[1])
                        total = sum(int(x) for x in parts)
                        if total > 0:
                            vaf = round(ad / total, 4)
            for rec in decompose_and_trim_line(fields):
                alt = rec[4]
                if "<" in alt or alt in (".", "*"):
                    continue
                try:
                    yield CanonicalVariant.from_vcf_fields(
                        build=build, chrom=rec[0], pos=int(rec[1]),
                        ref=rec[3], alt=alt, qual=qual,
                        filter_status=fields[6] if fields[6] != "." else None,
                        zygosity=zyg, allele_depth=ad, read_depth=dp, vaf=vaf,
                    )
                except ValueError:
                    continue  # counted by validate_vcf; parsing is permissive


def write_report(report: dict[str, Any], path: str | Path) -> None:
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(json.dumps(report, indent=2))
