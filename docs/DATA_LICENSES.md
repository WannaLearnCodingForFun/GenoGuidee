# GenoGuide — External Data Licenses & Compliance

Policy: raw datasets are **never committed to git**. The repo commits the
manifest (`research/data/manifest.yaml`), download scripts, and checksum
receipts (`DATASET_INFO.json`, written next to each download). Consult each
license before any commercial use or redistribution.

| Dataset | Source | License | Usage in GenoGuide | Redistribution | Citation |
|---|---|---|---|---|---|
| ClinVar (variant_summary, VCF) | NCBI | Public domain (US gov.) | Clinical labels + review-status confidence tiers | OK, but we still don't commit data | Landrum et al., NAR, doi:10.1093/nar/gkx1153 |
| HPO (hp.obo, phenotype.hpoa, genes_to_phenotype) | JAX/Monarch | Free with attribution; terms must not be altered | Phenotype ontology, IC-based similarity | Allowed with attribution | Köhler et al., NAR, doi:10.1093/nar/gkaa1043 |
| gnomAD v4.1 constraint metrics | Broad Institute | CC0 | Gene-level features (LOEUF, pLI, mis-z) | Allowed | Chen et al., Nature 2024, doi:10.1038/s41586-023-06045-0 |
| ClinGen gene-disease validity | ClinGen | CC0 1.0 | Gene-disease validity features + KG edges | Allowed | Rehm et al., NEJM 2015, doi:10.1056/NEJMsr1406261 |
| AlphaMissense (precomputed) | DeepMind via Zenodo | **CC BY-NC-SA 4.0 (non-commercial)** | External feature / baseline / ablation only — never retrained by us | **Do not redistribute in repo; non-commercial only** | Cheng et al., Science 2023, doi:10.1126/science.adg7492 |
| REVEL v1.3 | Ioannidis et al. | Free for non-commercial research | Missense feature / baseline / ablation | Check terms; not committed | Ioannidis et al., AJHG 2016, doi:10.1016/j.ajhg.2016.08.016 |
| SpliceAI precomputed scores | Illumina | Free academic; **registration required** | Splice features | Not redistributable; user must fetch | Jaganathan et al., Cell 2019, doi:10.1016/j.cell.2018.12.015 |
| CADD v1.7 | UW/Hudson-Alpha | Free non-commercial; commercial requires license | Optional predictive feature | Not redistributable | Rentzsch et al., NAR 2019, doi:10.1093/nar/gky1016 |
| gnomAD sites (per-variant AF) | Broad Institute | CC0 | Population evidence (via connector; TB-scale, not fetched) | Allowed but impractical | Chen et al., Nature 2024 |
| OMIM / GeneReviews / DisGeNET / PharmGKB | various | **Restrictive/registration licenses** | NOT INTEGRATED — optional connector points only | Not permitted without agreements | — |

Compliance rules encoded in the tooling:

1. `cli.genoguide data download` refuses datasets marked `auto_downloadable: false`
   and prints the acquisition instructions instead.
2. Every download writes a receipt with SHA-256, size, URL, license and date;
   `data verify` recomputes checksums.
3. `.gitignore` excludes `research/data/raw|interim|processed|external_holdout`.
4. AlphaMissense's non-commercial clause means any commercial deployment of
   GenoGuide must exclude AlphaMissense features or obtain separate rights;
   ablation results quantify exactly what would be lost.
