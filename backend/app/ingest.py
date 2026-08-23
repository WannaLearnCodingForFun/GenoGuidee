"""VCF / TXT ingestion into the clinical store. No invented coordinates."""
from __future__ import annotations

import hashlib
import logging
import re
import shutil
from pathlib import Path
from typing import Any

from . import clinical_db as DB
from .bioinformatics.vcf import iter_canonical_variants, validate_vcf
from .config import BASE_DIR
from .schemas.variant import GenomeBuild

log = logging.getLogger("genoguide")
UPLOAD_DIR = Path(BASE_DIR) / "uploads"
MAX_BYTES = 20 * 1024 * 1024

_COLON = re.compile(
    r"^(?:chr)?([0-9XYM]+):(\d+):([ACGTN]+):([ACGTN]+)$", re.I,
)
_SPACE = re.compile(
    r"^(?:chr)?([0-9XYM]+)\s+(\d+)\s+([ACGTN]+)\s+([ACGTN]+)$", re.I,
)
_GENE_C = re.compile(r"^([A-Z0-9-]+)[:\s]+(c\.[A-Za-z0-9_>+-]+)$")


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def store_file(filename: str, data: bytes) -> Path:
    UPLOAD_DIR.mkdir(parents=True, exist_ok=True)
    safe = re.sub(r"[^A-Za-z0-9._-]", "_", Path(filename).name)[:180]
    dest = UPLOAD_DIR / f"{sha256_bytes(data)[:16]}_{safe}"
    dest.write_bytes(data)
    return dest


def parse_txt_line(line: str) -> dict[str, Any] | None:
    s = line.strip()
    if not s or s.startswith("#"):
        return None
    m = _COLON.match(s)
    if m:
        chrom, pos, ref, alt = m.groups()
        return {
            "chromosome": chrom.upper(), "position": int(pos),
            "reference": ref.upper(), "alternate": alt.upper(),
            "genome_build": "GRCh38",
            "normalized_variant": f"GRCh38:{chrom.upper()}:{pos}:{ref.upper()}>{alt.upper()}",
        }
    m = _SPACE.match(s)
    if m:
        chrom, pos, ref, alt = m.groups()
        return {
            "chromosome": chrom.upper(), "position": int(pos),
            "reference": ref.upper(), "alternate": alt.upper(),
            "genome_build": "GRCh38",
            "normalized_variant": f"GRCh38:{chrom.upper()}:{pos}:{ref.upper()}>{alt.upper()}",
        }
    m = _GENE_C.match(s)
    if m:
        return {
            "gene": m.group(1), "hgvs_c": m.group(2),
            "normalized_variant": None,
        }
    raise ValueError(
        f"Unable to safely parse line: {s!r}. "
        "Accepted: chr17:43057045:A:AC, 17 43057045 A AC, BRCA1:c.5266dupC"
    )


def ingest_bytes(*, user_id: int, filename: str, data: bytes, patient_id: int | None) -> dict[str, Any]:
    if len(data) > MAX_BYTES:
        raise ValueError(f"file exceeds {MAX_BYTES} bytes")
    if not data:
        raise ValueError("empty file")
    digest = sha256_bytes(data)
    existing = DB.find_upload_by_sha(digest, uploaded_by=user_id)
    if existing:
        raise ValueError(
            f"duplicate upload (sha256={digest}); existing upload id={existing['id']} "
            f"status={existing['parsing_status']}"
        )
    path = store_file(filename, data)
    lower = filename.lower()
    if lower.endswith(".vcf") or lower.endswith(".vcf.gz"):
        file_type = "vcf"
    elif lower.endswith(".txt"):
        file_type = "txt"
    else:
        raise ValueError("allowed extensions: .vcf, .vcf.gz, .txt")

    upload = DB.create_upload(
        patient_id=patient_id, uploaded_by=user_id, filename=filename,
        file_type=file_type, file_size=len(data), sha256=digest,
        storage_path=str(path), parsing_status="PARSING",
    )
    uid = upload["id"]
    try:
        variants: list[dict[str, Any]] = []
        if file_type == "vcf":
            report = validate_vcf(path)
            if report["errors"] and not report["n_records"]:
                raise ValueError("; ".join(report["errors"][:8]))
            for cv in iter_canonical_variants(path, GenomeBuild.GRCH38):
                variants.append({
                    "chromosome": cv.chromosome, "position": cv.position,
                    "reference": cv.reference, "alternate": cv.alternate,
                    "genome_build": "GRCh38", "gene": cv.gene,
                    "hgvs_c": None, "hgvs_p": cv.hgvs_p,
                    "normalized_variant": cv.variant_id,
                    "consequence": None,
                    "allele_fraction": cv.vaf,
                    "source_type": "UPLOADED_VCF",
                })
        else:
            text = data.decode("utf-8", errors="replace")
            for line in text.splitlines():
                rec = parse_txt_line(line)
                if rec:
                    rec["source_type"] = "UPLOADED_TXT"
                    variants.append(rec)
        if not variants:
            raise ValueError("no variants extracted")
        for rec in variants:
            vid = DB.insert_variant(uid, rec)
            rec["id"] = vid
            if patient_id:
                DB.insert_observation(
                    patient_id=patient_id,
                    variant_id=vid,
                    source_file_id=uid,
                    allele_fraction=rec.get("allele_fraction"),
                    source_dataset=rec.get("source_type"),
                )
        DB.update_upload(uid, parsing_status="PARSED", variant_count=len(variants),
                         parsing_error=None, analysis_status="PARSED")
        log.info("[INGEST] parsed %s variants from %s", len(variants), filename)
        return {**DB.get_upload(uid), "variants": variants}
    except Exception as exc:
        DB.update_upload(uid, parsing_status="FAILED", parsing_error=str(exc))
        log.info("[INGEST] failed %s: %s", filename, exc)
        raise
