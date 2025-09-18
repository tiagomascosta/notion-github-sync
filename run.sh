#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
set -a
source .env
set +a
exec ./.venv/bin/python -u -m uvicorn app:app --host 127.0.0.1 --port 8088
