#!/usr/bin/env bash
set -e

cd "$(dirname "$0")"

# Load .env into environment (for GOOGLE_APPLICATION_CREDENTIALS etc.)
if [ -f .env ]; then
  set -a
  source .env
  set +a
fi

if [ ! -d ".venv" ]; then
    python3 -m venv .venv
    .venv/bin/pip install -r requirements.txt
fi

source .venv/bin/activate
exec uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-9000} --reload
