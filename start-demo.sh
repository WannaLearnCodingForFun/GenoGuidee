#!/usr/bin/env bash
# GenoGuide hackathon launcher — local-first. ngrok is optional.
set -euo pipefail
cd "$(dirname "$0")"
ROOT="$PWD"

unset GENOGUIDE_DRUG_API_ENABLED GENOGUIDE_DRUG_API_URL || true
export GENOGUIDE_DRUG_LOCAL=true
export PYTHONPATH="$ROOT"
export NEXT_PUBLIC_API_URL="${NEXT_PUBLIC_API_URL:-http://localhost:8000}"

BACKEND_PID=""
FRONTEND_PID=""
NGROK_PID=""
READY=0

cleanup() {
  trap - INT TERM EXIT
  echo ""
  echo "[GenoGuide] stopping child processes…"
  for pid in "$NGROK_PID" "$FRONTEND_PID" "$BACKEND_PID"; do
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
      kill "$pid" 2>/dev/null || true
    fi
  done
  wait >/dev/null 2>&1 || true
}
trap cleanup INT TERM EXIT

need() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "FAIL: missing prerequisite: $1"
    exit 1
  fi
}

echo "========================================="
echo "           GENOGUIDE"
echo "========================================="
echo ""

need python3
need node
need npm
echo "[GenoGuide] Python  $(python3 --version 2>&1)"
echo "[GenoGuide] Node    $(node --version)"
echo "[GenoGuide] npm     $(npm --version)"

if [ ! -x backend/.venv/bin/python ]; then
  echo "[GenoGuide] Creating Python venv + installing backend deps..."
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  echo "[GenoGuide] Installing frontend deps..."
  (cd frontend && npm install)
fi

if [ ! -f models/production/logreg_gene_disjoint.joblib ]; then
  echo "[GenoGuide] NOTE: research logreg artifact missing at models/production/logreg_gene_disjoint.joblib"
  echo "           Demo XGBoost and ACMG still run. Research ML will be DEGRADED."
fi
if [ ! -f Medical_DrugRecommendation/recommendation/recommender.py ]; then
  echo "FAIL: Missing model artifact: Medical_DrugRecommendation/recommendation/recommender.py"
  exit 1
fi

port_pid() {
  lsof -nP -iTCP:"$1" -sTCP:LISTEN -t 2>/dev/null | head -1 || true
}

wait_http() {
  local url="$1" label="$2" tries="${3:-40}"
  local i
  for i in $(seq 1 "$tries"); do
    if curl -sf "$url" >/dev/null; then
      echo "[GenoGuide] $label ready"
      return 0
    fi
    sleep 0.25
  done
  echo "FAIL: $label did not become ready ($url)"
  return 1
}

HEALTH_URL="http://127.0.0.1:8000/health"
if curl -sf "$HEALTH_URL" >/dev/null; then
  echo "[GenoGuide] Reusing healthy backend on :8000"
else
  stale="$(port_pid 8000)"
  if [ -n "$stale" ]; then
    echo "[GenoGuide] Stale process on :8000 (pid $stale) — restarting"
    kill "$stale" 2>/dev/null || true
    sleep 0.4
  fi
  echo "[GenoGuide] Starting backend on :8000"
  backend/.venv/bin/uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port 8000 &
  BACKEND_PID=$!
  wait_http "$HEALTH_URL" "Backend"
fi

if curl -sf http://127.0.0.1:3000 >/dev/null; then
  echo "[GenoGuide] Reusing frontend on :3000"
else
  stale="$(port_pid 3000)"
  if [ -n "$stale" ]; then
    echo "[GenoGuide] Stale process on :3000 (pid $stale) — restarting"
    kill "$stale" 2>/dev/null || true
    sleep 0.4
  fi
  echo "[GenoGuide] Starting frontend on :3000"
  (cd frontend && npm run dev -- --port 3000) &
  FRONTEND_PID=$!
  wait_http "http://127.0.0.1:3000" "Frontend" 80
fi

if [ "${GENOGUIDE_NGROK:-}" = "1" ] && command -v ngrok >/dev/null 2>&1; then
  if [ -n "${GENOGUIDE_NGROK_URL:-}" ]; then
    echo "[NGROK] optional tunnel → ${GENOGUIDE_NGROK_URL}"
    ngrok http 8000 --url "$GENOGUIDE_NGROK_URL" >/tmp/genoguide-ngrok.log 2>&1 &
  else
    echo "[NGROK] optional tunnel (random hostname)"
    ngrok http 8000 >/tmp/genoguide-ngrok.log 2>&1 &
  fi
  NGROK_PID=$!
else
  echo "[NGROK] skipped (optional — set GENOGUIDE_NGROK=1 to enable)"
fi

python_json() {
  backend/.venv/bin/python - <<'PY'
import json, urllib.request
raw = urllib.request.urlopen("http://127.0.0.1:8000/health", timeout=5).read()
print(raw.decode())
PY
}

mark() {
  local s="$1"
  case "$s" in
    READY) echo "✓ READY" ;;
    DEGRADED) echo "~ DEGRADED" ;;
    NOT_CONFIGURED) echo "○ OPTIONAL" ;;
    *) echo "× $s" ;;
  esac
}

HEALTH_JSON="$(python_json)"
comp() {
  echo "$HEALTH_JSON" | backend/.venv/bin/python -c "import json,sys; d=json.load(sys.stdin); print(d['components'].get('$1',{}).get('status','ERROR'))"
}

OVERALL="$(echo "$HEALTH_JSON" | backend/.venv/bin/python -c "import json,sys; print(json.load(sys.stdin)['status'])")"

echo ""
echo "========================================="
echo "           GENOGUIDE"
echo "========================================="
echo ""
printf "Frontend       %s\n" "$(curl -sf http://127.0.0.1:3000 >/dev/null && echo '✓ READY' || echo '× FAILED')"
printf "Backend        %s\n" "$(mark "$(comp backend)")"
printf "API            %s\n" "$(mark "$(comp backend)")"
printf "ACMG Engine    %s\n" "$(mark "$(comp acmg)")"
printf "ML Engine      %s\n" "$(mark "$(comp ml)")"
printf "Research       %s\n" "$(mark "$(comp research)")"
printf "Therapy        %s\n" "$(mark "$(comp therapy)")"
printf "Provenance     %s\n" "$(mark "$(comp provenance)")"
printf "Ngrok          %s\n" "$(mark "$(comp ngrok)")"
echo ""
echo "Frontend:"
echo "http://localhost:3000"
echo ""
echo "Backend:"
echo "http://localhost:8000"
echo ""
echo "API Docs:"
echo "http://localhost:8000/docs"
echo ""
if [ "$OVERALL" = "FAILED" ]; then
  echo "========================================="
  echo "SYSTEM NOT READY"
  echo "========================================="
  exit 1
fi
echo "========================================="
echo "SYSTEM READY"
echo "========================================="
READY=1

if [ -n "$BACKEND_PID" ] || [ -n "$FRONTEND_PID" ] || [ -n "$NGROK_PID" ]; then
  wait
fi
