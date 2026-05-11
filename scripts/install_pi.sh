#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y git build-essential cmake ninja-build python3-dev python3-pil python3-pip python3-venv alsa-utils

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

cd "$HOME"
test -d rpi-rgb-led-matrix || git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd "$HOME/rpi-rgb-led-matrix"
git pull --ff-only || true

python3 -m venv "$PROJECT_DIR/.venv"
"$PROJECT_DIR/.venv/bin/python" -m pip install --upgrade pip setuptools wheel
"$PROJECT_DIR/.venv/bin/python" -m pip install .
"$PROJECT_DIR/.venv/bin/python" -m pip install Pillow

echo "Install complete. Run:"
echo "  cd $PROJECT_DIR && sudo ./scripts/run_waveshare.sh"
