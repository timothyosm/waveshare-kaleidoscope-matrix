# Waveshare Kaleidoscope Matrix

64x64 Raspberry Pi HUB75 LED matrix port of `kaleidoscope-1x1.html`, with audio removed.

## Raspberry Pi Setup

```bash
sudo apt update
sudo apt install -y git build-essential python3-dev python3-pil

cd ~
test -d rpi-rgb-led-matrix || git clone https://github.com/hzeller/rpi-rgb-led-matrix.git
cd ~/rpi-rgb-led-matrix
make build-python PYTHON=$(command -v python3)
sudo make install-python PYTHON=$(command -v python3)

cd ~
git clone https://github.com/timothyosm/waveshare-kaleidoscope-matrix.git
cd waveshare-kaleidoscope-matrix
sudo ./scripts/run_waveshare.sh
```

## Manual Run

For the Waveshare 64x64 HUB75 wiring from Waveshare's guide:

```bash
sudo python3 kaleidoscope_matrix.py \
  --hardware-mapping regular \
  --no-hardware-pulse \
  --rows 64 \
  --cols 64 \
  --gpio-slowdown 4
```

If you are actually using an Adafruit HAT/Bonnet, try:

```bash
sudo python3 kaleidoscope_matrix.py \
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

Open the no-sound browser version:

```bash
open web/kaleidoscope-1x1-nosound.html
```

## systemd

```bash
sudo cp systemd/kaleidoscope-matrix.service /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now kaleidoscope-matrix
```

