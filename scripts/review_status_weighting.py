"""
review_status_weighting.py — adds a numeric confidence score derived from
ClinVar's review_status text (the same star-rating system ClinVar itself
displays on its website), so downstream consumers don't have to parse the
free-text review_status string themselves.

Star mapping (ClinVar's own system):
  4 stars — "practice guideline"
  3 stars — "reviewed by expert panel"
  2 stars — "criteria provided, multiple submitters, no conflicts"
  1 star  — "criteria provided, single submitter"
  1 star  — "criteria provided, conflicting classifications" (or
             "conflicting interpretations of pathogenicity" — older wording)
  0 stars — "no assertion criteria provided" / anything unrecognized

Input:  data/knowledge/clinvar_panel_with_hpo.csv
Output: data/knowledge/clinvar_panel_final.csv (adds confidence_stars,
        confidence_label columns)
"""
import csv

IN_PATH = "data/knowledge/clinvar_panel_with_hpo.csv"
OUT_PATH = "data/knowledge/clinvar_panel_final.csv"

# Ordered so more-specific / higher-confidence phrases are checked first,
# since some lower strings are substrings of higher ones' wording.
STAR_RULES = [
    (4, "practice guideline"),
    (3, "reviewed by expert panel"),
    (2, "criteria provided, multiple submitters, no conflicts"),
    (1, "criteria provided, conflicting classifications"),
    (1, "conflicting interpretations of pathogenicity"),
    (1, "criteria provided, single submitter"),
    (0, "no assertion criteria provided"),
]

STAR_LABELS = {
    4: "Practice guideline (highest confidence)",
    3: "Expert panel reviewed",
    2: "Multiple submitters, no conflicts",
    1: "Single submitter / conflicting",
    0: "No assertion criteria",
}


def score_review_status(text):
    text_lower = (text or "").lower()
    for stars, phrase in STAR_RULES:
        if phrase in text_lower:
            return stars
    return 0  # unrecognized/empty review_status defaults to lowest confidence


def main():
    with open(IN_PATH, encoding="utf-8") as f:
        rows = list(csv.DictReader(f))

    fieldnames = list(rows[0].keys())
    if "confidence_stars" not in fieldnames:
        fieldnames += ["confidence_stars", "confidence_label"]

    star_counts = {0: 0, 1: 0, 2: 0, 3: 0, 4: 0}
    for row in rows:
        stars = score_review_status(row.get("review_status", ""))
        row["confidence_stars"] = stars
        row["confidence_label"] = STAR_LABELS[stars]
        star_counts[stars] += 1

    with open(OUT_PATH, "w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)

    print("Confidence star distribution:")
    for stars in sorted(star_counts, reverse=True):
        print(f"  {stars} star(s): {star_counts[stars]} variants — {STAR_LABELS[stars]}")
    print(f"Wrote -> {OUT_PATH}")


if __name__ == "__main__":
    main()
