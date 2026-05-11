# Waveshare Kaleidoscope Matrix

64x64 Raspberry Pi HUB75 kaleidoscope animation. This version keeps the ant-driven symmetric pattern running continuously, with no audio and no letter drawing.

## Raspberry Pi Setup

```bash
sudo apt update
sudo apt install -y git build-essential cmake ninja-build python3-dev python3-pil python3-pip python3-venv

cd ~
test -d rpi-rgb-led-matrix || git clone https://github.com/hzeller/rpi-rgb-led-matrix.git

cd ~
git clone https://github.com/timothyosm/waveshare-kaleidoscope-matrix.git
cd waveshare-kaleidoscope-matrix
./scripts/install_pi.sh
sudo ./scripts/run_waveshare.sh
```

## Manual Run

For the Waveshare 64x64 HUB75 wiring from Waveshare's guide:

```bash
sudo ./.venv/bin/python3 kaleidoscope_matrix.py \
  --hardware-mapping regular \
  --no-hardware-pulse \
  --rows 64 \
  --cols 64 \
  --gpio-slowdown 5 \
  --brightness 35 \
  --pwm-bits 1 \
  --pwm-dither-bits 0
```

If you are actually using an Adafruit HAT/Bonnet, try:

```bash
sudo ./.venv/bin/python3 kaleidoscope_matrix.py \
  --hardware-mapping adafruit-hat \
  --rows 64 \
  --cols 64 \
  --gpio-slowdown 2
```

## Preview

Generate a still frame without matrix hardware:

```bash
python3 kaleidoscope_matrix.py --preview preview.png
```

## systemd

```bash
sudo cp systemd/kaleidoscope-matrix.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kaleidoscope-matrix
```
