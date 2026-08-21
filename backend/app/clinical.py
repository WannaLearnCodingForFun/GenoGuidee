"""
Patient-context clinical decision support (Problem 60 downstream layer).

Produces a transparent, component-based Clinical Relevance Score plus
evidence-grounded, guideline-referencing considerations. Deliberately
non-diagnostic and non-prescriptive: wording is limited to "review guidelines",
"consider counseling/referral", "potential pharmacogenomic relevance".
"""
from __future__ import annotations

from typing import Any

from .acmg import classify
from .dataset import VARIANTS_BY_ID
from .ml import esm_representation, predict

_CLASS_BASE = {"Pathogenic": 40, "Likely Pathogenic": 34, "VUS": 15, "Likely Benign": 4, "Benign": 0}

_GENE_DISEASE = {
    "BRCA1": {"disease": "Hereditary breast and ovarian cancer", "keywords": ["breast", "ovarian"],
              "guideline": "NCCN Genetic/Familial High-Risk Assessment: Breast, Ovarian & Pancreatic"},
    "BRCA2": {"disease": "Hereditary breast and ovarian cancer", "keywords": ["breast", "ovarian"],
              "guideline": "NCCN Genetic/Familial High-Risk Assessment: Breast, Ovarian & Pancreatic"},
    "TP53": {"disease": "Li-Fraumeni syndrome spectrum", "keywords": ["breast", "sarcoma", "cancer"],
             "guideline": "NCCN Li-Fraumeni Syndrome Management"},
    "CFTR": {"disease": "Cystic fibrosis", "keywords": ["lung", "pancreatic", "respiratory", "sinopulmonary"],
             "guideline": "CF Foundation Clinical Care Guidelines / CFTR modulator therapy criteria"},
    "MLH1": {"disease": "Lynch syndrome", "keywords": ["colorectal", "endometrial", "cancer"],
             "guideline": "NCCN Genetic/Familial High-Risk Assessment: Colorectal"},
    "MYH7": {"disease": "Hypertrophic cardiomyopathy", "keywords": ["cardiomyopathy", "cardiac", "ekg"],
             "guideline": "AHA/ACC Hypertrophic Cardiomyopathy Guideline (2020)"},
    "LDLR": {"disease": "Familial hypercholesterolemia", "keywords": ["cholesterol", "cardiac", "lipid"],
             "guideline": "ACMG Secondary Findings v3.2 + AHA/ACC Cholesterol Guideline"},
    "GJB2": {"disease": "Nonsyndromic hearing loss (DFNB1)", "keywords": ["hearing"],
             "guideline": "ACMG Hearing Loss Clinical Practice Resource"},
}


def analyze_variant_for_patient(patient: dict[str, Any], variant_id: str) -> dict[str, Any]:
    variant = VARIANTS_BY_ID[variant_id]
    acmg = classify(variant)
    esm = esm_representation(variant)
    ml = predict(variant, esm["delta_score"])

    gene_info = _GENE_DISEASE.get(variant["gene"], {})
    diagnosis_text = (patient["diagnosis"] + " " + " ".join(p["term"] for p in patient["phenotypes"])).lower()

    # --- component scores (transparent, additive) ---------------------------
    significance = _CLASS_BASE.get(acmg["classification"], 0)

    matched_terms = [kw for kw in gene_info.get("keywords", []) if kw in diagnosis_text]
    phenotype_match = min(25, len(matched_terms) * 13) if matched_terms else 0

    disease_relevance = 15 if matched_terms else (6 if gene_info else 0)

    fh = patient["family_history"]["positive"]
    dominant = "dominant" in (variant.get("inheritance") or "").lower()
    family_component = 10 if (fh and dominant) else (5 if fh else 0)

    pgx_meds = [m for m in patient["medications"] if m.get("pgx_gene")]
    medication_component = min(10, len(pgx_meds) * 4)

    # Context components are dampened when the variant itself is not
    # actionable: a VUS or benign variant must not surface as high relevance
    # purely because the patient's phenotype matches the gene.
    damp = 1.0 if acmg["classification"] in ("Pathogenic", "Likely Pathogenic") else (
        0.6 if acmg["classification"] == "VUS" else 0.2)
    phenotype_match = round(phenotype_match * damp)
    disease_relevance = round(disease_relevance * damp)
    family_component = round(family_component * damp)
    medication_component = round(medication_component * damp)

    total = significance + phenotype_match + disease_relevance + family_component + medication_component
    level = "HIGH" if total >= 70 else ("MODERATE" if total >= 40 else "LOW")

    considerations = _considerations(variant, acmg, patient, gene_info, matched_terms, pgx_meds)

    return {
        "variant": variant,
        "acmg_classification": acmg["classification"],
        "acmg_met": acmg["met_criteria"],
        "ml_top_class": ml["top_class"],
        "ml_confidence": ml["confidence"],
        "phenotype_matched_terms": matched_terms,
        "gene_disease": gene_info.get("disease"),
        "guideline": gene_info.get("guideline"),
        "relevance": {
            "score": total,
            "level": level,
            "components": [
                {"name": "Variant significance (ACMG)", "value": significance, "max": 40},
                {"name": "Phenotype match", "value": phenotype_match, "max": 25},
                {"name": "Disease relevance", "value": disease_relevance, "max": 15},
                {"name": "Family history", "value": family_component, "max": 10},
                {"name": "Medication relevance", "value": medication_component, "max": 10},
            ],
        },
        "considerations": considerations,
    }


def _considerations(variant, acmg, patient, gene_info, matched_terms, pgx_meds) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    cls = acmg["classification"]
    gene = variant["gene"]

    if cls in ("Pathogenic", "Likely Pathogenic"):
        if gene_info.get("guideline"):
            out.append({
                "type": "guideline",
                "text": f"{cls} {gene} variant identified. Review applicable clinical guidelines: {gene_info['guideline']}.",
            })
        out.append({
            "type": "counseling",
            "text": "Consider genetic counseling for the patient and cascade testing discussion for at-risk relatives.",
        })
        if matched_terms:
            out.append({
                "type": "phenotype",
                "text": f"Variant-associated condition ({gene_info.get('disease')}) overlaps the documented phenotype ({', '.join(matched_terms)}). Consider whether this finding informs current management per guideline review.",
            })
    elif cls == "VUS":
        out.append({
            "type": "caution",
            "text": f"{gene} variant is of uncertain significance under ACMG/AMP criteria. Per ACMG guidance, a VUS should not be used for clinical decision-making. Consider periodic reclassification review and family segregation studies.",
        })
    else:
        out.append({
            "type": "info",
            "text": f"{gene} variant classified {cls}; no action indicated based on this variant.",
        })

    for m in pgx_meds:
        if m.get("pgx_note"):
            out.append({
                "type": "pgx",
                "text": f"{m['name']} ({m['pgx_gene']}): {m['pgx_note']} Review CPIC/FDA pharmacogenomic guidance.",
            })

    out.append({
        "type": "disclaimer",
        "text": "Decision-support output only — not a diagnosis and not a treatment recommendation. Final interpretation requires a qualified clinician and accredited laboratory confirmation.",
    })
    return out


def build_knowledge_graph(patient: dict[str, Any]) -> dict[str, Any]:
    nodes: list[dict[str, Any]] = []
    edges: list[dict[str, Any]] = []

    def add_node(nid: str, ntype: str, label: str, sub: str = "") -> str:
        if not any(n["id"] == nid for n in nodes):
            nodes.append({"id": nid, "type": ntype, "label": label, "sublabel": sub})
        return nid

    def add_edge(a: str, b: str, rel: str) -> None:
        edges.append({"source": a, "target": b, "relation": rel})

    pid = add_node(f"patient:{patient['id']}", "patient", patient["id"], "Synthetic demo patient")

    for ph in patient["phenotypes"]:
        phid = add_node(f"phenotype:{ph['hpo']}", "phenotype", ph["term"], ph["hpo"])
        add_edge(pid, phid, "exhibits")

    for vid in patient["variant_ids"]:
        v = VARIANTS_BY_ID[vid]
        acmg = classify(v)
        vnode = add_node(f"variant:{vid}", "variant", f"{v['gene']} {v['hgvs_c']}", acmg["classification"])
        add_edge(pid, vnode, "carries")

        gnode = add_node(f"gene:{v['gene']}", "gene", v["gene"], v["transcript"])
        add_edge(vnode, gnode, "in gene")

        info = _GENE_DISEASE.get(v["gene"])
        if info:
            dnode = add_node(f"disease:{v['gene']}", "disease", info["disease"], "")
            add_edge(gnode, dnode, "associated with")
            glnode = add_node(f"guideline:{v['gene']}", "guideline", info["guideline"].split("/")[0].strip(), "Clinical guideline")
            add_edge(dnode, glnode, "managed per")

            diagnosis_text = (patient["diagnosis"] + " " + " ".join(p["term"] for p in patient["phenotypes"])).lower()
            for ph in patient["phenotypes"]:
                if any(kw in ph["term"].lower() or kw in diagnosis_text for kw in info["keywords"]):
                    add_edge(dnode, f"phenotype:{ph['hpo']}", "manifests as")
                    break

        for c in acmg["met"][:3]:
            enode = add_node(f"evidence:{vid}:{c['id']}", "evidence", c["id"], c["strength"])
            add_edge(vnode, enode, "supported by")

    for m in patient["medications"]:
        if m.get("pgx_gene"):
            mnode = add_node(f"drug:{m['name']}", "drug", m["name"], f"PGx: {m['pgx_gene']}")
            add_edge(pid, mnode, "prescribed")
            gid = f"gene:{m['pgx_gene']}"
            if any(n["id"] == gid for n in nodes):
                add_edge(mnode, gid, "metabolized via")

    return {"nodes": nodes, "edges": edges, "patient_id": patient["id"]}
