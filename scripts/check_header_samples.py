# scripts/check_header_samples.py
from pathlib import Path

path = Path(__file__).resolve().parent.parent / "data" / "raw" / "trio_regions" / "CFTR.vcf"

with open(path, encoding="utf-8") as f:
    for line in f:
        if line.startswith("#CHROM"):
            cols = line.strip().split("\t")
            print("total columns:", len(cols))
            print("first 9 (fixed fields):", cols[:9])
            print()
            for target in ["NA12878", "NA12891", "NA12892"]:
                print(target, "-> found" if target in cols else "NOT FOUND")
            break
    else:
        print("No #CHROM line found in file at all")