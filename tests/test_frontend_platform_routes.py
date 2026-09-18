from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
FRONT = ROOT / "frontend" / "src"

LEGACY = [
    "app/(app)/dashboard/page.tsx",
    "app/(app)/clinical-workup/page.tsx",
    "app/(app)/variant-lab/page.tsx",
    "app/(app)/patient-context/page.tsx",
    "app/(app)/genomic-timeline/page.tsx",
    "app/(app)/therapy/page.tsx",
    "app/(app)/knowledge-graph/page.tsx",
    "app/(app)/provenance/page.tsx",
    "app/(app)/model-evaluation/page.tsx",
    "app/(app)/upload/page.tsx",
]

PLATFORM = [
    "app/(app)/evidence-intelligence/page.tsx",
    "app/(app)/reanalysis/page.tsx",
    "app/(app)/curation/page.tsx",
    "app/(app)/phenotype-analysis/page.tsx",
    "app/(app)/inheritance/page.tsx",
    "app/(app)/acmg-simulator/page.tsx",
    "app/(app)/phenopackets/page.tsx",
    "app/(app)/model-monitoring/page.tsx",
    "app/(app)/interpretations/[id]/page.tsx",
]


def test_legacy_routes_still_exist():
    missing = [p for p in LEGACY if not (FRONT / p).exists()]
    assert missing == [], missing


def test_platform_routes_exist():
    missing = [p for p in PLATFORM if not (FRONT / p).exists()]
    assert missing == [], missing


def test_single_api_client():
    assert (FRONT / "lib" / "api.ts").exists()
    assert (FRONT / "lib" / "platform" / "client.ts").exists()
    text = (FRONT / "lib" / "platform" / "client.ts").read_text()
    assert "from \"@/lib/api\"" in text or "from '@/lib/api'" in text
    assert "apiGet" in text and "apiPost" in text


def test_nav_keeps_legacy_and_adds_platform():
    nav = (FRONT / "lib" / "nav.ts").read_text()
    for href in [
        "/dashboard",
        "/variant-lab",
        "/knowledge-graph",
        "/provenance",
        "/model-evaluation",
    ]:
        assert href in nav
    plat = (FRONT / "lib" / "platformNav.ts").read_text()
    for href in [
        "/evidence-intelligence",
        "/reanalysis",
        "/curation",
        "/phenotype-analysis",
        "/inheritance",
        "/acmg-simulator",
        "/phenopackets",
        "/model-monitoring",
    ]:
        assert href in plat


def test_knowledge_graph_not_replaced():
    kg = (FRONT / "app/(app)/knowledge-graph/page.tsx").read_text()
    assert "Knowledge Graph" in kg
    assert "Open Evidence Intelligence" in kg
    assert "/evidence-graph" not in kg
