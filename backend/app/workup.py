"""
Clinical workup: the end-to-end flow from a patient's history + a variant to
a medication shortlist.

Stage order is deliberate and matches the clinical reasoning order:

    1. INTAKE          past medical history + the variant under review
    2. TRIPLE          resolve (gene, variant, disease) — the three keys every
                       downstream layer needs
    3. CLASSIFICATION  ACMG rule engine and the ML model run INDEPENDENTLY
    4. RECONCILIATION  concordant / discordant; ACMG is always authoritative
    5. MEDICATION      therapy ranking, gated on the reconciliation outcome

The gating in stage 5 is the important part. Therapy is advisory context that
runs *after* classification and never feeds back into it. A benign variant
gets no therapy shortlist, and a discordant call carries a human-review flag
into the medication stage rather than being presented as settled.
"""
from __future__ import annotations

from typing import Any, Optional

from .clinical import _GENE_DISEASE

# ---------------------------------------------------------------------------
# Past medical history -> structured context
# ---------------------------------------------------------------------------

# Free-text phenotype/condition terms mapped onto the keyword vocabulary that
# _GENE_DISEASE already uses for gene-phenotype overlap. Keeping this table
# small and explicit is deliberate: silently fuzzy-matching a patient's
# history to a disease gene is exactly the kind of guess this system avoids.
_PHENOTYPE_KEYWORDS: dict[str, list[str]] = {
    "breast": ["breast", "mammary", "ductal carcinoma", "lobular carcinoma"],
    "ovarian": ["ovarian", "ovary", "fallopian"],
    "colorectal": ["colorectal", "colon", "rectal", "bowel", "polyps", "polyposis"],
    "endometrial": ["endometrial", "uterine", "uterus"],
    "pancreatic": ["pancreatic", "pancreas", "pancreatitis", "pancreatic insufficiency"],
    "lung": ["lung", "pulmonary", "sinopulmonary", "bronchiectasis", "nsclc"],
    "respiratory": ["respiratory", "recurrent infection", "chronic cough", "sinusitis"],
    "cardiomyopathy": ["cardiomyopathy", "hypertrophic", "septal", "heart failure"],
    "cardiac": ["cardiac", "arrhythmia", "sudden cardiac death", "palpitations", "syncope"],
    "ekg": ["ekg", "ecg", "qt", "conduction"],
    "cholesterol": ["cholesterol", "hyperlipid", "hypercholesterol", "ldl", "xanthoma"],
    "lipid": ["lipid", "statin", "triglyceride"],
    "hearing": ["hearing", "deaf", "hearing loss", "sensorineural"],
    "sarcoma": ["sarcoma", "osteosarcoma", "soft tissue tumour", "soft tissue tumor"],
    "cancer": ["cancer", "carcinoma", "tumour", "tumor", "malignancy", "neoplasm"],
}


def _match_keywords(history_text: str) -> list[str]:
    """Which _GENE_DISEASE keywords the patient's history supports."""
    text = history_text.lower()
    hits: list[str] = []
    for keyword, synonyms in _PHENOTYPE_KEYWORDS.items():
        if any(s in text for s in synonyms):
            hits.append(keyword)
    return hits


def summarize_history(history: dict[str, Any]) -> dict[str, Any]:
    """Flatten the intake form into the text + flags the later stages use."""
    parts: list[str] = []
    for key in ("diagnosis", "presenting_complaint", "family_details"):
        value = history.get(key)
        if value:
            parts.append(str(value))
    for key in ("phenotypes", "prior_conditions", "medications"):
        values = history.get(key) or []
        parts.extend(str(v) for v in values if v)

    joined = " ".join(parts)
    return {
        "text": joined,
        "keywords": _match_keywords(joined),
        "age": history.get("age"),
        "sex": history.get("sex"),
        "family_history_positive": bool(history.get("family_history_positive")),
        "phenotype_count": len(history.get("phenotypes") or []),
        "medication_count": len(history.get("medications") or []),
        "prior_condition_count": len(history.get("prior_conditions") or []),
    }


# ---------------------------------------------------------------------------
# Stage 2 — the (gene, variant, disease) triple
# ---------------------------------------------------------------------------

def resolve_triple(variant: dict[str, Any], history: dict[str, Any]) -> dict[str, Any]:
    """
    Produce the three keys the medication layer consumes.

    gene    comes from the variant annotation
    variant is the protein-change token, exact where HGVS.p allows it
    disease comes from the patient's stated diagnosis, falling back to the
            gene's curated association when the history does not name one
    """
    from .services.drug_recommendation import normalize_indication, protein_shorthand

    gene = (variant.get("gene") or "").upper() or None

    hgvs_p = variant.get("hgvs_p")
    exact_token = protein_shorthand(hgvs_p) if hgvs_p else None
    if exact_token:
        token, precision = exact_token, "EXACT"
        token_note = f"Protein change {hgvs_p} maps to {exact_token}."
    else:
        # Frameshifts, indels and coding-only HGVS have no single-residue
        # shorthand. The ranker still accepts the raw change and weights gene
        # and disease most heavily, so we pass what we have and say so.
        token = (hgvs_p or variant.get("hgvs_c") or variant.get("consequence") or "UNSPECIFIED")
        precision = "GENE_LEVEL"
        token_note = (
            f"{hgvs_p or variant.get('hgvs_c') or 'This change'} has no single-residue "
            "shorthand (frameshift, indel or coding-only HGVS). Ranking falls back to "
            "gene- and disease-level evidence."
        )

    stated = history.get("diagnosis") or history.get("oncology_indication")
    disease = normalize_indication(str(stated), passthrough=True) if stated else None
    disease_source = "patient history" if disease else None

    gene_info = _GENE_DISEASE.get(gene or "", {})
    if not disease and gene_info.get("disease"):
        disease = gene_info["disease"]
        disease_source = "curated gene-disease association (no diagnosis given)"

    return {
        "gene": gene,
        "variant": token,
        "variant_display": hgvs_p or variant.get("hgvs_c") or f"{variant.get('chrom')}:{variant.get('pos')}",
        "token_precision": precision,
        "token_note": token_note,
        "disease": disease,
        "disease_source": disease_source,
        "gene_disease": gene_info.get("disease"),
        "guideline": gene_info.get("guideline"),
        "complete": bool(gene and disease),
    }


# ---------------------------------------------------------------------------
# Stage 3/4 helpers — phenotype overlap between history and the gene
# ---------------------------------------------------------------------------

def phenotype_overlap(gene: Optional[str], summary: dict[str, Any]) -> dict[str, Any]:
    """Does the patient's history match what this gene actually causes?"""
    info = _GENE_DISEASE.get(gene or "", {})
    gene_keywords = info.get("keywords") or []
    if not gene_keywords:
        return {
            "status": "NO_CURATED_ASSOCIATION",
            "matched": [],
            "note": f"No curated phenotype keywords for {gene or 'this gene'} in the demo knowledge base.",
        }

    matched = sorted(set(gene_keywords) & set(summary["keywords"]))
    if matched:
        status = "SUPPORTED"
        note = (
            f"Patient history mentions {', '.join(matched)}, which overlaps the "
            f"presentation of {info.get('disease')}."
        )
    elif summary["keywords"]:
        status = "NO_OVERLAP"
        note = (
            f"History terms ({', '.join(summary['keywords'])}) do not overlap "
            f"{info.get('disease')}. The finding may be incidental to the presenting problem."
        )
    else:
        status = "NO_HISTORY"
        note = "No phenotype or condition terms were supplied, so overlap cannot be assessed."

    return {"status": status, "matched": matched, "gene_keywords": gene_keywords, "note": note}


# ---------------------------------------------------------------------------
# Stage 5 — medication, gated on the reconciliation outcome
# ---------------------------------------------------------------------------

ACTIONABLE = {"Pathogenic", "Likely Pathogenic"}


def medication_stage(
    triple: dict[str, Any],
    final_classification: str,
    reconciliation_status: str,
    human_review_required: bool,
) -> dict[str, Any]:
    """
    Rank therapies for the resolved triple — but only when the classification
    justifies it. Therapy never feeds back into ACMG; this stage only reads
    the verdict the earlier stages produced.
    """
    if not triple["complete"]:
        missing = "gene" if not triple["gene"] else "disease"
        return {
            "availability": "INSUFFICIENT_INPUT",
            "reason": f"Cannot rank therapy without a {missing}. "
                      f"{'Annotate the VCF with a gene symbol.' if missing == 'gene' else 'Record a diagnosis in the intake form.'}",
            "recommendations": [],
        }

    if final_classification not in ACTIONABLE:
        return {
            "availability": "NOT_INDICATED",
            "reason": (
                f"Final classification is {final_classification}. Per ACMG guidance a variant "
                "that is not pathogenic or likely pathogenic must not drive treatment "
                "selection, so no therapy shortlist is produced."
            ),
            "recommendations": [],
            "classification_gate": final_classification,
        }

    try:
        from recommendation.recommender import recommend_drugs
    except Exception as exc:  # noqa: BLE001 — module is optional at runtime
        return {
            "availability": "ENGINE_UNAVAILABLE",
            "reason": f"Drug recommendation engine not loaded: {exc}",
            "recommendations": [],
        }

    try:
        result = recommend_drugs({
            "gene": triple["gene"],
            "variant": triple["variant"],
            "disease": triple["disease"],
        })
    except Exception as exc:  # noqa: BLE001 — ranking failure must not break the workup
        return {
            "availability": "ENGINE_ERROR",
            "reason": f"Ranking failed: {exc}",
            "recommendations": [],
        }

    recommendations = result.get("recommendations", [])
    return {
        "availability": "AVAILABLE",
        "query": {"gene": triple["gene"], "variant": triple["variant"], "disease": triple["disease"]},
        "token_precision": triple["token_precision"],
        "recommendations": recommendations,
        "count": len(recommendations),
        "human_review_required": human_review_required,
        "reconciliation_status": reconciliation_status,
        "advisory": (
            "Ranked from curated variant-therapy evidence (CIViC / DGIdb). Gene and "
            "disease dominate the ranking; the specific protein change refines it. "
            "Decision support only — not a prescription, and it does not alter the "
            "ACMG classification above."
        ),
        "caution": (
            "AI and ACMG disagreed on this variant — treat the shortlist as provisional "
            "until a clinical molecular geneticist resolves the discordance."
            if human_review_required else None
        ),
    }


# ---------------------------------------------------------------------------
# Considerations drawn from the history (never evidence, always advisory)
# ---------------------------------------------------------------------------

def history_considerations(
    summary: dict[str, Any],
    overlap: dict[str, Any],
    triple: dict[str, Any],
    final_classification: str,
    history: dict[str, Any],
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    gene = triple.get("gene") or "this gene"

    if final_classification in ACTIONABLE:
        if triple.get("guideline"):
            out.append({
                "type": "guideline",
                "text": f"{final_classification} {gene} variant. Review applicable guidance: {triple['guideline']}.",
            })
        out.append({
            "type": "counseling",
            "text": "Consider genetic counseling and a cascade-testing discussion for at-risk relatives.",
        })

    if overlap["status"] == "SUPPORTED":
        out.append({"type": "phenotype", "text": overlap["note"]})
    elif overlap["status"] == "NO_OVERLAP" and final_classification in ACTIONABLE:
        out.append({
            "type": "caution",
            "text": overlap["note"] + " Consider whether this is a secondary finding rather than the cause of the presenting problem.",
        })

    if summary["family_history_positive"] and final_classification in ACTIONABLE:
        out.append({
            "type": "family",
            "text": "Positive family history recorded alongside an actionable variant — segregation "
                    "testing in affected relatives may strengthen the interpretation.",
        })

    if final_classification == "VUS":
        out.append({
            "type": "caution",
            "text": f"{gene} variant is of uncertain significance. Per ACMG guidance a VUS must not be "
                    "used for clinical decision-making; consider periodic reclassification review.",
        })

    for med in history.get("medications") or []:
        out.append({
            "type": "pgx",
            "text": f"Current medication recorded: {med}. Check CPIC/FDA pharmacogenomic guidance for "
                    "interactions with the patient's genotype.",
        })

    out.append({
        "type": "disclaimer",
        "text": "Decision-support output only — not a diagnosis and not a treatment recommendation. "
                "Final interpretation requires a qualified clinician and accredited laboratory confirmation.",
    })
    return out
