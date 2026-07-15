#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKEND="$ROOT/backend"
FRONTEND="$ROOT/frontend"

"$ROOT/scripts/check-env.sh" || true

if [[ ! -f "$BACKEND/.env" && -f "$BACKEND/.env.example" ]]; then
  cp "$BACKEND/.env.example" "$BACKEND/.env"
  echo "Created backend/.env from .env.example"
fi

echo "==> Backend deps"
(cd "$BACKEND" && pip install -e ".[dev]" -q)

echo "==> Frontend deps"
(cd "$FRONTEND" && if [[ ! -d node_modules ]]; then npm ci; fi)

echo "==> Starting backend :8000 and frontend :5173"
(cd "$BACKEND" && python -m uvicorn aivp.api.app:create_app --factory --reload --host 127.0.0.1 --port 8000) &
BACK_PID=$!
(cd "$FRONTEND" && npm run dev -- --host 127.0.0.1 --port 5173) &
FRONT_PID=$!

cleanup() {
  kill "$BACK_PID" "$FRONT_PID" 2>/dev/null || true
}
trap cleanup EXIT INT TERM

echo "Backend  http://127.0.0.1:8000"
echo "Frontend http://127.0.0.1:5173"
echo "Ctrl+C to stop."
wait
