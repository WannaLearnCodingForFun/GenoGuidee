import pandas as pd

from research.evaluation.splits import gene_disjoint_split


def test_gene_disjoint_no_overlap():
    genes = (["BRCA1"] * 20 + ["TP53"] * 20 + ["CFTR"] * 20
             + ["LDLR"] * 20 + ["GJB2"] * 20 + ["MYH7"] * 20)
    df = pd.DataFrame({
        "gene": genes,
        "chrom": ["17"] * 40 + ["7"] * 20 + ["19"] * 20 + ["13"] * 20 + ["14"] * 20,
        "y": [0, 1, 2, 3, 4] * 24,
    })
    split = gene_disjoint_split(df)
    tg = set(df.iloc[split["train"]]["gene"])
    vg = set(df.iloc[split["val"]]["gene"])
    sg = set(df.iloc[split["test"]]["gene"])
    assert split["meta"]["gene_overlap_train_test"] == 0
    assert split["meta"]["gene_overlap_train_val"] == 0
    assert not (tg & sg)
    assert not (tg & vg)
