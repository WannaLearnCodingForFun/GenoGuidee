"""
GenoGuide demo dataset.

Variant-level evidence for the showcase variants is modeled on public knowledge
(ClinVar / literature) but simplified for a demo. All patient records are
SYNTHETIC and clearly flagged as such. Nothing here is real patient data.

The cohort is generated deterministically (seeded) so the demo is reproducible
and works fully offline.
"""
from __future__ import annotations

import json
import random
from typing import Any

from .config import DATA_DIR, RANDOM_SEED

# ---------------------------------------------------------------------------
# Curated showcase variants (public variant-level evidence, simplified)
# ---------------------------------------------------------------------------

SHOWCASE_VARIANTS: list[dict[str, Any]] = [
    {
        "id": "VAR-BRCA1-5266DUP",
        "gene": "BRCA1",
        "transcript": "NM_007294.4",
        "hgvs_c": "c.5266dupC",
        "hgvs_p": "p.(Gln1756ProfsTer74)",
        "chrom": "17",
        "pos": 43057062,
        "ref": "T",
        "alt": "TG",
        "consequence": "frameshift",
        "gnomad_af": 0.00003,
        "cadd": 33.0,
        "revel": None,
        "spliceai": 0.02,
        "phylop": 5.9,
        "lof_mechanism": True,
        "hotspot_domain": None,
        "functional_evidence": "damaging",
        "functional_source": "Homology-directed repair assay: complete loss of BRCA1 function (Findlay et al., saturation genome editing)",
        "segregation": False,
        "segregation_families": 0,
        "same_aa_pathogenic": False,
        "condition": "Hereditary breast and ovarian cancer syndrome",
        "inheritance": "Autosomal dominant",
        "esm_delta": 0.92,
        "showcase": True,
        "showcase_label": "BRCA1 c.5266dupC — founder frameshift",
        "public_note": "Well-characterized Ashkenazi founder pathogenic variant (ClinVar: Pathogenic, multiple expert panel reviews).",
        "demo_probs": {"pathogenic": 0.914, "likely_pathogenic": 0.062, "vus": 0.018, "likely_benign": 0.004, "benign": 0.002},
    },
    {
        "id": "VAR-TP53-R158H",
        "gene": "TP53",
        "transcript": "NM_000546.6",
        "hgvs_c": "c.473G>A",
        "hgvs_p": "p.(Arg158His)",
        "chrom": "17",
        "pos": 7675139,
        "ref": "C",
        "alt": "T",
        "consequence": "missense",
        "gnomad_af": 0.0,
        "cadd": 29.1,
        "revel": 0.83,
        "spliceai": 0.01,
        "phylop": 7.5,
        "lof_mechanism": False,
        "hotspot_domain": None,
        "functional_evidence": None,
        "functional_source": None,
        "segregation": False,
        "segregation_families": 0,
        "same_aa_pathogenic": False,
        "condition": "Li-Fraumeni spectrum (demo VUS case)",
        "inheritance": "Autosomal dominant",
        "esm_delta": 0.71,
        "showcase": True,
        "showcase_label": "TP53 demo VUS — AI/ACMG discordance case",
        "public_note": "Demo VUS: strong in-silico signal but no functional or segregation evidence. Designed to show the platform refusing to let ML override ACMG.",
        "demo_probs": {"pathogenic": 0.26, "likely_pathogenic": 0.52, "vus": 0.17, "likely_benign": 0.04, "benign": 0.01},
    },
    {
        "id": "VAR-CFTR-F508DEL",
        "gene": "CFTR",
        "transcript": "NM_000492.4",
        "hgvs_c": "c.1521_1523del",
        "hgvs_p": "p.(Phe508del)",
        "chrom": "7",
        "pos": 117559590,
        "ref": "ATCT",
        "alt": "A",
        "consequence": "inframe_deletion",
        "gnomad_af": 0.0071,
        "cadd": 27.4,
        "revel": None,
        "spliceai": 0.03,
        "phylop": 6.1,
        "lof_mechanism": True,
        "hotspot_domain": "NBD1 nucleotide-binding domain",
        "functional_evidence": "damaging",
        "functional_source": "CFTR folding/trafficking assays: misfolded protein degraded before reaching cell membrane",
        "segregation": True,
        "segregation_families": 30,
        "same_aa_pathogenic": False,
        "condition": "Cystic fibrosis",
        "inheritance": "Autosomal recessive",
        "esm_delta": 0.84,
        "showcase": True,
        "showcase_label": "CFTR p.Phe508del — classic in-frame deletion",
        "public_note": "Most common CF-causing variant worldwide (ClinVar: Pathogenic). Note: too frequent for PM2 — the engine handles recessive carrier frequency correctly.",
        "demo_probs": {"pathogenic": 0.881, "likely_pathogenic": 0.083, "vus": 0.027, "likely_benign": 0.006, "benign": 0.003},
    },
    {
        "id": "VAR-MLH1-T117M",
        "gene": "MLH1",
        "transcript": "NM_000249.4",
        "hgvs_c": "c.350C>T",
        "hgvs_p": "p.(Thr117Met)",
        "chrom": "3",
        "pos": 37000970,
        "ref": "C",
        "alt": "T",
        "consequence": "missense",
        "gnomad_af": 0.000006,
        "cadd": 28.3,
        "revel": 0.92,
        "spliceai": 0.02,
        "phylop": 7.8,
        "lof_mechanism": True,
        "hotspot_domain": "ATPase domain",
        "functional_evidence": "damaging",
        "functional_source": "In-vitro mismatch repair assay: loss of MMR activity",
        "segregation": True,
        "segregation_families": 6,
        "same_aa_pathogenic": False,
        "condition": "Lynch syndrome",
        "inheritance": "Autosomal dominant",
        "esm_delta": 0.79,
        "showcase": True,
        "showcase_label": "MLH1 p.Thr117Met — Lynch syndrome missense",
        "public_note": "Recurrent Lynch syndrome variant with functional MMR-deficiency evidence (ClinVar: Pathogenic).",
        "demo_probs": {"pathogenic": 0.842, "likely_pathogenic": 0.117, "vus": 0.031, "likely_benign": 0.007, "benign": 0.003},
    },
    {
        "id": "VAR-MYH7-R403Q",
        "gene": "MYH7",
        "transcript": "NM_000257.4",
        "hgvs_c": "c.1208G>A",
        "hgvs_p": "p.(Arg403Gln)",
        "chrom": "14",
        "pos": 23429279,
        "ref": "C",
        "alt": "T",
        "consequence": "missense",
        "gnomad_af": 0.0,
        "cadd": 26.9,
        "revel": 0.88,
        "spliceai": 0.01,
        "phylop": 6.7,
        "lof_mechanism": False,
        "hotspot_domain": "Myosin motor (head) domain",
        "functional_evidence": None,
        "functional_source": None,
        "segregation": True,
        "segregation_families": 9,
        "same_aa_pathogenic": False,
        "condition": "Hypertrophic cardiomyopathy",
        "inheritance": "Autosomal dominant",
        "esm_delta": 0.74,
        "showcase": True,
        "showcase_label": "MYH7 p.Arg403Gln — HCM hotspot missense",
        "public_note": "Classic hypertrophic cardiomyopathy variant in the myosin head domain with strong family segregation data.",
        "demo_probs": {"pathogenic": 0.281, "likely_pathogenic": 0.553, "vus": 0.132, "likely_benign": 0.024, "benign": 0.010},
    },
    {
        "id": "VAR-LDLR-W23X",
        "gene": "LDLR",
        "transcript": "NM_000527.5",
        "hgvs_c": "c.68G>A",
        "hgvs_p": "p.(Trp23Ter)",
        "chrom": "19",
        "pos": 11089435,
        "ref": "G",
        "alt": "A",
        "consequence": "nonsense",
        "gnomad_af": 0.000008,
        "cadd": 38.0,
        "revel": None,
        "spliceai": 0.02,
        "phylop": 7.1,
        "lof_mechanism": True,
        "hotspot_domain": None,
        "functional_evidence": None,
        "functional_source": None,
        "segregation": False,
        "segregation_families": 0,
        "same_aa_pathogenic": False,
        "condition": "Familial hypercholesterolemia",
        "inheritance": "Autosomal dominant",
        "esm_delta": 0.89,
        "showcase": True,
        "showcase_label": "LDLR p.Trp23Ter — FH nonsense (secondary finding)",
        "public_note": "Loss-of-function LDLR variant; familial hypercholesterolemia is on the ACMG secondary-findings gene list.",
        "demo_probs": {"pathogenic": 0.897, "likely_pathogenic": 0.071, "vus": 0.024, "likely_benign": 0.005, "benign": 0.003},
    },
    {
        "id": "VAR-BRCA2-N372H",
        "gene": "BRCA2",
        "transcript": "NM_000059.4",
        "hgvs_c": "c.1114A>C",
        "hgvs_p": "p.(Asn372His)",
        "chrom": "13",
        "pos": 32332592,
        "ref": "A",
        "alt": "C",
        "consequence": "missense",
        "gnomad_af": 0.27,
        "cadd": 8.2,
        "revel": 0.09,
        "spliceai": 0.0,
        "phylop": 0.4,
        "lof_mechanism": True,
        "hotspot_domain": None,
        "functional_evidence": "benign",
        "functional_source": "Common polymorphism; no functional impact in HDR assays",
        "segregation": False,
        "segregation_families": 0,
        "same_aa_pathogenic": False,
        "condition": "None (common polymorphism)",
        "inheritance": "—",
        "esm_delta": 0.08,
        "showcase": True,
        "showcase_label": "BRCA2 p.Asn372His — common benign polymorphism",
        "public_note": "Common polymorphism (gnomAD AF ~27%). Demonstrates BA1 stand-alone benign classification and noise filtering.",
        "demo_probs": {"pathogenic": 0.004, "likely_pathogenic": 0.009, "vus": 0.028, "likely_benign": 0.061, "benign": 0.898},
    },
    {
        "id": "VAR-GJB2-35DELG",
        "gene": "GJB2",
        "transcript": "NM_004004.6",
        "hgvs_c": "c.35delG",
        "hgvs_p": "p.(Gly12ValfsTer2)",
        "chrom": "13",
        "pos": 20189547,
        "ref": "AC",
        "alt": "A",
        "consequence": "frameshift",
        "gnomad_af": 0.0079,
        "cadd": 26.1,
        "revel": None,
        "spliceai": 0.01,
        "phylop": 3.2,
        "lof_mechanism": True,
        "hotspot_domain": None,
        "functional_evidence": "damaging",
        "functional_source": "Connexin-26 channel assays: absent gap-junction activity",
        "segregation": True,
        "segregation_families": 40,
        "same_aa_pathogenic": False,
        "condition": "Autosomal recessive nonsyndromic hearing loss (DFNB1)",
        "inheritance": "Autosomal recessive",
        "esm_delta": 0.87,
        "showcase": True,
        "showcase_label": "GJB2 c.35delG — recessive frameshift",
        "public_note": "Most common cause of autosomal recessive nonsyndromic hearing loss in many populations (ClinVar: Pathogenic).",
        "demo_probs": {"pathogenic": 0.869, "likely_pathogenic": 0.094, "vus": 0.028, "likely_benign": 0.006, "benign": 0.003},
    },
]

# ---------------------------------------------------------------------------
# Generated cohort (deterministic, seeded)
# ---------------------------------------------------------------------------

_COHORT_GENES = [
    ("BRCA1", "17", True), ("BRCA2", "13", True), ("TP53", "17", False),
    ("MLH1", "3", True), ("MSH2", "2", True), ("APC", "5", True),
    ("CFTR", "7", True), ("MYH7", "14", False), ("MYBPC3", "11", True),
    ("LDLR", "19", True), ("PCSK9", "1", False), ("SCN5A", "3", False),
    ("KCNQ1", "11", False), ("PTEN", "10", True), ("PALB2", "16", True),
    ("ATM", "11", True), ("CHEK2", "22", True), ("RET", "10", False),
    ("VHL", "3", True), ("FBN1", "15", True), ("COL3A1", "2", False),
    ("DSP", "6", True), ("PKP2", "12", True), ("GJB2", "13", True),
    ("HBB", "11", False),
]

_AA3 = ["Ala", "Arg", "Asn", "Asp", "Cys", "Gln", "Glu", "Gly", "His", "Ile",
        "Leu", "Lys", "Met", "Phe", "Pro", "Ser", "Thr", "Trp", "Tyr", "Val"]

_CLASS_PLAN = (
    [("pathogenic", 17)] + [("likely_pathogenic", 17)] + [("vus", 44)]
    + [("likely_benign", 17)] + [("benign", 17)]
)


def _sample_variant(rng: random.Random, idx: int, target: str) -> dict[str, Any]:
    gene, chrom, lof = _COHORT_GENES[rng.randrange(len(_COHORT_GENES))]
    pos = rng.randrange(1_000_000, 120_000_000)
    aa_from, aa_to = rng.choice(_AA3), rng.choice(_AA3)
    aa_pos = rng.randrange(20, 1800)

    if target in ("pathogenic", "likely_pathogenic"):
        consequence = rng.choice(["nonsense", "frameshift", "missense", "missense", "splice_donor"])
        af = rng.choice([0.0, rng.uniform(0, 0.00008)])
        cadd = rng.uniform(24, 38)
        revel = rng.uniform(0.72, 0.98) if consequence == "missense" else None
        phylop = rng.uniform(4.5, 9.0)
        spliceai = rng.uniform(0.6, 0.95) if consequence == "splice_donor" else rng.uniform(0, 0.1)
        esm_delta = rng.uniform(0.62, 0.95)
        hotspot = rng.random() < 0.35
        functional = "damaging" if (target == "pathogenic" and rng.random() < 0.7) else None
        segregation = rng.random() < (0.5 if target == "pathogenic" else 0.3)
    elif target == "vus":
        consequence = rng.choice(["missense", "missense", "missense", "inframe_deletion", "synonymous"])
        af = rng.choice([0.0, rng.uniform(0, 0.0004)])
        cadd = rng.uniform(10, 27)
        revel = rng.uniform(0.25, 0.72) if consequence == "missense" else None
        phylop = rng.uniform(1.0, 6.0)
        spliceai = rng.uniform(0, 0.2)
        esm_delta = rng.uniform(0.25, 0.65)
        hotspot = rng.random() < 0.08
        functional = None
        segregation = False
    else:
        consequence = rng.choice(["missense", "synonymous", "synonymous", "intronic"])
        af = rng.uniform(0.005, 0.35) if target == "benign" else rng.uniform(0.002, 0.02)
        cadd = rng.uniform(0.5, 12)
        revel = rng.uniform(0.01, 0.2) if consequence == "missense" else None
        phylop = rng.uniform(-1.5, 1.5)
        spliceai = rng.uniform(0, 0.05)
        esm_delta = rng.uniform(0.02, 0.22)
        hotspot = False
        functional = "benign" if (target == "benign" and rng.random() < 0.4) else None
        segregation = False

    if consequence == "missense":
        hgvs_p = f"p.({aa_from}{aa_pos}{aa_to})"
        hgvs_c = f"c.{aa_pos * 3 - 1}{rng.choice('ACGT')}>{rng.choice('ACGT')}"
    elif consequence == "nonsense":
        hgvs_p = f"p.({aa_from}{aa_pos}Ter)"
        hgvs_c = f"c.{aa_pos * 3 - 2}{rng.choice('ACGT')}>{rng.choice('ACGT')}"
    elif consequence == "frameshift":
        hgvs_p = f"p.({aa_from}{aa_pos}fs)"
        hgvs_c = f"c.{aa_pos * 3}del"
    elif consequence == "inframe_deletion":
        hgvs_p = f"p.({aa_from}{aa_pos}del)"
        hgvs_c = f"c.{aa_pos * 3 - 2}_{aa_pos * 3}del"
    elif consequence == "splice_donor":
        hgvs_p = "p.(?)"
        hgvs_c = f"c.{aa_pos * 3}+1G>{rng.choice('ACT')}"
    else:
        hgvs_p = "p.(=)" if consequence == "synonymous" else "p.(?)"
        hgvs_c = f"c.{aa_pos * 3}{rng.choice('ACGT')}>{rng.choice('ACGT')}"

    return {
        "id": f"VAR-{gene}-{idx:04d}",
        "gene": gene,
        "transcript": f"NM_{rng.randrange(100000, 999999)}.{rng.randrange(1, 6)}",
        "hgvs_c": hgvs_c,
        "hgvs_p": hgvs_p,
        "chrom": chrom,
        "pos": pos,
        "ref": rng.choice("ACGT"),
        "alt": rng.choice("ACGT"),
        "consequence": consequence,
        "gnomad_af": round(af, 8),
        "cadd": round(cadd, 1),
        "revel": round(revel, 2) if revel is not None else None,
        "spliceai": round(spliceai, 2),
        "phylop": round(phylop, 1),
        "lof_mechanism": lof,
        "hotspot_domain": "Functional hotspot domain" if hotspot else None,
        "functional_evidence": functional,
        "functional_source": "Curated demo functional assay record" if functional else None,
        "segregation": segregation,
        "segregation_families": rng.randrange(3, 12) if segregation else 0,
        "same_aa_pathogenic": False,
        "condition": "Gene-associated condition (demo cohort)",
        "inheritance": "—",
        "esm_delta": round(esm_delta, 3),
        "showcase": False,
        "showcase_label": None,
        "public_note": "Synthetic demo-cohort variant (deterministically generated).",
        "demo_probs": None,
        "_target_hint": target,  # used only for XGBoost training-set generation
    }


def build_cohort() -> list[dict[str, Any]]:
    rng = random.Random(RANDOM_SEED)
    variants: list[dict[str, Any]] = []
    idx = 100
    for target, count in _CLASS_PLAN:
        for _ in range(count):
            variants.append(_sample_variant(rng, idx, target))
            idx += 1
    return variants


ALL_VARIANTS: list[dict[str, Any]] = SHOWCASE_VARIANTS + build_cohort()
VARIANTS_BY_ID: dict[str, dict[str, Any]] = {v["id"]: v for v in ALL_VARIANTS}

# Persist a copy for inspection / transparency.
_dump = [{k: v for k, v in var.items() if k != "_target_hint"} for var in ALL_VARIANTS]
(DATA_DIR / "variants.json").write_text(json.dumps(_dump, indent=2))

# ---------------------------------------------------------------------------
# Synthetic demo patients — clearly marked, never real data
# ---------------------------------------------------------------------------

PATIENTS: list[dict[str, Any]] = [
    {
        "id": "G-1027",
        "synthetic": True,
        "label": "SYNTHETIC DEMO PATIENT",
        "age": 47,
        "sex": "Female",
        "diagnosis": "Invasive ductal carcinoma of the breast (ER+/PR+, HER2−)",
        "diagnosis_short": "Breast cancer",
        "phenotypes": [
            {"hpo": "HP:0003002", "term": "Breast carcinoma"},
            {"hpo": "HP:0006625", "term": "Early-onset breast cancer"},
            {"hpo": "HP:0000006", "term": "Autosomal dominant family pattern"},
        ],
        "family_history": {
            "positive": True,
            "entries": [
                "Mother — breast cancer, diagnosed age 44",
                "Maternal aunt — ovarian cancer, diagnosed age 51",
                "Maternal grandmother — cancer of unknown primary, age 60s",
            ],
        },
        "medications": [
            {"name": "Tamoxifen", "dose": "20 mg daily", "pgx_gene": "CYP2D6", "pgx_note": "Prodrug activated by CYP2D6 — potential pharmacogenomic relevance detected."},
            {"name": "Ondansetron", "dose": "8 mg PRN", "pgx_gene": "CYP2D6", "pgx_note": "CYP2D6 ultrarapid metabolizers may have reduced antiemetic effect (CPIC guidance exists)."},
            {"name": "Sertraline", "dose": "50 mg daily", "pgx_gene": "CYP2C19", "pgx_note": "CPIC dosing guidance exists for CYP2C19 phenotypes."},
        ],
        "variant_ids": ["VAR-BRCA1-5266DUP", "VAR-TP53-R158H", "VAR-BRCA2-N372H"],
        "primary_variant_id": "VAR-BRCA1-5266DUP",
        "genome_stats": {"total_variants": 24812, "candidates": 1426, "annotated": 84, "prioritized": 7},
        "consent_scope": "Diagnostic germline analysis + secondary findings (ACMG SF list) — consented",
    },
    {
        "id": "G-2044",
        "synthetic": True,
        "label": "SYNTHETIC DEMO PATIENT",
        "age": 34,
        "sex": "Male",
        "diagnosis": "Chronic sinopulmonary disease with pancreatic insufficiency",
        "diagnosis_short": "Cystic fibrosis workup",
        "phenotypes": [
            {"hpo": "HP:0006528", "term": "Chronic lung disease"},
            {"hpo": "HP:0001738", "term": "Exocrine pancreatic insufficiency"},
            {"hpo": "HP:0011947", "term": "Recurrent respiratory infections"},
        ],
        "family_history": {
            "positive": False,
            "entries": ["No known family history of cystic fibrosis (consistent with recessive inheritance)"],
        },
        "medications": [
            {"name": "Pancrelipase", "dose": "with meals", "pgx_gene": None, "pgx_note": None},
            {"name": "Azithromycin", "dose": "500 mg 3×/week", "pgx_gene": None, "pgx_note": None},
            {"name": "Elexacaftor/Tezacaftor/Ivacaftor (candidate)", "dose": "—", "pgx_gene": "CFTR", "pgx_note": "CFTR modulator eligibility is genotype-dependent — potential pharmacogenomic relevance detected."},
        ],
        "variant_ids": ["VAR-CFTR-F508DEL", "VAR-GJB2-35DELG"],
        "primary_variant_id": "VAR-CFTR-F508DEL",
        "genome_stats": {"total_variants": 24391, "candidates": 1289, "annotated": 61, "prioritized": 4},
        "consent_scope": "Diagnostic germline analysis — consented; secondary findings declined",
    },
    {
        "id": "G-3311",
        "synthetic": True,
        "label": "SYNTHETIC DEMO PATIENT",
        "age": 52,
        "sex": "Male",
        "diagnosis": "Hypertrophic cardiomyopathy (septal thickness 21 mm)",
        "diagnosis_short": "Hypertrophic cardiomyopathy",
        "phenotypes": [
            {"hpo": "HP:0001639", "term": "Hypertrophic cardiomyopathy"},
            {"hpo": "HP:0001695", "term": "Cardiac arrest (family)"},
            {"hpo": "HP:0003115", "term": "Abnormal EKG"},
        ],
        "family_history": {
            "positive": True,
            "entries": [
                "Brother — sudden cardiac death, age 48",
                "Father — 'enlarged heart', died age 61",
            ],
        },
        "medications": [
            {"name": "Metoprolol", "dose": "100 mg daily", "pgx_gene": "CYP2D6", "pgx_note": "Metabolized by CYP2D6 — potential pharmacogenomic relevance detected."},
            {"name": "Atorvastatin", "dose": "40 mg daily", "pgx_gene": "SLCO1B1", "pgx_note": "SLCO1B1 variants influence statin myopathy risk (CPIC guidance exists)."},
        ],
        "variant_ids": ["VAR-MYH7-R403Q", "VAR-LDLR-W23X", "VAR-MLH1-T117M"],
        "primary_variant_id": "VAR-MYH7-R403Q",
        "genome_stats": {"total_variants": 25102, "candidates": 1502, "annotated": 77, "prioritized": 6},
        "consent_scope": "Diagnostic germline analysis + secondary findings (ACMG SF list) — consented",
    },
]

PATIENTS_BY_ID: dict[str, dict[str, Any]] = {p["id"]: p for p in PATIENTS}
