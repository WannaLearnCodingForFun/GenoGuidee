#!/usr/bin/env bash
# GenoGuide one-shot demo launcher (fully offline once dependencies are installed).
set -e
cd "$(dirname "$0")"

if [ ! -d backend/.venv ]; then
  echo "[GenoGuide] Creating Python venv + installing backend deps..."
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi

if [ ! -d frontend/node_modules ]; then
  echo "[GenoGuide] Installing frontend deps..."
  (cd frontend && npm install)
fi

if [ ! -d frontend/.next ]; then
  echo "[GenoGuide] Building frontend..."
  (cd frontend && npm run build)
fi

echo "[GenoGuide] Starting backend on :8000"
(cd backend && .venv/bin/uvicorn app.main:app --port 8000 &)

echo "[GenoGuide] Starting frontend on :3000"
(cd frontend && npm run start &)

sleep 4
echo ""
echo "  GenoGuide is live → http://localhost:3000"
echo "  API docs          → http://localhost:8000/docs"
echo ""
wait
