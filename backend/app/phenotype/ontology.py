"""
HPO ontology + annotation loading.

Parses the real hp.obo (release version recorded), phenotype.hpoa
(disease → phenotype annotations) and genes_to_phenotype.txt
(gene → phenotype profiles). Computes per-term information content from
disease-annotation frequencies with ancestor propagation:

    IC(t) = -ln( n_diseases_annotated_to_t_or_descendants / n_diseases )

The parsed ontology is cached in-process (singleton) — files are read once.
"""
from __future__ import annotations

from collections import defaultdict
from functools import lru_cache
from math import log
from pathlib import Path
from typing import Optional

REPO = Path(__file__).resolve().parents[3]
HPO_DIR = REPO / "research/data/raw/hpo"
PHENOTYPIC_ABNORMALITY_ROOT = "HP:0000118"


class Ontology:
    def __init__(self) -> None:
        self.version: Optional[str] = None
        self.terms: dict[str, str] = {}                 # id → name
        self.parents: dict[str, set[str]] = defaultdict(set)
        self.alt_ids: dict[str, str] = {}
        self.ic: dict[str, float] = {}
        self.disease_terms: dict[str, set[str]] = defaultdict(set)   # disease → direct terms
        self.disease_names: dict[str, str] = {}
        self.gene_terms: dict[str, set[str]] = defaultdict(set)      # gene → direct terms
        self.gene_diseases: dict[str, set[str]] = defaultdict(set)
        self._anc_cache: dict[str, frozenset[str]] = {}

    # -- structure ----------------------------------------------------------
    def resolve(self, term: str) -> Optional[str]:
        term = term.strip()
        if term in self.terms:
            return term
        return self.alt_ids.get(term)

    def ancestors(self, term: str) -> frozenset[str]:
        """All ancestors including the term itself."""
        cached = self._anc_cache.get(term)
        if cached is not None:
            return cached
        seen: set[str] = set()
        stack = [term]
        while stack:
            t = stack.pop()
            if t in seen:
                continue
            seen.add(t)
            stack.extend(self.parents.get(t, ()))
        result = frozenset(seen)
        self._anc_cache[term] = result
        return result

    def term_ic(self, term: str) -> float:
        return self.ic.get(term, 0.0)


def _parse_obo(onto: Ontology, path: Path) -> None:
    current: Optional[str] = None
    obsolete = False
    with open(path) as f:
        for line in f:
            line = line.strip()
            if line == "[Term]":
                current, obsolete = None, False
            elif line.startswith("data-version:"):
                onto.version = line.split(":", 1)[1].strip()
            elif line.startswith("id: HP:"):
                current = line[4:].strip()
            elif line.startswith("name: ") and current:
                onto.terms[current] = line[6:].strip()
            elif line.startswith("alt_id: ") and current:
                onto.alt_ids[line[8:].strip()] = current
            elif line.startswith("is_a: ") and current:
                onto.parents[current].add(line[6:].split("!")[0].strip())
            elif line == "is_obsolete: true" and current:
                obsolete = True
                onto.terms.pop(current, None)


def _parse_hpoa(onto: Ontology, path: Path) -> None:
    with open(path) as f:
        for line in f:
            if line.startswith("#") or line.startswith("database_id"):
                continue
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 12:
                continue
            disease_id, disease_name, qualifier, hpo_id, aspect = \
                parts[0], parts[1], parts[2], parts[3], parts[10]
            if qualifier == "NOT" or aspect != "P":
                continue
            term = onto.resolve(hpo_id)
            if term:
                onto.disease_terms[disease_id].add(term)
                onto.disease_names[disease_id] = disease_name


def _parse_g2p(onto: Ontology, path: Path) -> None:
    with open(path) as f:
        next(f)  # header
        for line in f:
            parts = line.rstrip("\n").split("\t")
            if len(parts) < 6:
                continue
            gene, hpo_id, disease_id = parts[1], parts[2], parts[5]
            term = onto.resolve(hpo_id)
            if term:
                onto.gene_terms[gene].add(term)
                onto.gene_diseases[gene].add(disease_id)


def _compute_ic(onto: Ontology) -> None:
    n_diseases = len(onto.disease_terms)
    if n_diseases == 0:
        return
    counts: dict[str, int] = defaultdict(int)
    for terms in onto.disease_terms.values():
        propagated: set[str] = set()
        for t in terms:
            propagated |= onto.ancestors(t)
        for t in propagated:
            counts[t] += 1
    for t, c in counts.items():
        onto.ic[t] = -log(c / n_diseases) if c else 0.0


@lru_cache(maxsize=1)
def load_ontology() -> Ontology:
    obo = HPO_DIR / "hp.obo"
    if not obo.exists():
        raise FileNotFoundError(
            "HPO files missing — run: python -m cli.genoguide data download hpo")
    onto = Ontology()
    _parse_obo(onto, obo)
    hpoa = HPO_DIR / "phenotype.hpoa"
    if hpoa.exists():
        _parse_hpoa(onto, hpoa)
    g2p = HPO_DIR / "genes_to_phenotype.txt"
    if g2p.exists():
        _parse_g2p(onto, g2p)
    _compute_ic(onto)
    return onto
