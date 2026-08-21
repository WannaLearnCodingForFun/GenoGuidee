"""
Deterministic ACMG/AMP (Richards et al. 2015) rule engine.

Every criterion is a pure Python function over structured variant annotations.
No ML and no LLM is involved anywhere in this module — the classification is
fully rule-based, auditable and reproducible.
"""
from __future__ import annotations

from typing import Any

PM2_AF_THRESHOLD = 0.0001
BS1_AF_THRESHOLD = 0.01
BA1_AF_THRESHOLD = 0.05

NULL_CONSEQUENCES = {"nonsense", "frameshift", "splice_donor", "splice_acceptor"}


def _crit(cid: str, name: str, strength: str, met: bool, reason: str, source: str) -> dict[str, Any]:
    return {
        "id": cid,
        "name": name,
        "strength": strength,
        "status": "MET" if met else "NOT_MET",
        "met": met,
        "reason": reason,
        "evidence_source": source,
    }


def evaluate_criteria(v: dict[str, Any]) -> list[dict[str, Any]]:
    af = v.get("gnomad_af") or 0.0
    cons = v.get("consequence")
    revel = v.get("revel")
    cadd = v.get("cadd") or 0.0
    phylop = v.get("phylop") or 0.0
    spliceai = v.get("spliceai") or 0.0

    out: list[dict[str, Any]] = []

    # --- Pathogenic evidence -------------------------------------------------
    pvs1 = cons in NULL_CONSEQUENCES and bool(v.get("lof_mechanism"))
    out.append(_crit(
        "PVS1", "Null variant in LOF-mechanism gene", "Very Strong", pvs1,
        f"Consequence is '{cons}'"
        + (" in a gene where loss of function is an established disease mechanism."
           if pvs1 else
           (" — not a null consequence." if cons not in NULL_CONSEQUENCES
            else " but loss of function is not an established mechanism for this gene.")),
        "Sequence annotation + curated LOF-mechanism gene list",
    ))

    ps1 = bool(v.get("same_aa_pathogenic"))
    out.append(_crit(
        "PS1", "Same amino-acid change as established pathogenic variant", "Strong", ps1,
        "A previously classified pathogenic variant produces the identical amino-acid change."
        if ps1 else "No established pathogenic variant with the same amino-acid change on record.",
        "Curated pathogenic variant registry (demo snapshot)",
    ))

    ps3 = v.get("functional_evidence") == "damaging"
    out.append(_crit(
        "PS3", "Well-established functional studies show damaging effect", "Strong", ps3,
        (v.get("functional_source") or "Functional assay demonstrates a deleterious effect.")
        if ps3 else "No well-established functional study demonstrating a damaging effect.",
        v.get("functional_source") or "Functional evidence registry (demo snapshot)",
    ))

    pm1 = bool(v.get("hotspot_domain"))
    out.append(_crit(
        "PM1", "Located in mutational hotspot / critical functional domain", "Moderate", pm1,
        f"Variant falls in {v.get('hotspot_domain')}." if pm1
        else "Not located in a known mutational hotspot or critical functional domain.",
        "Protein domain / hotspot annotation (demo snapshot)",
    ))

    pm2 = af < PM2_AF_THRESHOLD
    out.append(_crit(
        "PM2", "Absent / extremely rare in population databases", "Moderate", pm2,
        (f"gnomAD allele frequency {af:.2e} is below the {PM2_AF_THRESHOLD:.0e} rarity threshold."
         if af > 0 else "Absent from gnomAD population database.") if pm2
        else f"gnomAD allele frequency {af:.4f} exceeds the {PM2_AF_THRESHOLD:.0e} rarity threshold.",
        "gnomAD population frequency (demo snapshot)",
    ))

    pm4 = cons == "inframe_deletion"
    out.append(_crit(
        "PM4", "Protein length change (in-frame indel in non-repeat region)", "Moderate", pm4,
        "In-frame deletion alters protein length in a non-repeat region." if pm4
        else "No in-frame protein-length-changing event.",
        "Sequence annotation",
    ))

    pp1 = bool(v.get("segregation"))
    fams = v.get("segregation_families") or 0
    out.append(_crit(
        "PP1", "Co-segregation with disease in affected family members", "Supporting", pp1,
        f"Variant co-segregates with disease in {fams} reported famil{'ies' if fams != 1 else 'y'}."
        if pp1 else "No segregation data available.",
        "Family segregation studies (demo snapshot)",
    ))

    if cons == "missense" and revel is not None:
        pp3 = revel >= 0.7
        pp3_reason = (f"REVEL {revel:.2f} ≥ 0.70 with CADD {cadd:.1f} — concordant deleterious in-silico consensus."
                      if pp3 else f"REVEL {revel:.2f} below the 0.70 deleterious consensus threshold.")
    elif cons in ("splice_donor", "splice_acceptor") or spliceai >= 0.5:
        pp3 = spliceai >= 0.5
        pp3_reason = (f"SpliceAI Δ-score {spliceai:.2f} predicts splice disruption."
                      if pp3 else f"SpliceAI Δ-score {spliceai:.2f} below 0.50.")
    else:
        pp3 = cadd >= 24 and phylop >= 3.0
        pp3_reason = (f"CADD {cadd:.1f} ≥ 24 and phyloP {phylop:.1f} indicate strong deleteriousness/conservation."
                      if pp3 else f"CADD {cadd:.1f} / phyloP {phylop:.1f} do not reach the deleterious consensus threshold.")
    out.append(_crit(
        "PP3", "Multiple computational tools predict deleterious effect", "Supporting", pp3,
        pp3_reason, "REVEL / CADD / SpliceAI / phyloP (demo snapshot)",
    ))

    # --- Benign evidence -----------------------------------------------------
    ba1 = af > BA1_AF_THRESHOLD
    out.append(_crit(
        "BA1", "Allele frequency > 5% (stand-alone benign)", "Stand-alone", ba1,
        f"gnomAD allele frequency {af:.3f} exceeds 5% — incompatible with a highly penetrant monogenic disorder."
        if ba1 else f"gnomAD allele frequency {af:.2e} does not exceed 5%.",
        "gnomAD population frequency (demo snapshot)",
    ))

    bs1 = (not ba1) and af > BS1_AF_THRESHOLD
    out.append(_crit(
        "BS1", "Allele frequency greater than expected for disorder", "Strong (benign)", bs1,
        f"gnomAD allele frequency {af:.4f} exceeds the expected frequency for this disorder."
        if bs1 else "Allele frequency compatible with disease prevalence.",
        "gnomAD population frequency (demo snapshot)",
    ))

    bs3 = v.get("functional_evidence") == "benign"
    out.append(_crit(
        "BS3", "Functional studies show no damaging effect", "Strong (benign)", bs3,
        (v.get("functional_source") or "Functional assays show no deleterious effect.")
        if bs3 else "No functional study demonstrating a neutral effect.",
        v.get("functional_source") or "Functional evidence registry (demo snapshot)",
    ))

    bp4 = ((revel is not None and revel < 0.2) or (revel is None and cadd < 10)) and spliceai < 0.2 and phylop < 2.0
    out.append(_crit(
        "BP4", "Multiple computational tools predict benign effect", "Supporting (benign)", bp4,
        "In-silico consensus (REVEL/CADD/SpliceAI/phyloP) predicts no functional impact." if bp4
        else "In-silico consensus does not support a benign prediction.",
        "REVEL / CADD / SpliceAI / phyloP (demo snapshot)",
    ))

    bp7 = cons == "synonymous" and spliceai < 0.2 and phylop < 2.0
    out.append(_crit(
        "BP7", "Synonymous variant with no predicted splice impact", "Supporting (benign)", bp7,
        "Synonymous change at a non-conserved position with no predicted splice effect." if bp7
        else "Not a synonymous variant, or splice/conservation signal present.",
        "Sequence annotation + SpliceAI/phyloP",
    ))

    return out


def combine(criteria: list[dict[str, Any]]) -> dict[str, Any]:
    """ACMG/AMP 2015 evidence-combining rules."""
    met = {c["id"] for c in criteria if c["met"]}

    pvs = len(met & {"PVS1"})
    ps = len(met & {"PS1", "PS2", "PS3", "PS4"})
    pm = len(met & {"PM1", "PM2", "PM3", "PM4", "PM5", "PM6"})
    pp = len(met & {"PP1", "PP2", "PP3", "PP4", "PP5"})
    ba = len(met & {"BA1"})
    bs = len(met & {"BS1", "BS2", "BS3", "BS4"})
    bp = len(met & {"BP1", "BP2", "BP3", "BP4", "BP5", "BP6", "BP7"})

    pathogenic = (
        (pvs >= 1 and (ps >= 1 or pm >= 2 or (pm == 1 and pp == 1) or pp >= 2))
        or ps >= 2
        or (ps == 1 and (pm >= 3 or (pm == 2 and pp >= 2) or (pm == 1 and pp >= 4)))
    )
    likely_pathogenic = (
        (pvs == 1 and pm == 1)
        or (ps == 1 and 1 <= pm <= 2)
        or (ps == 1 and pp >= 2)
        or pm >= 3
        or (pm == 2 and pp >= 2)
        or (pm == 1 and pp >= 4)
    )
    benign = ba >= 1 or bs >= 2
    likely_benign = (bs == 1 and bp == 1) or bp >= 2 or (bs >= 1 and not benign)

    has_pathogenic_evidence = (pvs + ps + pm + pp) > 0
    has_benign_evidence = (ba + bs + bp) > 0

    if pathogenic and not has_benign_evidence:
        cls = "Pathogenic"
    elif benign and not has_pathogenic_evidence:
        cls = "Benign"
    elif likely_pathogenic and not has_benign_evidence:
        cls = "Likely Pathogenic"
    elif likely_benign and not has_pathogenic_evidence:
        cls = "Likely Benign"
    else:
        cls = "VUS"

    return {
        "classification": cls,
        "counts": {"PVS": pvs, "PS": ps, "PM": pm, "PP": pp, "BA": ba, "BS": bs, "BP": bp},
        "met_criteria": sorted(met),
        "rule_note": _rule_note(cls, pvs, ps, pm, pp, ba, bs, bp),
    }


def _rule_note(cls: str, pvs: int, ps: int, pm: int, pp: int, ba: int, bs: int, bp: int) -> str:
    parts = []
    if pvs: parts.append(f"{pvs}× Very Strong")
    if ps: parts.append(f"{ps}× Strong")
    if pm: parts.append(f"{pm}× Moderate")
    if pp: parts.append(f"{pp}× Supporting")
    if ba: parts.append(f"{ba}× Stand-alone benign")
    if bs: parts.append(f"{bs}× Strong benign")
    if bp: parts.append(f"{bp}× Supporting benign")
    evidence = " + ".join(parts) if parts else "no criteria met"
    return f"{cls} per ACMG/AMP 2015 combining rules ({evidence})."


def classify(variant: dict[str, Any]) -> dict[str, Any]:
    criteria = evaluate_criteria(variant)
    combined = combine(criteria)
    return {
        "criteria": criteria,
        "met": [c for c in criteria if c["met"]],
        **combined,
        "engine": "deterministic-rule-engine",
        "framework": "ACMG/AMP 2015 (Richards et al.)",
    }
