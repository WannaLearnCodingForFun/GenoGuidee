# scripts/setup_alphamissense_index.py
r"""
One-shot setup: slices AlphaMissense_hg38.tsv.gz down to just the
chromosomes your 12 panel genes are on (per real coordinates confirmed via
clinvar_panel_with_coords.csv), then builds the local DuckDB index.

PREREQUISITE (do this first, separately -- large download, do it once):
    Download AlphaMissense_hg38.tsv.gz from the Zenodo/Google Storage link
    in https://github.com/google-deepmind/alphamissense, and place it in
    your project root (or update RAW_GZ_PATH below to point at it).

Usage:
    python -m scripts.setup_alphamissense_index
"""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.scoring.alphamissense import filter_to_chromosome, build_index

RAW_GZ_PATH = "AlphaMissense_hg38.tsv.gz"  # update this if the file lives elsewhere

# Confirmed via: clinvar_panel_with_coords.csv real chrom values per gene
CHROMS_NEEDED = [
    "chr1", "chr3", "chr5", "chr7", "chr11",
    "chr12", "chr13", "chr15", "chr16", "chr17", "chrX",
]


def main():
    raw_path = Path(RAW_GZ_PATH)
    if not raw_path.exists():
        print(f"ERROR: {raw_path} not found. Download it first -- see this "
              f"script's module docstring for the source link.")
        sys.exit(1)

    sliced_paths = []
    for chrom in CHROMS_NEEDED:
        out_path = f"data/raw/alphamissense_{chrom}.tsv"
        if Path(out_path).exists():
            print(f"{chrom}: already sliced, skipping ({out_path})")
        else:
            print(f"{chrom}: slicing from {raw_path} ...")
            filter_to_chromosome(str(raw_path), chrom, out_path)
            print(f"{chrom}: done -> {out_path}")
        sliced_paths.append(out_path)

    print("\nBuilding DuckDB index from all sliced chromosome files ...")
    db_path = build_index(sliced_paths)
    print(f"\nDone. Index built at: {db_path}")
    print("You can now run scripts/mutation_chain_data.py again -- "
          "alphamissense_score should no longer be None.")


if __name__ == "__main__":
    main()
