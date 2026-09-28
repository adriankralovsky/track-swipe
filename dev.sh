#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
if [[ ! -d .venv ]]; then python3 -m venv .venv; fi
if [[ ! -f .venv/.installed ]]; then .venv/bin/pip install -r requirements.txt; touch .venv/.installed; fi
if [[ ! -d frontend/node_modules ]]; then npm ci --prefix frontend; fi
.venv/bin/uvicorn backend.main:app --host 127.0.0.1 --port 8765 --reload &
backend_pid=$!
trap 'kill "$backend_pid" 2>/dev/null || true' EXIT INT TERM
npm run dev --prefix frontend
