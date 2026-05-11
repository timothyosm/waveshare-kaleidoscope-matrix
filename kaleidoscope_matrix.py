#!/usr/bin/env python3
"""Run the kaleidoscope animation on a 64x64 HUB75 RGB matrix."""

from __future__ import annotations

import argparse
import math
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
BLACK = (0, 0, 0)
WHITE = (255, 255, 255)


class Kaleidoscope:
    def __init__(
        self,
        color: tuple[int, int, int],
        fade: float,
        ink: float,
        step_stride: int,
        turn_chance: float,
        curve_chance: float,
        speed: float,
        brush_radius: float,
        neighbor_boost_threshold: int,
    ) -> None:
        self.random = random.SystemRandom()
        self.color = color
        self.fade = fade
        self.ink = ink
        self.step_stride = step_stride
        self.turn_chance = turn_chance
        self.curve_chance = curve_chance
        self.speed = speed
        self.brush_radius = brush_radius
        self.neighbor_boost_threshold = neighbor_boost_threshold
        self.cells = [[0.0 for _ in range(SIZE)] for _ in range(SIZE)]
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0
        self.curl = 0.0
        self.phase = 0.0
        self.reset(0.0)

    def reset(self, now: float) -> None:
        for row in self.cells:
            for x_pos in range(SIZE):
                row[x_pos] = 0.0

        center = (SIZE - 1) / 2
        self.x = center + self.random.uniform(-4.0, 4.0)
        self.y = center + self.random.uniform(-4.0, 4.0)
        self.heading = self.random.random() * math.tau
        self.curl = self.random.uniform(-0.035, 0.035)
        self.phase = self.random.random() * math.tau
        self._seed_random_pattern()

    def update(self, _now: float) -> None:
        self._fade()
        for _ in range(self.step_stride):
            self._step()

    def render_pixels(self) -> list[tuple[int, int, int]]:
        pixels = [BLACK for _ in range(SIZE * SIZE)]
        red, green, blue = self.color

        for y_pos, row in enumerate(self.cells):
            for x_pos, value in enumerate(row):
                if value > 0.01:
                    if self._lit_neighbor_count(x_pos, y_pos) >= self.neighbor_boost_threshold:
                        value = 1.0
                    pixels[y_pos * SIZE + x_pos] = (
                        min(255, round(red * value)),
                        min(255, round(green * value)),
                        min(255, round(blue * value)),
                    )

        return pixels

    def _lit_neighbor_count(self, x_pos: int, y_pos: int) -> int:
        count = 0
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                if dx == 0 and dy == 0:
                    continue
                near_x = x_pos + dx
                near_y = y_pos + dy
                if 0 <= near_x < SIZE and 0 <= near_y < SIZE and self.cells[near_y][near_x] > 0.08:
                    count += 1
        return count

    def _seed_random_pattern(self) -> None:
        seed_flips = 2 + self.random.randrange(5)

        for _ in range(seed_flips):
            angle = self.random.random() * math.tau
            radius = self.random.randrange(5, 22)
            x_pos = (SIZE - 1) / 2 + math.cos(angle) * radius
            y_pos = (SIZE - 1) / 2 + math.sin(angle) * radius
            self._ink_symmetric_cells(x_pos, y_pos, self.ink * 0.65)

    def _fade(self) -> None:
        for row in self.cells:
            for x_pos, value in enumerate(row):
                row[x_pos] = value * self.fade

    def _symmetry_points(self, x_pos: float, y_pos: float) -> list[tuple[float, float]]:
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

    def _ink_symmetric_cells(self, x_pos: float, y_pos: float, amount: float) -> None:
        for point_x, point_y in self._symmetry_points(x_pos, y_pos):
            self._splat(point_x, point_y, amount)

    def _splat(self, x_pos: float, y_pos: float, amount: float) -> None:
        radius = max(0.5, self.brush_radius)
        min_x = math.floor(x_pos - radius)
        max_x = math.ceil(x_pos + radius)
        min_y = math.floor(y_pos - radius)
        max_y = math.ceil(y_pos + radius)

        for y_cell in range(min_y, max_y + 1):
            if y_cell < 0 or y_cell >= SIZE:
                continue
            for x_cell in range(min_x, max_x + 1):
                if x_cell < 0 or x_cell >= SIZE:
                    continue
                distance = math.hypot(x_cell - x_pos, y_cell - y_pos)
                if distance > radius:
                    continue
                weight = (1 - distance / radius) ** 1.7
                self.cells[y_cell][x_cell] = min(1.0, self.cells[y_cell][x_cell] + amount * weight)

    def _step(self) -> None:
        center = (SIZE - 1) / 2
        dx_center = center - self.x
        dy_center = center - self.y
        distance_from_center = math.hypot(dx_center, dy_center)

        if self.random.random() < self.turn_chance:
            self.curl += self.random.uniform(-0.05, 0.05)

        self.curl *= 0.985
        self.phase += 0.045
        self.heading += self.curl + math.sin(self.phase) * self.curve_chance * 0.045

        if distance_from_center > 25:
            target_heading = math.atan2(dy_center, dx_center)
            turn = math.atan2(math.sin(target_heading - self.heading), math.cos(target_heading - self.heading))
            self.heading += turn * 0.06

        self._ink_symmetric_cells(self.x, self.y, self.ink)
        self.x += math.cos(self.heading) * self.speed
        self.y += math.sin(self.heading) * self.speed

        if self.x < 1 or self.x > SIZE - 2 or self.y < 1 or self.y > SIZE - 2:
            self.heading = math.atan2(center - self.y, center - self.x) + self.random.uniform(-0.5, 0.5)
            self.x = min(SIZE - 2, max(1, self.x))
            self.y = min(SIZE - 2, max(1, self.y))


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
        fade=args.fade,
        ink=args.ink,
        step_stride=args.step_stride,
        turn_chance=args.turn_chance,
        curve_chance=args.curve_chance,
        speed=args.speed,
        brush_radius=args.brush_radius,
        neighbor_boost_threshold=args.neighbor_boost_threshold,
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
    parser.add_argument("--fade", type=float, default=0.985)
    parser.add_argument("--ink", type=float, default=0.32)
    parser.add_argument("--step-stride", type=int, default=1)
    parser.add_argument("--turn-chance", type=float, default=0.035)
    parser.add_argument("--curve-chance", type=float, default=0.2)
    parser.add_argument("--speed", type=float, default=0.58)
    parser.add_argument("--brush-radius", type=float, default=1.45)
    parser.add_argument("--neighbor-boost-threshold", type=int, default=6)
    parser.add_argument("--color", type=parse_color, default=WHITE)
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
