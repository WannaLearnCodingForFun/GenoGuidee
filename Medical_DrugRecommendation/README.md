# Medical Drug Recommendation Engine

An isolated, clinical-grade precision medicine drug recommendation engine for **GenoGuide**. 

Given a patient's genomic mutation payload (`gene`, `variant`, `disease`), the engine queries CIViC clinical evidence and DGIdb drug-gene interaction databases, extracts multi-dimensional features, applies Machine Learning relevance ranking, and enforces deterministic clinical safety rules to output prioritized therapeutic drug recommendations.

---

## 🏗️ Module Architecture

```
Medical_DrugRecommendation/
│
├── Data/                                                     # Attached Knowledge Datasets
│   ├── categories.tsv                                        # DGIdb gene categories
│   ├── drugs.tsv                                             # DGIdb drug attributes & approvals
│   ├── genes.tsv                                             # DGIdb gene symbols
│   ├── interactions.tsv                                      # DGIdb gene-drug interaction records
│   ├── nightly-AcceptedClinicalEvidenceSummaries.tsv          # CIViC clinical evidence items
│   ├── nightly-AcceptedAssertionSummaries.tsv                 # CIViC clinical assertions
│   ├── nightly-FeatureSummaries.tsv                          # CIViC gene/feature summaries
│   ├── nightly-MolecularProfileSummaries.tsv                 # CIViC molecular profile records
│   ├── nightly-VariantSummaries.tsv                          # CIViC variant records
│   └── IntOGen-DriverGenes.tsv                               # IntOGen driver gene list
│
├── preprocessing/
│   ├── normalizer.py                                         # Normalizes HGNC symbols, AA variants (L858R), diseases
│   ├── civic_parser.py                                       # Vectorized parser for CIViC clinical evidence
│   └── dgidb_parser.py                                       # Vectorized parser for DGIdb interaction tables
│
├── recommendation/
│   ├── candidate_generator.py                                # Discovers candidate drugs from CIViC & DGIdb
│   ├── evidence_ranker.py                                    # Deterministic baseline evidence scorer (A-E levels)
│   ├── drug_ranker.py                                        # Hybrid ranker (ML prediction + clinical safety rules)
│   └── recommender.py                                        # End-to-end pipeline orchestrator
│
├── model/
│   ├── features.py                                           # 15-D feature extractor for candidate drugs
│   ├── train.py                                              # ML classifier training script
│   ├── evaluate.py                                           # Baseline vs ML vs Hybrid ranking matrix
│   └── model.pkl                                             # Persisted trained Gradient Boosting model
│
├── api/
│   └── routes.py                                             # FastAPI routes (POST /drug-recommendation)
│
├── tests/
│   ├── test_normalizer.py
│   ├── test_parsers.py
│   ├── test_candidate_generator.py
│   ├── test_evidence_ranker.py
│   ├── test_ml_model.py
│   └── test_api.py
│
├── requirements.txt
└── README.md
```

---

## ⚡ Data Pipeline & Decision Flow

```
               INPUT Payload: { "gene": "EGFR", "variant": "L858R", "disease": "NSCLC" }
                                         │
                                         ▼
                             Entity Normalization (normalizer.py)
                                         │
                                         ▼
                        Candidate Generator (candidate_generator.py)
                         ├── CIViC Variant-Disease Evidence Items
                         └── DGIdb Target-Drug Interaction Candidates
                                         │
                                         ▼
                        Feature Extractor (model/features.py)
                         ├── CIViC Evidence Count & Level Counts (A, B, C, D)
                         ├── Sensitivity & Resistance Ratios
                         └── DGIdb Approval, Antineoplastic, Inhibitor Scores
                                         │
                                         ▼
                     ML Relevance Prediction (model.pkl / train.py)
                                         │
                                         ▼
                    Deterministic Safety Override (drug_ranker.py)
                         ├── Resistance Penalty (Primary Resistance -> Penalized)
                         └── Evidence Level A/B Priority Boost
                                         │
                                         ▼
               OUTPUT Ranked Recommendations (JSON API Response)
```

---

## 🔌 API Contract

### Request Endpoint
`POST /drug-recommendation` (or `/api/drug-recommendation`)

```json
{
  "gene": "EGFR",
  "variant": "L858R",
  "disease": "NSCLC"
}
```

### Response Output
```json
{
  "gene": "EGFR",
  "variant": "L858R",
  "disease": "NSCLC",
  "recommendations": [
    {
      "drug": "Sunvozertinib",
      "rank": 1,
      "score": 0.9682,
      "response": "Sensitivity",
      "evidence_level": "A",
      "evidence_count": 7
    },
    {
      "drug": "Amivantamab",
      "rank": 2,
      "score": 0.9506,
      "response": "Sensitivity",
      "evidence_level": "A",
      "evidence_count": 4
    },
    {
      "drug": "Osimertinib",
      "rank": 3,
      "score": 0.9391,
      "response": "Sensitivity",
      "evidence_level": "A",
      "evidence_count": 24
    }
  ]
}
```

---

## 🧪 Testing & Execution

### Running the Test Suite
```bash
pytest tests/ -v
```

### Model Re-training & Evaluation
```bash
# Train ML Relevance Model
python model/train.py

# Benchmark Baseline vs ML vs Hybrid Ranking
python model/evaluate.py
```

### Standalone API Server Execution
```bash
uvicorn api.routes:app --reload --port 8000
```
