"""
stringdb_client.py -- fetches protein-protein interaction network data and
images from STRING-DB (string-db.org) for a "gene context" view: click a
gene, see its known protein interaction partners.

This is a genuinely different axis from everything else in the pipeline --
ClinVar/ACMG/AlphaMissense reason about a single variant's pathogenicity;
STRING reasons about what a gene's protein PHYSICALLY DOES in a cell (what
it binds, what pathway it sits in). It's not meant to feed pathogenicity
scoring -- it's a complementary "why does this gene matter biologically"
panel alongside the variant-level views.

No auth required. Confirmed against official docs: https://string-db.org/help/api/

Two-step workflow (STRING's own recommended pattern, not skipped for
speed): resolve the gene symbol to an unambiguous STRING ID first via
get_string_ids, THEN use that ID for the network image / interaction
partner queries. Skipping the resolve step and passing gene symbols
directly to the image endpoint also technically works (STRING's docs show
this), but risks silently matching the wrong gene/species for anything
even slightly ambiguous -- not worth the risk for real disease genes.

For production/demo-day stability, STRING recommends pinning to a
version-specific host (e.g. version-12-0.string-db.org) instead of the
rolling string-db.org, since the rolling host can change between demo
prep and the actual demo. Left as string-db.org (dev) here since pinning
to a version number without confirming the current version live risks
guessing wrong -- flagged as a TODO, not silently assumed.

NEW in this version: get_panel_network() -- a batch call across ALL panel
genes at once, instead of looping resolve+network per gene. This is the
STRING-documented way to see real edges BETWEEN a set of proteins (e.g.
"do any of our 12 panel genes' proteins interact with each other?"),
which per-gene looping cannot show -- looping only ever returns each
gene's own individual neighborhood, never cross-gene edges within the
input set.
"""
from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any, Optional

import requests

STRING_API_BASE = "https://string-db.org/api"  # TODO: consider pinning to a version-specific host before demo day
CALLER_IDENTITY = "genochain-hackathon-project"
HUMAN_SPECIES = 9606

CACHE_PATH = Path(__file__).resolve().parent.parent.parent / "data" / "knowledge" / "stringdb_cache.json"


def _load_cache() -> dict:
    if CACHE_PATH.exists():
        with open(CACHE_PATH, encoding="utf-8") as f:
            return json.load(f)
    return {}


def _save_cache(cache: dict) -> None:
    CACHE_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(CACHE_PATH, "w", encoding="utf-8") as f:
        json.dump(cache, f, indent=2)


def resolve_string_id(gene_symbol: str, species: int = HUMAN_SPECIES) -> Optional[str]:
    """
    Resolves a gene symbol (e.g. 'CFTR') to STRING's own unambiguous
    identifier (e.g. '9606.ENSP00000003084'). This is STRING's documented
    first step -- skipping it and passing gene symbols straight into later
    calls works for clean cases but risks a silent wrong-match for
    anything ambiguous.

    Cached locally since this project's gene panel is small and fixed --
    no reason to re-resolve the same 12 gene symbols on every run.
    """
    cache = _load_cache()
    cache_key = f"resolve:{gene_symbol}:{species}"
    if cache_key in cache:
        return cache[cache_key]

    url = f"{STRING_API_BASE}/json/get_string_ids"
    params = {
        "identifiers": gene_symbol,
        "species": species,
        "limit": 1,
        "caller_identity": CALLER_IDENTITY,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    results = resp.json()

    string_id = results[0]["stringId"] if results else None
    cache[cache_key] = string_id
    _save_cache(cache)
    return string_id


def resolve_string_ids_batch(gene_symbols: list[str], species: int = HUMAN_SPECIES) -> dict[str, Optional[str]]:
    """
    Batch version of resolve_string_id -- resolves multiple gene symbols
    in ONE request instead of one request per gene. STRING's
    get_string_ids accepts multiple identifiers separated by newline
    ("%0d" URL-encoded, or a literal newline in the POST body -- requests
    handles the encoding).

    Returns {gene_symbol: string_id_or_None}, preserving input order.
    Falls back to the single-gene cache/lookup for any gene missing from
    the batch response (STRING drops unmatched identifiers rather than
    returning a null placeholder, so we can't assume positional alignment).
    """
    cache = _load_cache()
    uncached = [g for g in gene_symbols if f"resolve:{g}:{species}" not in cache]

    if uncached:
        url = f"{STRING_API_BASE}/json/get_string_ids"
        params = {
            "identifiers": "\n".join(uncached),
            "species": species,
            "limit": 1,
            "caller_identity": CALLER_IDENTITY,
        }
        resp = requests.get(url, params=params, timeout=30)
        resp.raise_for_status()
        results = resp.json()

        resolved_by_query = {r["queryItem"]: r["stringId"] for r in results if "queryItem" in r}
        for gene in uncached:
            cache[f"resolve:{gene}:{species}"] = resolved_by_query.get(gene)
        _save_cache(cache)

    return {gene: cache.get(f"resolve:{gene}:{species}") for gene in gene_symbols}


def get_network_image_url(
    gene_symbol: str,
    species: int = HUMAN_SPECIES,
    required_score: int = 400,
    limit: int = 10,
    network_flavor: str = "confidence",
) -> Optional[str]:
    """
    Returns a plain image URL (PNG) for a gene's interaction network --
    embed directly as <img src=...> in the frontend, no image download
    needed server-side.

    required_score: STRING's confidence threshold, 0-1000 (400 = STRING's
    own "medium confidence" default; raise toward 700-900 for a cleaner,
    higher-confidence-only network if the default looks too noisy/dense
    for a demo).
    limit: max number of additional interacting proteins to show.
    network_flavor: 'confidence' (edge thickness = confidence score),
    'evidence' (edge color = evidence type: experimental/database/text-
    mining/etc.), or 'actions' (shows activation/inhibition arrows where
    known). 'evidence' is likely the most visually interesting for judges
    since it shows HOW each interaction was determined, not just that it
    exists.
    """
    string_id = resolve_string_id(gene_symbol, species)
    if string_id is None:
        return None

    params = {
        "identifiers": string_id,
        "required_score": required_score,
        "limit": limit,
        "network_flavor": network_flavor,
        "caller_identity": CALLER_IDENTITY,
    }
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{STRING_API_BASE}/image/network?{query_string}"


def get_panel_network_image_url(
    gene_symbols: list[str],
    species: int = HUMAN_SPECIES,
    required_score: int = 400,
    add_nodes: int = 0,
    network_flavor: str = "confidence",
) -> Optional[str]:
    """
    ONE combined network image for the whole panel, not one image per
    gene. get_network_image_url() only ever accepts a single string_id,
    so calling it in a loop -- even after batch-resolving IDs -- still
    draws N separate pictures, each showing only that one gene's own
    neighborhood. This is the actual fix: batch-resolve all gene_symbols,
    then pass ALL resolved STRING IDs into ONE call to the image endpoint,
    which is what makes STRING draw them as a single connected picture
    (showing real edges between panel genes if any exist, per required_score).

    add_nodes: same meaning as in get_panel_network() -- extra connector
    proteins STRING may add to bridge otherwise-isolated genes. Keep at 0
    first to see the panel genes' true (likely sparse) connectivity;
    raise it afterward if you want a denser demo image.

    Returns None if none of the gene_symbols resolved to a STRING ID.
    """
    resolved = resolve_string_ids_batch(gene_symbols, species)
    string_ids = [sid for sid in resolved.values() if sid is not None]
    if not string_ids:
        return None

    params = {
        "identifiers": "%0d".join(string_ids),
        "species": species,
        "required_score": required_score,
        "add_nodes": add_nodes,
        "network_flavor": network_flavor,
        "caller_identity": CALLER_IDENTITY,
    }
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{STRING_API_BASE}/image/network?{query_string}"


def get_interaction_partners(
    gene_symbol: str,
    species: int = HUMAN_SPECIES,
    required_score: int = 400,
    limit: int = 10,
) -> list[dict[str, Any]]:
    """
    Returns structured interaction-partner data (not just the image) --
    useful for a "top interacting proteins" sidebar/table alongside the
    network image, or for feeding partner gene names into other parts of
    the pipeline later (e.g. 'this gene's network also touches these
    other panel genes').

    Each result dict has (per STRING's network method): stringId_A,
    stringId_B, preferredName_A, preferredName_B, score, plus per-channel
    evidence scores (nscore, fscore, pscore, ascore, escore, dscore, tscore).
    """
    string_id = resolve_string_id(gene_symbol, species)
    if string_id is None:
        return []

    url = f"{STRING_API_BASE}/json/network"
    params = {
        "identifiers": string_id,
        "species": species,
        "required_score": required_score,
        "limit": limit,
        "caller_identity": CALLER_IDENTITY,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    return resp.json()


def get_panel_network(
    gene_symbols: list[str],
    species: int = HUMAN_SPECIES,
    required_score: int = 400,
    add_nodes: int = 0,
) -> dict[str, Any]:
    """
    Batch/panel-level network call -- the actual "overall graph with all
    these genes" query. Resolves all gene_symbols in one batch request,
    then queries STRING's network method with ALL resolved IDs passed
    together, so the result includes real edges BETWEEN panel genes, not
    just each gene's individual neighborhood.

    add_nodes: how many EXTRA interactors STRING may add beyond the input
    set (0 = show only edges among the input genes themselves -- the
    "are our panel genes connected at all" view; >0 lets STRING pull in
    a few extra connector proteins to bridge otherwise-isolated genes,
    which can turn a sparse panel-only graph into a more connected one,
    at the cost of introducing genes not in the actual panel).

    Returns:
        {
            "resolved": {gene_symbol: string_id_or_None, ...},
            "unresolved": [gene_symbols with no STRING match],
            "edges": [raw network-method result dicts],
            "connected_gene_pairs": [(geneA, geneB, score), ...] -- edges
                where BOTH endpoints are in the original input panel
                (i.e. excludes edges to any add_nodes extras),
        }

    Expect for this specific 12-gene panel: most of these genes represent
    unrelated monogenic diseases (CFTR/HBB/GJB2/HEXA/PAH/ATP7B/SMN1/MEFV/
    ASPA/GBA1/G6PD/BTD), chosen for carrier-screening relevance, not
    shared biology. A largely disconnected or sparse result here is a
    real, informative finding -- not a bug in this function.
    """
    resolved = resolve_string_ids_batch(gene_symbols, species)
    unresolved = [g for g, sid in resolved.items() if sid is None]
    string_ids = [sid for sid in resolved.values() if sid is not None]

    if not string_ids:
        return {"resolved": resolved, "unresolved": unresolved, "edges": [], "connected_gene_pairs": []}

    url = f"{STRING_API_BASE}/json/network"
    params = {
        "identifiers": "\n".join(string_ids),
        "species": species,
        "required_score": required_score,
        "add_nodes": add_nodes,
        "caller_identity": CALLER_IDENTITY,
    }
    resp = requests.get(url, params=params, timeout=30)
    resp.raise_for_status()
    edges = resp.json()

    panel_symbols = set(resolved.keys())
    connected_gene_pairs = [
        (e["preferredName_A"], e["preferredName_B"], e.get("score"))
        for e in edges
        if e.get("preferredName_A") in panel_symbols and e.get("preferredName_B") in panel_symbols
    ]

    return {
        "resolved": resolved,
        "unresolved": unresolved,
        "edges": edges,
        "connected_gene_pairs": connected_gene_pairs,
    }


if __name__ == "__main__":
    PANEL_GENES = [
        "CFTR", "HBB", "GJB2", "HEXA", "PAH", "ATP7B",
        "SMN1", "MEFV", "ASPA", "GBA1", "G6PD", "BTD",
    ]

    print("=== STRING-DB smoke test across panel genes (per-gene) ===\n")
    for gene in PANEL_GENES:
        string_id = resolve_string_id(gene)
        if string_id is None:
            print(f"{gene}: FAILED to resolve -- check gene symbol / STRING coverage")
            continue

        partners = get_interaction_partners(gene, limit=5)
        partner_names = [
            p["preferredName_B"] for p in partners
            if p.get("preferredName_A") == gene.upper() or p.get("preferredName_B") != gene.upper()
        ][:5]
        image_url = get_network_image_url(gene, limit=5)

        print(f"{gene} -> {string_id}")
        print(f"  top partners: {partner_names}")
        print(f"  image: {image_url}\n")

    print("\n=== STRING-DB panel-level network (batch, all 12 genes at once) ===\n")
    panel_result = get_panel_network(PANEL_GENES, required_score=400, add_nodes=0)

    print(f"Resolved: {sum(1 for v in panel_result['resolved'].values() if v)}/{len(PANEL_GENES)}")
    if panel_result["unresolved"]:
        print(f"Unresolved: {panel_result['unresolved']}")

    panel_image_url = get_panel_network_image_url(PANEL_GENES, required_score=400, add_nodes=0)
    print(f"\nSingle combined panel image (all 12 genes, one picture): {panel_image_url}")

    if panel_result["connected_gene_pairs"]:
        print(f"\n{len(panel_result['connected_gene_pairs'])} direct edge(s) found BETWEEN panel genes:")
        for gene_a, gene_b, score in panel_result["connected_gene_pairs"]:
            print(f"  {gene_a} -- {gene_b}  (score: {score})")
    else:
        print("\nNo direct edges found between any of the 12 panel genes at required_score=400.")
        print("This is expected -- these genes represent unrelated monogenic diseases, not a shared pathway.")
        print("Try required_score=150 (STRING's lowest-confidence threshold) or add_nodes=5-10 to see")
        print("whether any panel genes connect through a shared intermediate protein.")
