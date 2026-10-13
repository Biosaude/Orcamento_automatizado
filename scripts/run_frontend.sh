#!/usr/bin/env bash
set -euo pipefail
export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/biosaude-uv-cache}"
cd "$(dirname "${BASH_SOURCE[0]}")/.."
exec uv run --frozen streamlit run frontend/app.py --server.address 127.0.0.1 --server.port 8501
