"""Entity normalization module for genomic variants, genes, and diseases.

Converts diverse user inputs into canonical representations for querying
CIViC and DGIdb knowledge bases.
"""

from __future__ import annotations

import re

# Standard HGNC gene alias mapping
GENE_ALIASES: dict[str, str] = {
    "ERBB1": "EGFR",
    "HER1": "EGFR",
    "HER2": "ERBB2",
    "NEU": "ERBB2",
    "K-RAS": "KRAS",
    "KRAS2": "KRAS",
    "B-RAF": "BRAF",
    "BRAF1": "BRAF",
    "P53": "TP53",
    "TP-53": "TP53",
    "PD-L1": "CD274",
    "PDL1": "CD274",
    "PD-1": "PDCD1",
    "PD1": "PDCD1",
    "C-KIT": "KIT",
    "C-MET": "MET",
    "ABL": "ABL1",
    "C-ABL": "ABL1",
    "PI3K": "PIK3CA",
    "PIK3C": "PIK3CA",
}

# Amino acid 3-letter to 1-letter map
AA_3_TO_1: dict[str, str] = {
    "ALA": "A", "ARG": "R", "ASN": "N", "ASP": "D", "CYS": "C",
    "GLN": "Q", "GLU": "E", "GLY": "G", "HIS": "H", "ILE": "I",
    "LEU": "L", "LYS": "K", "MET": "M", "PHE": "F", "PRO": "P",
    "SER": "S", "THR": "T", "TRP": "W", "TYR": "Y", "VAL": "V",
    "TER": "*", "STOP": "*",
}

# Standard disease synonyms/acronyms to canonical CIViC disease names
DISEASE_SYNONYMS: dict[str, str] = {
    "NSCLC": "Non-Small Cell Lung Cancer",
    "LUNG NON-SMALL CELL CARCINOMA": "Non-Small Cell Lung Cancer",
    "NON SMALL CELL LUNG CANCER": "Non-Small Cell Lung Cancer",
    "NON-SMALL CELL LUNG CARCINOMA": "Non-Small Cell Lung Cancer",
    "LUNG ADENOCARCINOMA": "Non-Small Cell Lung Cancer",
    "LUAD": "Non-Small Cell Lung Cancer",
    "LUNG CANCER": "Non-Small Cell Lung Cancer",
    "MELANOMA": "Melanoma",
    "CUTANEOUS MELANOMA": "Melanoma",
    "SKIN MELANOMA": "Melanoma",
    "SKIN CANCER": "Melanoma",
    "CRC": "Colorectal Cancer",
    "COLORECTAL CARCINOMA": "Colorectal Cancer",
    "COLON CANCER": "Colorectal Cancer",
    "RECTAL CANCER": "Colorectal Cancer",
    "BC": "Breast Cancer",
    "BREAST CARCINOMA": "Breast Cancer",
    "GIST": "Gastrointestinal Stromal Tumor",
    "GASTROINTESTINAL STROMAL CANCER": "Gastrointestinal Stromal Tumor",
    "AML": "Acute Myeloid Leukemia",
    "ACUTE MYELOGENOUS LEUKEMIA": "Acute Myeloid Leukemia",
    "CML": "Chronic Myelogenous Leukemia",
    "CHRONIC MYELOID LEUKEMIA": "Chronic Myelogenous Leukemia",
    "PANCREATIC CANCER": "Pancreatic Adenocarcinoma",
    "PAAD": "Pancreatic Adenocarcinoma",
    "PANCREATIC DUCTAL ADENOCARCINOMA": "Pancreatic Adenocarcinoma",
    "PDAC": "Pancreatic Adenocarcinoma",
    "OVARIAN CANCER": "Ovarian Cancer",
    "OV": "Ovarian Cancer",
    "PROSTATE CANCER": "Prostate Cancer",
    "PRAD": "Prostate Cancer",
    "GLIOBLASTOMA": "Glioblastoma",
    "GBM": "Glioblastoma",
}


def normalize_gene(gene: str) -> str:
    """Normalize gene symbol to canonical HGNC symbol."""
    if not gene:
        return ""
    clean = gene.strip().upper()
    clean = re.sub(r"[^A-Z0-9\-]", "", clean)
    return GENE_ALIASES.get(clean, clean)


def normalize_variant(variant: str) -> str:
    """Normalize genomic variant string into standard 1-letter representation.

    Examples:
        'L858R' -> 'L858R'
        'p.L858R' -> 'L858R'
        'p.Leu858Arg' -> 'L858R'
        'V600E' -> 'V600E'
        'p.Val600Glu' -> 'V600E'
        'Amplification' -> 'AMPLIFICATION'
    """
    if not variant:
        return ""
    clean = variant.strip()

    # Strip leading HGVS prefixes if present
    clean = re.sub(r"^[pcgmn]\.", "", clean, flags=re.IGNORECASE)

    # Check for 3-letter AA substitution pattern like Leu858Arg or Val600Glu
    match_3aa = re.match(r"^([A-Za-z]{3})(\d+)([A-Za-z]{3}|\*)$", clean, re.IGNORECASE)
    if match_3aa:
        ref3, pos, alt3 = match_3aa.groups()
        ref1 = AA_3_TO_1.get(ref3.upper(), "")
        alt1 = AA_3_TO_1.get(alt3.upper(), "")
        if ref1 and alt1:
            return f"{ref1}{pos}{alt1}"

    # Check for standard 1-letter AA substitution pattern like L858R or V600E
    match_1aa = re.match(r"^([A-Z])(\d+)([A-Z\*])$", clean, re.IGNORECASE)
    if match_1aa:
        ref1, pos, alt1 = match_1aa.groups()
        return f"{ref1.upper()}{pos}{alt1.upper()}"

    # Common structural/consequence terms
    upper = clean.upper()
    if "AMP" in upper:
        return "AMPLIFICATION"
    if "FUS" in upper:
        return clean.upper()

    return clean.upper()


def normalize_disease(disease: str) -> str:
    """Normalize disease name into canonical ontology representation."""
    if not disease:
        return ""
    clean = disease.strip()

    # Direct match or upper lookup
    upper = clean.upper()
    if upper in DISEASE_SYNONYMS:
        return DISEASE_SYNONYMS[upper]

    # Fuzzy clean string (remove extra spaces and punctuation)
    simplified = re.sub(r"[\-\_\,\.]", " ", upper)
    simplified = re.sub(r"\s+", " ", simplified).strip()
    if simplified in DISEASE_SYNONYMS:
        return DISEASE_SYNONYMS[simplified]

    # Capitalize title case fallback
    return clean.title()


def normalize_payload(data: dict[str, str]) -> dict[str, str]:
    """Normalize an incoming API mutation payload dict."""
    return {
        "gene": normalize_gene(data.get("gene", "")),
        "variant": normalize_variant(data.get("variant", "")),
        "disease": normalize_disease(data.get("disease", "")),
    }
