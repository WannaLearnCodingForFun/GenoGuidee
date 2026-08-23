#!/usr/bin/env bash
# GenoGuide diagnostics — honest status only.
set -u
cd "$(dirname "$0")"
ROOT="$PWD"
export PYTHONPATH="$ROOT"

echo "GENOGUIDE DIAGNOSTICS"
echo "====================="
echo ""

REMOTE_SHA="$(git rev-parse origin/main 2>/dev/null || echo MISSING)"
LOCAL_SHA="$(git rev-parse HEAD 2>/dev/null || echo MISSING)"

echo "REMOTE MAIN:"
echo "$REMOTE_SHA"
echo "LOCAL HEAD:"
echo "$LOCAL_SHA"
echo ""

SYNC="NO"
if [ "$REMOTE_SHA" != "MISSING" ] && [ "$LOCAL_SHA" = "$REMOTE_SHA" ]; then
  SYNC="YES"
else
  echo "FAIL:"
  echo "LOCAL CODE IS NOT SYNCHRONIZED WITH REMOTE MAIN"
  echo ""
fi

echo "Git"
echo "Remote: $REMOTE_SHA"
echo "Local:  $LOCAL_SHA"
echo "Synchronized: $SYNC"
echo ""

echo "Environment"
echo "Python: $(python3 --version 2>&1)"
echo "Node:   $(command -v node >/dev/null && node --version || echo missing)"
echo "npm:    $(command -v npm >/dev/null && npm --version || echo missing)"
if [ -x backend/.venv/bin/python ]; then
  echo "Virtualenv: backend/.venv ($(backend/.venv/bin/python --version 2>&1))"
else
  echo "Virtualenv: MISSING"
fi
echo ""

port_ok() {
  if curl -sf --max-time 2 "$1" >/dev/null; then echo "READY"; else echo "OFFLINE"; fi
}

BACKEND="$(port_ok http://127.0.0.1:8000/health)"
API="$(port_ok http://127.0.0.1:8000/docs)"
FRONTEND="$(port_ok http://127.0.0.1:3000)"

ACMG="OFFLINE"
ML="OFFLINE"
RESEARCH="OFFLINE"
THERAPY="OFFLINE"
PROVENANCE="OFFLINE"
NGROK="NOT_CONFIGURED"
OVERALL="FAILED"

if [ "$BACKEND" = "READY" ] && [ -x backend/.venv/bin/python ]; then
  backend/.venv/bin/python - <<'PY' > /tmp/genoguide-diagnose-health.env
import json, urllib.request
raw = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5).read()
d = json.loads(raw)
c = d.get("components", {})
def s(name):
    return c.get(name, {}).get("status", "OFFLINE")
for key, name in (
    ("ACMG", "acmg"),
    ("ML", "ml"),
    ("RESEARCH", "research"),
    ("THERAPY", "therapy"),
    ("PROVENANCE", "provenance"),
    ("NGROK", "ngrok"),
):
    print(f"{key}={s(name)}")
print("OVERALL=" + str(d.get("status", "FAILED")))
PY
  # shellcheck disable=SC1091
  ACMG="$(sed -n 's/^ACMG=//p' /tmp/genoguide-diagnose-health.env)"
  ML="$(sed -n 's/^ML=//p' /tmp/genoguide-diagnose-health.env)"
  RESEARCH="$(sed -n 's/^RESEARCH=//p' /tmp/genoguide-diagnose-health.env)"
  THERAPY="$(sed -n 's/^THERAPY=//p' /tmp/genoguide-diagnose-health.env)"
  PROVENANCE="$(sed -n 's/^PROVENANCE=//p' /tmp/genoguide-diagnose-health.env)"
  NGROK="$(sed -n 's/^NGROK=//p' /tmp/genoguide-diagnose-health.env)"
  OVERALL="$(sed -n 's/^OVERALL=//p' /tmp/genoguide-diagnose-health.env)"
fi

echo "Services"
echo "Backend:     $BACKEND"
echo "API:         $API"
echo "ACMG:        $ACMG"
echo "ML:          $ML"
echo "Research:    $RESEARCH"
echo "Therapy:     $THERAPY"
echo "Provenance:  $PROVENANCE"
echo "Ngrok:       $NGROK"
echo ""

echo "Frontend"
echo "Build: $( [ -f frontend/.next/BUILD_ID ] && echo present || echo not-built — npm run dev is enough )"
echo "API connectivity: $BACKEND"
echo ""

echo "Model artifacts"
if [ -f models/production/logreg_gene_disjoint.joblib ]; then
  echo "research logreg: present"
else
  echo "research logreg: MISSING models/production/logreg_gene_disjoint.joblib"
fi
if [ -f Medical_DrugRecommendation/recommendation/recommender.py ]; then
  echo "therapy ranker: present"
else
  echo "therapy ranker: MISSING"
fi
echo ""

echo "Environment variables"
echo "NEXT_PUBLIC_API_URL=${NEXT_PUBLIC_API_URL:-http://localhost:8000 (default)}"
echo "GENOGUIDE_DRUG_LOCAL=${GENOGUIDE_DRUG_LOCAL:-true (default)}"
echo "GENOGUIDE_DRUG_API_URL=${GENOGUIDE_DRUG_API_URL:-<unset>}"
echo "GENOGUIDE_PUBLIC_URL=${GENOGUIDE_PUBLIC_URL:-<unset>}"
echo "NEXT_PUBLIC_SUPABASE_URL=${NEXT_PUBLIC_SUPABASE_URL:-<unset — local demo fallback>}"
echo ""

echo "Tests"
if [ -x backend/.venv/bin/python ]; then
  if PYTHONPATH="$ROOT" backend/.venv/bin/python -m pytest -q >/tmp/genoguide-diagnose-pytest.txt 2>&1; then
    echo "Pytest: PASS"
  else
    echo "Pytest: FAIL (see /tmp/genoguide-diagnose-pytest.txt)"
  fi
else
  echo "Pytest: SKIPPED (no venv)"
fi
if [ -f frontend/.next/BUILD_ID ]; then
  echo "Frontend build: PASS ($(cat frontend/.next/BUILD_ID))"
else
  echo "Frontend build: not-built (npm run dev is enough for local demo)"
fi
echo ""

if [ "$SYNC" != "YES" ]; then
  OVERALL="FAILED"
fi

echo "Overall:"
echo "$OVERALL"
echo ""

if [ "$SYNC" != "YES" ]; then
  exit 2
fi
[ "$OVERALL" = "FAILED" ] && exit 1
exit 0
