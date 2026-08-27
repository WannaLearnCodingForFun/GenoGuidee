# GenoChain — ML Branch

Genomic variant pathogenicity classification with dual-path reconciliation
(ACMG rules engine + ML), family-aware carrier screening, trio de novo
detection, real mutation hotspot/path analysis, and retrieval-grounded
clinical summaries. Built on real ClinVar, 1000 Genomes, and AlphaMissense
data — not synthetic-only.

## What's in this branch

This branch contains the gene-mapping / coordinate-resolution / family-history
pipeline: real genomic coordinate resolution (ClinVar → VEP), position-exact
de novo variant matching, ancestry-aware carrier screening, real ClinVar
mutation hotspot detection, AlphaMissense-based heuristic mutation ordering,
and a retrieval-grounded (RAG) clinical summary generator — plus the FastAPI
endpoints exposing all of it.

---

## Setup

### 1. Install dependencies
```
pip install -r requirements.txt
```
(If no requirements.txt exists yet, core dependencies used here: `fastapi`,
`uvicorn`, `requests`, `duckdb`, `pydantic`.)

### 2. Fetch real data (one-time, in order)

```
python -m scripts.fetch_clinvar_panel
python -m scripts.vep_coordinate_lookup
```
This produces `data/knowledge/clinvar_panel.csv` and
`data/knowledge/clinvar_panel_with_coords.csv` — real ClinVar
pathogenic/likely-pathogenic variants across 12 recessive-disease panel
genes, with real genomic coordinates (GRCh38) resolved via Ensembl VEP.

### 3. (Optional) Build the AlphaMissense index

Only needed for `/family/mutation-path` (heuristic evolutionary ordering).
Everything else works without this step.

```
curl -L -o AlphaMissense_hg38.tsv.gz https://storage.googleapis.com/dm_alphamissense/AlphaMissense_hg38.tsv.gz
python -m scripts.setup_alphamissense_index
```
The first command downloads ~613MB (one time). The second slices it down to
just the panel genes' chromosomes and builds a local DuckDB index at
`data/processed/alphamissense.duckdb`. **This file and the raw download are
gitignored — do not commit them (600MB+, exceeds GitHub's file limits).**

### 4. Run the API
```
uvicorn src.api.main:app --reload
```
Interactive docs: `http://127.0.0.1:8000/docs`

---

## Endpoints

### `POST /recommend` — retrieval-grounded clinical summary

Retrieval-augmented summary built entirely from real, already-fetched data
(ClinVar classification/conditions/cross-references, published ancestry
carrier rates, real mutation hotspots). No free-generated clinical claims —
every line in the summary traces back to a specific retrieved field.

**Request:**
```json
{
  "gene": "CFTR",
  "variant_id": null,
  "ancestry": "ashkenazi_jewish",
  "summary_mode": true
}
```
- `gene` (required): gene symbol, e.g. `"CFTR"`
- `variant_id` (optional): specific ClinVar variant_id (c. notation). Omit for a gene-level query.
- `ancestry` (optional): one of `european`, `ashkenazi_jewish`, `african`, `hispanic`, `asian`, `mediterranean`. Adds a real published carrier-rate figure where available.
- `summary_mode` (optional, default `false`): if `true` and `variant_id` is omitted, returns aggregate counts instead of a full per-variant listing (recommended for genes with many entries).

**Response:**
```json
{
  "summary_text": "=== Retrieval-grounded summary: CFTR (Cystic fibrosis) ===\n\n50 ClinVar entries in local panel data for CFTR:\n  Likely Pathogenic: 39\n  Pathogenic: 11\n...",
  "gene": "CFTR",
  "disease": "Cystic fibrosis",
  "matched_variant_count": 50,
  "ancestry_rate": "1 in 24",
  "hotspot_positions": [15, 155, 1211]
}
```
Returns `404` if no ClinVar entries match the given gene/variant_id in local panel data.

---

### `POST /family/carrier-screen` — couple carrier screening

Checks whether both partners carry a pathogenic/likely-pathogenic variant in
the same recessive-disease gene (same variant, or compound heterozygous —
two different variants). Attaches real published ancestry-specific carrier
rates where available. Also reports near-miss genes (only one partner
carries) for transparency.

**Request:**
```json
{
  "partner_a_variants": [
    {"gene": "CFTR", "variant_id": "c.1521_1523delCTT", "classification": "Pathogenic"}
  ],
  "partner_b_variants": [
    {"gene": "CFTR", "variant_id": "c.1652G>A", "classification": "Pathogenic"}
  ],
  "ancestry": "ashkenazi_jewish"
}
```
- `classification`: one of `"Pathogenic"`, `"Likely Pathogenic"`, `"VUS"`, `"Benign"` (only pathogenic/likely-pathogenic trigger a flag)
- `ancestry`: optional, same labels as `/recommend`

**Response:**
```json
{
  "flagged_genes": [
    {
      "gene": "CFTR",
      "disease": "Cystic fibrosis",
      "partner_a_variant_ids": ["c.1521_1523delCTT"],
      "partner_b_variant_ids": ["c.1652G>A"],
      "compound_het": true,
      "recurrence_risk_pct": 25,
      "carrier_rate_context": "1 in 24"
    }
  ],
  "near_miss_genes": [],
  "screened_gene_count": 12,
  "network_graph": { "...": "pyvis-compatible node/edge JSON" }
}
```

---

### `POST /family/trio-phase` — trio de novo detection

Given a child's variants and both parents' variants, classifies each child
variant's origin (maternal / paternal / inherited from both / de novo).
De novo variants can be flagged high-priority if matched against a real,
position-exact ClinVar pathogenic lookup.

**Request:**
```json
{
  "child_variants": [
    {"chrom": "chr7", "pos": 117559590, "ref": "C", "alt": "T", "gene": "CFTR", "is_pathogenic": true}
  ],
  "mother_variants": [],
  "father_variants": []
}
```
- `is_pathogenic` (optional, per child variant): pass a real position-exact ClinVar match result if known — otherwise high-priority flagging is skipped for that variant.

**Response:**
```json
{
  "phased_variants": [
    {"gene": "CFTR", "chrom": "chr7", "pos": 117559590, "ref": "C", "alt": "T",
     "origin": "de novo", "is_pathogenic": true, "high_priority": true}
  ],
  "de_novo_count": 1,
  "high_priority_count": 1,
  "pedigree_graph": { "...": "pyvis-compatible node/edge JSON" }
}
```

---

### `GET /family/mutation-hotspots` — real recurring pathogenic positions

Aggregates real ClinVar pathogenic/likely-pathogenic variants by protein
position within one gene. Positions with 2+ independent variants are
returned as candidate hotspots. **Caveat (always returned):** this reflects
recurrence in ClinVar's curated submissions, not confirmed structural or
functional significance — ClinVar's own submission bias toward well-studied
positions is a real confound, not corrected for.

**Request:** query parameters, e.g.
```
GET /family/mutation-hotspots?gene=GBA1&min_count=2
```

**Response:**
```json
{
  "gene": "GBA1",
  "hotspots": [
    {"protein_pos": 234, "variant_count": 3,
     "variant_ids": ["c.700G>T", "c.700G>C", "c.700G>A"],
     "classifications": ["Pathogenic", "Pathogenic", "Likely Pathogenic"]}
  ],
  "caveat": "Hotspots reflect recurrence in ClinVar's curated pathogenic entries, not necessarily a structurally or functionally critical residue..."
}
```

---

### `GET /family/mutation-path` — AlphaMissense heuristic evolutionary path

Orders a gene's multi-hit variants by ascending AlphaMissense pathogenicity
score, as a heuristic "path of least resistance" toward the full combined
genotype. **Requires the AlphaMissense index to be built (see Setup step 3)
and at least 2 missense variants with a real score** — AlphaMissense only
scores missense substitutions, not indels/nonsense/splice-site changes,
which make up a large share of ClinVar panel entries.

**Important caveat (always returned in `caveat` field):** AlphaMissense
scores each substitution independently and has no epistasis model — this
ordering is a heuristic proxy, NOT a validated or literature-confirmed
evolutionary trajectory.

**Request:**
```
GET /family/mutation-path?gene=CFTR
```

**Response** (or `null` if fewer than 2 variants have a real score):
```json
{
  "gene": "CFTR",
  "final_variant_ids": ["c.44T>G", "c.3717G>C", "c.3310G>A", "c.3739G>C", "c.3909C>A"],
  "steps": [
    {"order": 1, "variant_id": "c.44T>G", "protein_pos": 15, "alphamissense_score": 0.624,
     "cumulative_label": "1 of 5 mutations acquired"}
  ],
  "caveat": "Heuristic ordering only: AlphaMissense scores each substitution independently and does not model epistasis between mutations..."
}
```

---

### `POST /variant/interpret`, `POST /variant/decision-map`

In Swagger UI, under POST /variant/interpret → "Try it out":

json
{
  "hgvs_notation": "NM_000492.4:c.1521_1523delCTT"
}

POST /variant/decision-map — same request body shape (hgvs_notation):

curl -X POST http://127.0.0.1:8000/variant/decision-map -H "Content-Type: application/json" -d "{\"hgvs_notation\": \"NM_000492.4:c.1521_1523delCTT\"}"
### `GET /ledger/verify`

Stubbed — Phase 4 (hash-chain audit ledger) not built in this branch.
Returns `501 Not Implemented`.

---

## Data sources & honesty notes

- **ClinVar panel** (`clinvar_panel.csv`, `clinvar_panel_with_coords.csv`):
  real data via NCBI E-utilities, 12 recessive-disease genes, ~550 variants.
  Includes real condition names and OMIM/MedGen/Orphanet cross-references
  (extracted from ClinVar's `germline_classification.trait_set`, not
  invented).
- **Genomic coordinates**: real, resolved via Ensembl VEP (GRCh38), ~425/428
  resolvable entries (remainder are CNV/structural variants or complex HGVS
  VEP's parser doesn't handle).
- **1000 Genomes trio data**: child (NA12878) genotypes are real, fetched
  directly from the 1000 Genomes phase 3 panel. **Parent genotypes are
  synthetic** — NA12878's real parents are not present in the phase 3
  "unrelated individuals" panel by design. This is clearly flagged in code
  and should be stated in any demo: "child genotypes real, parent genotypes
  simulated for demonstration."
- **Carrier-rate figures**: real, published population carrier-frequency
  estimates (the kind cited in ACOG/NIH/CDC carrier-screening guidance).
  Approximate and for demo/education context — not a substitute for
  individualized clinical carrier screening.
- **AlphaMissense scores**: real, from DeepMind's published precomputed
  scores, queried via local DuckDB index. Only covers missense
  substitutions.
- **Mutation hotspots / heuristic path**: real aggregation and real scores,
  but both come with explicit caveats (see endpoint docs above) about what
  they do and don't establish. Neither should be presented as validated
  functional or evolutionary claims.

## Known limitations

- No disease *prediction* (severity, onset, which specific disease a person
  will develop) is performed or claimed anywhere in this branch — only
  variant-to-condition association lookups from real curated sources.
- `/family/mutation-path` will return `null` for genes with fewer than 2
  scoreable missense variants, or if the AlphaMissense index hasn't been
  built.
- Review-status weighting (ClinVar confidence tiers) exists as a separate,
  independently-verified script but is not yet wired into the API responses
  in this branch.
