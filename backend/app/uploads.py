"""
Normalization layer for user-uploaded VCF variants.

The curated demo dataset carries hand-assembled clinical evidence (functional
assays, segregation counts, hotspot domains, a curated ESM-2 embedding shift).
An uploaded VCF carries none of that — only what the annotator wrote into the
INFO field. This module maps an uploaded record onto the internal variant dict
that `acmg.py` and `ml.py` consume, and is deliberately explicit about which
evidence is genuinely absent.

Design rule: absent evidence is encoded as absent, never invented. An uploaded
variant therefore cannot satisfy PS3 (functional), PP1 (segregation), PM1
(hotspot) or PS1 (same-AA) — those criteria require curated knowledge this
pipeline does not have. The result is a conservative, honest classification:
uploads lean toward VUS unless the sequence consequence and population
frequency alone carry the call.
"""
from __future__ import annotations

import hashlib
from typing import Any

from .config import MODEL_VERSION

# ---------------------------------------------------------------------------
# Curated knowledge that CAN be applied to an arbitrary variant, because it is
# a property of the gene rather than of the specific variant.
# ---------------------------------------------------------------------------

# Genes where loss of function is an established disease mechanism. Drives
# PVS1. Deliberately conservative: genes acting through dominant-negative or
# gain-of-function mechanisms (MYH7, FGFR3, RET, …) are excluded, because a
# null variant there does NOT satisfy PVS1.
LOF_MECHANISM_GENES = {
    # Hereditary cancer
    "BRCA1", "BRCA2", "PALB2", "ATM", "CHEK2", "BARD1", "RAD51C", "RAD51D",
    "BRIP1", "TP53", "PTEN", "STK11", "CDH1", "APC", "MUTYH", "SMAD4",
    "BMPR1A", "NF1", "NF2", "RB1", "VHL", "TSC1", "TSC2", "MEN1", "SDHB",
    "SDHC", "SDHD", "FH", "FLCN", "CDKN2A",
    # Lynch / mismatch repair
    "MLH1", "MSH2", "MSH6", "PMS2", "EPCAM",
    # Metabolic / cardiovascular
    "LDLR", "APOB", "PCSK9", "CFTR", "SERPINA1", "HFE",
    # Sensorineural / neuromuscular
    "GJB2", "DMD", "SMN1", "OTC", "F8", "F9",
    # Cardiac channelopathy / structural where haploinsufficiency applies
    "KCNQ1", "KCNH2", "SCN5A", "MYBPC3", "LMNA", "PKP2", "DSP", "TTN",
}

# Gene -> associated condition + inheritance, used for display only. Nothing
# here feeds the ACMG rule engine.
GENE_CONDITIONS: dict[str, tuple[str, str]] = {
    "BRCA1": ("Hereditary breast and ovarian cancer syndrome", "Autosomal dominant"),
    "BRCA2": ("Hereditary breast and ovarian cancer syndrome", "Autosomal dominant"),
    "PALB2": ("Hereditary breast cancer", "Autosomal dominant"),
    "TP53": ("Li-Fraumeni syndrome", "Autosomal dominant"),
    "PTEN": ("PTEN hamartoma tumor syndrome", "Autosomal dominant"),
    "MLH1": ("Lynch syndrome", "Autosomal dominant"),
    "MSH2": ("Lynch syndrome", "Autosomal dominant"),
    "MSH6": ("Lynch syndrome", "Autosomal dominant"),
    "PMS2": ("Lynch syndrome", "Autosomal dominant"),
    "APC": ("Familial adenomatous polyposis", "Autosomal dominant"),
    "CFTR": ("Cystic fibrosis", "Autosomal recessive"),
    "LDLR": ("Familial hypercholesterolemia", "Autosomal dominant"),
    "GJB2": ("Nonsyndromic hearing loss (DFNB1)", "Autosomal recessive"),
    "MYH7": ("Hypertrophic cardiomyopathy", "Autosomal dominant"),
    "MYBPC3": ("Hypertrophic cardiomyopathy", "Autosomal dominant"),
    "KCNQ1": ("Long QT syndrome type 1", "Autosomal dominant"),
    "KCNH2": ("Long QT syndrome type 2", "Autosomal dominant"),
    "SCN5A": ("Brugada / Long QT syndrome type 3", "Autosomal dominant"),
    "LMNA": ("Dilated cardiomyopathy / laminopathy", "Autosomal dominant"),
    "ATM": ("Ataxia-telangiectasia / breast cancer risk", "Autosomal dominant/recessive"),
    "CHEK2": ("Hereditary breast cancer", "Autosomal dominant"),
    "DMD": ("Duchenne/Becker muscular dystrophy", "X-linked recessive"),
    "SERPINA1": ("Alpha-1 antitrypsin deficiency", "Autosomal recessive"),
    "HFE": ("Hereditary hemochromatosis", "Autosomal recessive"),
}

_CONSEQUENCE_SEVERITY = {
    "frameshift": 6, "nonsense": 6, "splice_donor": 5, "splice_acceptor": 5,
    "inframe_deletion": 4, "missense": 3, "synonymous": 1, "intronic": 0,
}


def _proxy_esm_delta(consequence: str | None, cadd: float | None, phylop: float | None,
                     revel: float | None, spliceai: float | None) -> float:
    """
    Transparent stand-in for the ESM-2 embedding shift on an uploaded variant.

    The curated dataset stores a real per-variant `esm_delta`; an uploaded VCF
    has none, and in DEMO_MODE there is no protein language model available to
    compute one. Rather than emit a hash-derived number that would look like a
    model output while carrying no signal, we derive a bounded proxy from the
    annotations actually present in the file. It is reported to the UI as
    `mode: "proxy-from-annotations"` so it is never mistaken for ESM-2 output.

    In LIVE_MODE (GENOGUIDE_MODE=live with torch + fair-esm installed) the real
    model runs instead and this function is bypassed.
    """
    severity = _CONSEQUENCE_SEVERITY.get(consequence or "", 0) / 6.0
    parts: list[tuple[float, float]] = [(severity, 0.45)]
    if cadd is not None:
        parts.append((min(max(cadd, 0.0) / 40.0, 1.0), 0.25))
    if phylop is not None:
        parts.append((min(max(phylop, 0.0) / 10.0, 1.0), 0.15))
    if revel is not None:
        parts.append((min(max(revel, 0.0), 1.0), 0.20))
    if spliceai is not None:
        parts.append((min(max(spliceai, 0.0), 1.0), 0.15))

    total_weight = sum(w for _, w in parts)
    score = sum(v * w for v, w in parts) / total_weight if total_weight else 0.0
    return round(min(max(score, 0.0), 1.0), 3)


def uploaded_variant_id(chrom: str, pos: int, ref: str, alt: str) -> str:
    """Stable, content-addressed id so re-uploading the same variant is idempotent."""
    digest = hashlib.sha256(f"{chrom}|{pos}|{ref}|{alt}".encode()).hexdigest()[:12]
    return f"UPL-{digest.upper()}"


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    """Map a parsed VCF record onto the internal variant dict."""
    gene = (payload.get("gene") or "").upper() or None
    consequence = payload.get("consequence") or "intronic"
    chrom = str(payload.get("chrom") or "?")
    pos = int(payload.get("pos") or 0)
    ref = payload.get("ref") or "N"
    alt = payload.get("alt") or "N"

    cadd = payload.get("cadd")
    revel = payload.get("revel")
    spliceai = payload.get("spliceai")
    phylop = payload.get("phylop")
    gnomad_af = payload.get("gnomad_af")

    condition, inheritance = GENE_CONDITIONS.get(gene or "", ("Not established in demo knowledge base", "—"))

    # Which ACMG criteria are unreachable because the upload lacks the evidence.
    missing_evidence = [
        {"criterion": "PS1", "reason": "No curated same-amino-acid pathogenic variant registry for uploaded data."},
        {"criterion": "PS3", "reason": "No functional assay evidence is present in a VCF file."},
        {"criterion": "PM1", "reason": "No hotspot / functional-domain annotation available for uploaded data."},
        {"criterion": "PP1", "reason": "No family segregation data is present in a VCF file."},
    ]
    if gnomad_af is None:
        missing_evidence.append({
            "criterion": "PM2 / BA1 / BS1",
            "reason": "No population allele frequency in the file — treated as absent from gnomAD, which satisfies PM2. Re-annotate with gnomAD frequencies for a reliable frequency call.",
        })

    return {
        "id": uploaded_variant_id(chrom, pos, ref, alt),
        "gene": gene or "—",
        "transcript": payload.get("transcript") or "—",
        "hgvs_c": payload.get("hgvs_c") or f"{chrom}:g.{pos}{ref}>{alt}",
        "hgvs_p": payload.get("hgvs_p") or "—",
        "chrom": chrom,
        "pos": pos,
        "ref": ref,
        "alt": alt,
        "consequence": consequence,
        "gnomad_af": gnomad_af,
        "cadd": cadd,
        "revel": revel,
        "spliceai": spliceai,
        "phylop": phylop,
        # Gene-level curated knowledge — legitimately applicable.
        "lof_mechanism": (gene in LOF_MECHANISM_GENES) if gene else False,
        # Variant-level curated evidence — genuinely absent for an upload.
        "hotspot_domain": None,
        "functional_evidence": None,
        "functional_source": None,
        "segregation": False,
        "segregation_families": 0,
        "same_aa_pathogenic": False,
        "condition": condition,
        "inheritance": inheritance,
        "esm_delta": _proxy_esm_delta(consequence, cadd, revel=revel, phylop=phylop, spliceai=spliceai),
        "showcase": False,
        "showcase_label": None,
        "public_note": "User-uploaded variant parsed from a VCF file. Evidence limited to what the file's annotations provide.",
        "demo_probs": None,
        "source": "upload",
        "missing_evidence": missing_evidence,
        "annotation_completeness": _completeness(cadd, revel, spliceai, phylop, gnomad_af, consequence),
        "model_version": MODEL_VERSION,
    }


def _completeness(cadd, revel, spliceai, phylop, gnomad_af, consequence) -> dict[str, Any]:
    fields = {
        "consequence": consequence is not None,
        "gnomad_af": gnomad_af is not None,
        "cadd": cadd is not None,
        "revel": revel is not None,
        "spliceai": spliceai is not None,
        "phylop": phylop is not None,
    }
    present = sum(1 for ok in fields.values() if ok)
    total = len(fields)
    return {
        "present": present,
        "total": total,
        "percent": round(100 * present / total),
        "fields": fields,
        "level": "HIGH" if present >= 5 else ("PARTIAL" if present >= 3 else "LOW"),
    }
