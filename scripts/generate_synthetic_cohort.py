"""
generate_synthetic_cohort.py -- builds a synthetic multi-ancestral cohort by
sampling genotypes per variant per ancestry using Hardy-Weinberg equilibrium.

THREE-TIER DATA SOURCE (each output row is tagged with which tier it came
from -- never silently blended):

  1. REAL gnomAD population AF, when available (fetched live, cached).
  2. LITERATURE FALLBACK carrier frequency, for genes where gnomAD has no
     coverage at all but a real published ancestry-specific carrier rate
     exists (see FALLBACK_CARRIER_FREQ below, each entry cited). Applied
     at the GENE level (one rate for the gene's most common pathogenic
     variant profile), not the individual-variant level, since that's
     what the literature actually reports.
  3. NO DATA -- gene/variant genuinely has neither. Reported explicitly,
     not silently dropped.

IMPORTANT CAVEAT: FALLBACK_CARRIER_FREQ below was researched independently
this session and has NOT been reconciled against carrier_screen.py's own
ancestry-frequency table (built earlier, contents not available when this
was written). If the two disagree, that's two sources of truth in the
codebase -- worth reconciling before this ships, not after.

Coverage of FALLBACK_CARRIER_FREQ is PARTIAL by design: only genes/
ancestries with a real, findable, cited published rate are included.
ATP7B, G6PD, BTD, GJB2, PAH have NO fallback entries here -- inventing
numbers for those without a real source would be fabrication, not a
fallback. They'll show 0 rows unless/until real numbers are sourced and
added.

Only SNVs (single-base ref/alt) are queried against gnomAD directly --
indels need proper VCF anchor-base normalization, not handled here (known
limitation, flagged in output). The literature fallback, being gene-level
rather than position-level, applies regardless of variant type.

Input:  data/knowledge/clinvar_panel_with_coords.csv
Cache:  data/knowledge/gnomad_af_cache.json  (created/reused automatically)
Output: data/knowledge/synthetic_cohort.csv  (long format: individual_id,
        ancestry, gene, variant_id, genotype, data_source)
"""
import csv
import json
import os
import time

from src.annotation.gnomad_client import fetch_gnomad_population_af, POPULATION_LABELS

IN_PATH = "data/knowledge/clinvar_panel_with_coords.csv"
CACHE_PATH = "data/knowledge/gnomad_af_cache.json"
OUT_PATH = "data/knowledge/synthetic_cohort.csv"

INDIVIDUALS_PER_ANCESTRY = 500
REQUEST_DELAY_SEC = 0.15  # be polite to gnomAD's free API

# ---------------------------------------------------------------------------
# Literature-sourced carrier frequency fallback, for genes with no gnomAD
# coverage. Keys are gnomAD's own ancestry bucket labels (afr, amr, asj,
# eas, fin, mid, nfe, sas, remaining) so this maps directly onto the same
# ancestry loop used for real gnomAD data. Every entry cited; genes/
# ancestries without a real found source are simply absent, not guessed.
# ---------------------------------------------------------------------------

FALLBACK_CARRIER_FREQ: dict[str, dict[str, float]] = {
    # Tay-Sachs. NEJM 1990 (Ashkenazi 1/27); general clinical genetics
    # literature (~1/250-300 general population, used here for nfe as a
    # conservative stand-in since most detailed general-population studies
    # are of European-descent cohorts).
    "HEXA": {
        "asj": 1 / 27,
        "nfe": 1 / 275,  # midpoint of cited 1/250-1/300 general-population range
    },
    # Canavan disease. Jewish Genetics Center (Ashkenazi 1/40; general
    # population 1/159).
    "ASPA": {
        "asj": 1 / 40,
        "nfe": 1 / 159,
    },
    # Gaucher disease type 1. Concordant across multiple sources (Ashkenazi
    # 1/15; Sephardic 1/125). No exact gnomAD "Sephardic" bucket exists --
    # NOT mapped to any gnomAD ancestry label here since "Sephardic Jewish"
    # doesn't correspond one-to-one with gnomAD's mid/remaining categories;
    # left out rather than force a questionable mapping.
    "GBA1": {
        "asj": 1 / 15,
    },
    # Familial Mediterranean Fever. ScienceDirect study, ~200 Ashkenazi
    # samples: 21% carrier frequency. CAVEAT flagged in the source itself:
    # reduced penetrance for the most common variant (E148Q) means this
    # high carrier rate does NOT translate proportionally to disease
    # incidence -- worth surfacing that caveat wherever this number is used
    # downstream, not just here.
    "MEFV": {
        "asj": 0.21,
    },
    # Spinal muscular atrophy. PMC study, >1000 samples per group, real
    # multi-ancestry breakdown -- the most complete fallback entry here.
    # Mapped: Caucasian->nfe, Ashkenazi Jewish->asj, Asian->eas (source
    # doesn't distinguish east/south Asian, mapped to eas as the more
    # commonly-implied default in US clinical literature -- flagged as an
    # approximation), African American->afr, Hispanic->amr.
    "SMN1": {
        "nfe": 1 / 37,
        "asj": 1 / 46,
        "eas": 1 / 56,
        "afr": 1 / 91,
        "amr": 1 / 125,
    },
    # ATP7B, G6PD, BTD, GJB2, PAH: NO fallback entries. Not found with
    # sufficient sourcing this session -- left absent rather than guessed.
}


def load_cache():
    if os.path.exists(CACHE_PATH):
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def save_cache(cache):
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def is_snv(row):
    ref, alt = row.get("ref", ""), row.get("alt", "")
    return bool(row.get("chrom")) and ref not in ("", "-") and alt not in ("", "-") \
        and len(ref) == 1 and len(alt) == 1


def variant_key(row):
    return f"{row['chrom']}-{row['pos']}-{row['ref']}-{row['alt']}"


def fetch_all_afs(rows):
    cache = load_cache()
    snv_rows = [r for r in rows if is_snv(r)]
    print(f"Total rows: {len(rows)} | SNVs eligible for gnomAD lookup: {len(snv_rows)} "
          f"(indels/CNVs/no-coords skipped -- literature fallback still applies to these by gene)")

    fetched, cached_hits, no_coverage = 0, 0, 0
    for i, row in enumerate(snv_rows):
        key = variant_key(row)
        if key in cache:
            cached_hits += 1
            continue
        chrom = row["chrom"].replace("chr", "")
        pop_af = fetch_gnomad_population_af(chrom, int(row["pos"]), row["ref"], row["alt"])
        cache[key] = pop_af  # may be None -- cached as such so we don't re-query
        fetched += 1
        if pop_af is None:
            no_coverage += 1
        if fetched % 25 == 0:
            print(f"  ...fetched {fetched}/{len(snv_rows) - cached_hits}")
            save_cache(cache)
        time.sleep(REQUEST_DELAY_SEC)

    save_cache(cache)
    print(f"Fetched fresh: {fetched} | From cache: {cached_hits} | "
          f"No gnomAD coverage: {no_coverage} (real absence -- consistent with "
          f"ACMG PM2 for rare pathogenic variants, not a bug)")
    return cache


def expected_counts(q, n):
    """Deterministic Hardy-Weinberg expected counts, rounded to nearest
    integer, instead of noisy per-individual random sampling."""
    p_het = 2 * q * (1 - q)
    p_hom = q ** 2
    return round(n * p_het), round(n * p_hom)


def main():
    with open(IN_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    af_cache = fetch_all_afs(rows)

    ancestries = list(POPULATION_LABELS.keys())
    print(f"Allocating deterministic expected counts across "
          f"{INDIVIDUALS_PER_ANCESTRY} x {len(ancestries)} ancestries")

    out_rows = []
    individual_counter = {anc: 0 for anc in ancestries}

    genes_seen = set()
    genes_with_any_data = set()
    genes_using_fallback = set()
    zero_expected = []  # (gene, variant_id, key, source) -- real rarity, reported not hidden

    for row in rows:
        gene = row["gene"]
        genes_seen.add(gene)
        key = variant_key(row) if is_snv(row) else None

        gnomad_af = af_cache.get(key) if key else None
        fallback_af = FALLBACK_CARRIER_FREQ.get(gene)

        any_representation = False
        for anc in ancestries:
            q, source = None, None
            if gnomad_af and gnomad_af.get(anc):
                q, source = gnomad_af[anc], "gnomad"
            elif fallback_af and fallback_af.get(anc):
                q, source = fallback_af[anc], "literature_fallback"

            if q is None or q == 0:
                continue

            n_het, n_hom = expected_counts(q, INDIVIDUALS_PER_ANCESTRY)
            if n_het == 0 and n_hom == 0:
                continue  # real rarity -- expected count rounds to 0

            any_representation = True
            genes_with_any_data.add(gene)
            if source == "literature_fallback":
                genes_using_fallback.add(gene)

            for genotype, count in ((1, n_het), (2, n_hom)):
                for _ in range(count):
                    individual_counter[anc] += 1
                    indiv_id = f"{anc}_{individual_counter[anc]:04d}"
                    out_rows.append({
                        "individual_id": indiv_id,
                        "ancestry": anc,
                        "gene": gene,
                        "variant_id": row["variant_id"],
                        "chrom": row.get("chrom", ""),
                        "pos": row.get("pos", ""),
                        "ref": row.get("ref", ""),
                        "alt": row.get("alt", ""),
                        "classification": row["classification"],
                        "genotype": genotype,
                        "data_source": source,
                    })

        if not any_representation and (gnomad_af or fallback_af):
            zero_expected.append((gene, row["variant_id"], key))

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        fieldnames = ["individual_id", "ancestry", "gene", "variant_id",
                      "chrom", "pos", "ref", "alt", "classification",
                      "genotype", "data_source"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(out_rows)

    print(f"\nWrote {len(out_rows)} carrier/homozygous genotype rows -> {OUT_PATH}")
    print(f"\nGene coverage: {len(genes_with_any_data)}/{len(genes_seen)} panel genes "
          f"produced at least one synthetic carrier")
    print(f"  via real gnomAD data: {sorted(genes_with_any_data - genes_using_fallback)}")
    print(f"  via literature fallback: {sorted(genes_using_fallback)}")
    no_data_genes = genes_seen - genes_with_any_data
    if no_data_genes:
        print(f"  NO data (neither gnomAD nor sourced fallback) -- 0 synthetic "
              f"carriers possible for these until real numbers are found: "
              f"{sorted(no_data_genes)}")

    if zero_expected:
        print(f"\n{len(zero_expected)} variant(s) had real frequency data but the "
              f"rate was too rare to expect ANY carrier at {INDIVIDUALS_PER_ANCESTRY} "
              f"individuals/ancestry (real rarity, not a bug):")
        for gene, variant_id, key in zero_expected[:20]:
            print(f"  {gene} {variant_id}")
        if len(zero_expected) > 20:
            print(f"  ...and {len(zero_expected) - 20} more")

    print("\n(Homozygous-reference genotypes omitted to keep file size manageable -- "
          "absence of an individual+variant pair means genotype 0.)")
    print("\nCAVEAT: literature fallback rates in this script have NOT been "
          "reconciled against carrier_screen.py's own ancestry-frequency table "
          "-- check for conflicting numbers before treating this as final.")


if __name__ == "__main__":
    main()
