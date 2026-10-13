#!/usr/bin/env bash
set -euo pipefail
export UV_CACHE_DIR="${UV_CACHE_DIR:-${TMPDIR:-/tmp}/biosaude-uv-cache}"
cd "$(dirname "${BASH_SOURCE[0]}")/.."
uv sync --locked
