# GenoGuide benchmark table (real ClinVar data)

## split: gene_disjoint
(train=300,000 test=120,000 leakage=OK)

| model | AUPRC(macro) | AUROC(macro) | MCC | bal.acc | macro F1 | ECE(cal) | binary AUROC | binary AUPRC |
|---|---|---|---|---|---|---|---|---|
| xgboost | 0.558 | 0.897 | 0.592 | 0.604 | 0.554 | 0.068 | 0.978 | 0.937 |
| logreg **⭐** | 0.572 | 0.898 | 0.610 | 0.622 | 0.567 | 0.116 | 0.980 | 0.937 |
