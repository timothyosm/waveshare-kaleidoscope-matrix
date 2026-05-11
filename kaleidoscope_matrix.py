#!/usr/bin/env python3
"""Run the kaleidoscope animation on a 64x64 HUB75 RGB matrix."""

from __future__ import annotations

import argparse
import random
import signal
import sys
import time
from pathlib import Path
try:
    from PIL import Image
except ImportError as error:
    raise SystemExit("Pillow is required. Install it with: sudo apt install python3-pil") from error


SIZE = 64
DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))
BLACK = (0, 0, 0)
RED = (255, 0, 0)


class Kaleidoscope:
    def __init__(
        self,
        color: tuple[int, int, int],
    ) -> None:
        self.random = random.SystemRandom()
        self.color = color
        self.cells = [[False for _ in range(SIZE)] for _ in range(SIZE)]
        self.ant_x = 0
        self.ant_y = 0
        self.ant_direction = 0
        self.reset(0.0)

    def reset(self, now: float) -> None:
        for row in self.cells:
            for x_pos in range(SIZE):
                row[x_pos] = False

        self.ant_x = self.random.randrange(SIZE)
        self.ant_y = self.random.randrange(SIZE)
        self.ant_direction = self.random.randrange(len(DIRECTIONS))
        self._seed_random_pattern()

    def update(self, _now: float) -> None:
        self._step()

    def render_pixels(self) -> list[tuple[int, int, int]]:
        pixels = [BLACK for _ in range(SIZE * SIZE)]

        for y_pos, row in enumerate(self.cells):
            for x_pos, enabled in enumerate(row):
                if enabled:
                    pixels[y_pos * SIZE + x_pos] = self.color

        ant_index = self.ant_y * SIZE + self.ant_x
        pixels[ant_index] = BLACK if self.cells[self.ant_y][self.ant_x] else self.color
        return pixels

    def _seed_random_pattern(self) -> None:
        seed_flips = 8 + self.random.randrange(17)

        for _ in range(seed_flips):
            self._flip_symmetric_cells(self.random.randrange(SIZE), self.random.randrange(SIZE))

    def _symmetry_points(self, x_pos: int, y_pos: int) -> list[tuple[int, int]]:
        max_pos = SIZE - 1
        points = (
            (x_pos, y_pos),
            (max_pos - x_pos, y_pos),
            (x_pos, max_pos - y_pos),
            (max_pos - x_pos, max_pos - y_pos),
            (y_pos, x_pos),
            (max_pos - y_pos, x_pos),
            (y_pos, max_pos - x_pos),
            (max_pos - y_pos, max_pos - x_pos),
        )

        return list(dict.fromkeys(points))

    def _flip_symmetric_cells(self, x_pos: int, y_pos: int) -> None:
        for point_x, point_y in self._symmetry_points(x_pos, y_pos):
            self.cells[point_y][point_x] = not self.cells[point_y][point_x]

    def _step(self) -> None:
        if self.cells[self.ant_y][self.ant_x]:
            self.ant_direction = (self.ant_direction + 3) % len(DIRECTIONS)
        else:
            self.ant_direction = (self.ant_direction + 1) % len(DIRECTIONS)

        self._flip_symmetric_cells(self.ant_x, self.ant_y)

        dx, dy = DIRECTIONS[self.ant_direction]
        next_x = self.ant_x + dx
        next_y = self.ant_y + dy

        if next_x < 0 or next_x >= SIZE or next_y < 0 or next_y >= SIZE:
            self.ant_direction = (self.ant_direction + 2) % len(DIRECTIONS)
            dx, dy = DIRECTIONS[self.ant_direction]
            next_x = self.ant_x + dx
            next_y = self.ant_y + dy

        self.ant_x = next_x
        self.ant_y = next_y


def parse_color(value: str) -> tuple[int, int, int]:
    parts = value.split(",")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("color must be R,G,B")

    try:
        color = tuple(max(0, min(255, int(part))) for part in parts)
    except ValueError as error:
        raise argparse.ArgumentTypeError("color must be numeric R,G,B") from error

    return color  # type: ignore[return-value]


def create_state(args: argparse.Namespace) -> Kaleidoscope:
    return Kaleidoscope(
        color=args.color,
    )


def save_preview(args: argparse.Namespace) -> None:
    state = create_state(args)

    for _ in range(args.preview_steps):
        state.update(0.0)

    image = Image.new("RGB", (SIZE, SIZE))
    image.putdata(state.render_pixels())
    image = image.resize((args.preview_scale * SIZE, args.preview_scale * SIZE), Image.Resampling.NEAREST)
    image.save(args.preview)


def run_matrix(args: argparse.Namespace) -> None:
    try:
        from rgbmatrix import RGBMatrix, RGBMatrixOptions
    except ImportError as error:
        raise SystemExit(
            "rgbmatrix is not installed. Run ./scripts/install_pi.sh on the Pi first."
        ) from error

    state = create_state(args)

    options = RGBMatrixOptions()
    options.rows = args.rows
    options.cols = args.cols
    options.chain_length = args.chain_length
    options.parallel = args.parallel
    options.hardware_mapping = args.hardware_mapping
    options.gpio_slowdown = args.gpio_slowdown
    options.brightness = args.brightness
    options.pwm_bits = args.pwm_bits
    options.pwm_dither_bits = args.pwm_dither_bits
    options.pwm_lsb_nanoseconds = args.pwm_lsb_nanoseconds
    options.scan_mode = args.scan_mode
    options.multiplexing = args.multiplexing
    options.row_address_type = args.row_address_type
    options.led_rgb_sequence = args.rgb_sequence
    options.pixel_mapper_config = args.pixel_mapper
    options.panel_type = args.panel_type
    options.disable_hardware_pulsing = args.no_hardware_pulse
    options.limit_refresh_rate_hz = args.limit_refresh_rate_hz

    matrix = RGBMatrix(options=options)
    canvas = matrix.CreateFrameCanvas()
    image = Image.new("RGB", (SIZE, SIZE))
    running = True

    def stop(_signum: int, _frame: object) -> None:
        nonlocal running
        running = False

    signal.signal(signal.SIGINT, stop)
    signal.signal(signal.SIGTERM, stop)

    frame_seconds = 1.0 / args.fps

    try:
        while running:
            frame_started = time.monotonic()
            state.update(frame_started)
            image.putdata(state.render_pixels())
            canvas.Clear()
            canvas.SetImage(image)
            canvas = matrix.SwapOnVSync(canvas)
            elapsed = time.monotonic() - frame_started
            time.sleep(max(0.0, frame_seconds - elapsed))
    finally:
        canvas.Clear()
        matrix.SwapOnVSync(canvas)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Kaleidoscope animation for a 64x64 HUB75 matrix.")
    parser.add_argument("--rows", type=int, default=64)
    parser.add_argument("--cols", type=int, default=64)
    parser.add_argument("--chain-length", type=int, default=1)
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument("--hardware-mapping", default="regular")
    parser.add_argument("--gpio-slowdown", type=int, default=5)
    parser.add_argument("--brightness", type=int, default=35)
    parser.add_argument("--pwm-bits", type=int, default=1)
    parser.add_argument("--pwm-dither-bits", type=int, default=0)
    parser.add_argument("--pwm-lsb-nanoseconds", type=int, default=130)
    parser.add_argument("--scan-mode", type=int, default=0)
    parser.add_argument("--multiplexing", type=int, default=0)
    parser.add_argument("--row-address-type", type=int, default=0)
    parser.add_argument("--rgb-sequence", default="RGB")
    parser.add_argument("--pixel-mapper", default="")
    parser.add_argument("--panel-type", default="")
    parser.add_argument("--limit-refresh-rate-hz", type=int, default=120)
    parser.add_argument("--no-hardware-pulse", action="store_true")
    parser.add_argument("--fps", type=float, default=30.0)
    parser.add_argument("--color", type=parse_color, default=RED)
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--preview-steps", type=int, default=700)
    parser.add_argument("--preview-scale", type=int, default=8)
    return parser


def main() -> int:
    args = build_parser().parse_args()

    if args.preview:
        save_preview(args)
        return 0

    run_matrix(args)
    return 0


if __name__ == "__main__":
    sys.exit(main())
