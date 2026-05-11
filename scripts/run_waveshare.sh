#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

exec python3 kaleidoscope_matrix.py \
  --hardware-mapping regular \
  --no-hardware-pulse \
  --rows 64 \
  --cols 64 \
  --gpio-slowdown 4 \
  "$@"

