#!/usr/bin/env bash
set -euo pipefail

sudo apt update
sudo apt install -y git build-essential python3-dev python3-pil

cd "$HOME"
test -d rpi-rgb-led-matrix || git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd "$HOME/rpi-rgb-led-matrix"
make build-python PYTHON="$(command -v python3)"
sudo make install-python PYTHON="$(command -v python3)"

echo "Install complete. Run:"
echo "  cd $HOME/waveshare-kaleidoscope-matrix && sudo ./scripts/run_waveshare.sh"

