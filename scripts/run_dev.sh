#!/usr/bin/env bash
# Run the API locally against dockerized Postgres (semantic/vector memory now
# lives in the same database -- no separate Qdrant service).
set -euo pipefail

cd "$(dirname "$0")/.."

docker compose up -d postgres

export PYTHONPATH="$(pwd)/src"
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

uvicorn aio.api.main:app --reload --host "${API_HOST:-0.0.0.0}" --port "${API_PORT:-8000}"
