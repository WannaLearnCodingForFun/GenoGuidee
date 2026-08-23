"""
Map ClinVar variants (clinvar_panel_with_coords.csv) to HPO phenotype terms
via disease IDs (OMIM first, Orphanet as fallback) present in the
disease_db_xrefs column.

Requires: data/knowledge/phenotype.hpoa (downloaded from HPO releases)
Input:    data/knowledge/clinvar_panel_with_coords.csv
Output:   data/knowledge/clinvar_panel_with_hpo.csv (adds hpo_terms, hpo_source_id columns)
"""
import csv
import re
from collections import defaultdict

HPOA_PATH = "data/knowledge/phenotype.hpoa"
IN_PATH = "data/knowledge/clinvar_panel_with_coords.csv"
OUT_PATH = "data/knowledge/clinvar_panel_with_hpo.csv"


def load_hpoa(path):
    """
    Build database_id -> set of hpo_id from phenotype.hpoa.
    File has '#' comment lines, then a tab-separated header, then data.
    database_id values include both 'OMIM:xxxxx' and 'ORPHA:xxxxx'.
    Skips rows where qualifier == 'NOT' (negative annotation).
    """
    id_to_hpo = defaultdict(set)
    with open(path, encoding="utf-8") as f:
        header = None
        idx = {}
        for line in f:
            if line.startswith("#"):
                continue
            row = line.rstrip("\n").split("\t")
            if header is None:
                header = row
                idx = {name: i for i, name in enumerate(header)}
                continue
            if len(row) <= max(idx.get("database_id", 0), idx.get("hpo_id", 0)):
                continue
            db_id = row[idx["database_id"]]
            hpo_id = row[idx["hpo_id"]]
            qualifier = row[idx.get("qualifier", -1)] if "qualifier" in idx else ""
            if qualifier == "NOT":
                continue
            if db_id.startswith("OMIM:") or db_id.startswith("ORPHA:"):
                id_to_hpo[db_id].add(hpo_id)
    return id_to_hpo


def extract_omim(xref_str):
    m = re.search(r"OMIM:(\d+)", xref_str or "")
    return f"OMIM:{m.group(1)}" if m else None


def extract_orphanet(xref_str):
    """Pull 'Orphanet:586' -> 'ORPHA:586' (HPO's file uses the ORPHA: prefix,
    ClinVar's uses Orphanet: — same numeric ID, different prefix)."""
    m = re.search(r"Orphanet:(\d+)", xref_str or "")
    return f"ORPHA:{m.group(1)}" if m else None


def main():
    id_to_hpo = load_hpoa(HPOA_PATH)
    print(f"Loaded HPO annotations for {len(id_to_hpo)} disease entries (OMIM + Orphanet)")

    with open(IN_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys())
    if "hpo_terms" not in fieldnames:
        fieldnames += ["hpo_terms", "hpo_source_id"]

    omim_matched = 0
    orphanet_matched = 0
    unmatched = 0

    for row in rows:
        xref_str = row.get("disease_db_xrefs", "")
        omim_id = extract_omim(xref_str)
        hpo_ids = id_to_hpo.get(omim_id, set()) if omim_id else set()
        source_id = omim_id if hpo_ids else None

        if not hpo_ids:
            orphanet_id = extract_orphanet(xref_str)
            hpo_ids = id_to_hpo.get(orphanet_id, set()) if orphanet_id else set()
            source_id = orphanet_id if hpo_ids else None

        row["hpo_terms"] = "; ".join(sorted(hpo_ids))
        row["hpo_source_id"] = source_id or ""

        if hpo_ids and source_id and source_id.startswith("OMIM"):
            omim_matched += 1
        elif hpo_ids and source_id and source_id.startswith("ORPHA"):
            orphanet_matched += 1
        else:
            unmatched += 1

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    total = len(rows)
    print(f"Matched via OMIM: {omim_matched}/{total}")
    print(f"Matched via Orphanet (fallback): {orphanet_matched}/{total}")
    print(f"Still unmatched: {unmatched}/{total}")
    print(f"Wrote -> {OUT_PATH}")


if __name__ == "__main__":
    main()
