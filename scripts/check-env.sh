#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ok=0

need() {
  if command -v "$1" >/dev/null 2>&1; then
    echo "OK  $1: $(command -v "$1")"
  else
    echo "MISSING  $1"
    ok=1
  fi
}

need python3 || need python
need npm
need node

if command -v curl >/dev/null 2>&1; then
  if curl -sf --max-time 2 "http://127.0.0.1:11434/api/tags" >/dev/null 2>&1; then
    echo "OK  ollama: http://127.0.0.1:11434"
  else
    echo "WARN  ollama not reachable (optional for text extract)"
  fi
fi

if [[ ! -f "$ROOT/backend/pyproject.toml" ]]; then
  echo "MISSING  backend/pyproject.toml"
  ok=1
fi
if [[ ! -f "$ROOT/frontend/package.json" ]]; then
  echo "MISSING  frontend/package.json"
  ok=1
fi

exit "$ok"
