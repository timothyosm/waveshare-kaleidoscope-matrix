#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

PYTHON="${PYTHON:-./.venv/bin/python3}"
if [[ ! -x "$PYTHON" ]]; then
  PYTHON="$(command -v python3)"
fi

exec "$PYTHON" kaleidoscope_matrix.py \
  --hardware-mapping regular \
  --no-hardware-pulse \
  --rows 64 \
  --cols 64 \
  --gpio-slowdown 5 \
  --brightness 35 \
  --color 255,255,255 \
  --pwm-bits 5 \
  --pwm-dither-bits 0 \
  --limit-refresh-rate-hz 120 \
  --fade 0.985 \
  --ink 0.32 \
  --turn-chance 0.035 \
  --curve-chance 0.2 \
  --speed 0.58 \
  --brush-radius 1.45 \
  --neighbor-boost-threshold 6 \
  --audio \
  --chime-volume 0.035 \
  --chime-duration 0.18 \
  "$@"
