#!/usr/bin/env python3
"""Run the kaleidoscope animation on a 64x64 HUB75 RGB matrix."""

from __future__ import annotations

import argparse
from collections import deque
import math
import random
import signal
import struct
import subprocess
import sys
import threading
import time
from pathlib import Path
try:
    from PIL import Image
except ImportError as error:
    raise SystemExit("Pillow is required. Install it with: sudo apt install python3-pil") from error


SIZE = 64
BLACK = (0, 0, 0)
DEFAULT_COLOR = (255, 255, 255)
MAGMA_HEX = (
    "4B2991",
    "5A2995",
    "692A99",
    "782B9D",
    "872CA2",
    "952EA0",
    "A3319F",
    "B1339E",
    "C0369D",
    "CA3C97",
    "D44292",
    "DF488D",
    "EA4F88",
    "ED5983",
    "F2637F",
    "F66D7A",
    "FA7876",
    "F98477",
    "F89078",
    "F79C79",
    "F6A97A",
    "F3B584",
    "F1C18E",
    "EFCC98",
    "EDD9A3",
)
MAGMA_PALETTE = tuple(
    (
        index / (len(MAGMA_HEX) - 1),
        (
            int(hex_value[0:2], 16),
            int(hex_value[2:4], 16),
            int(hex_value[4:6], 16),
        ),
    )
    for index, hex_value in enumerate(MAGMA_HEX)
)


def magma_color(value: float) -> tuple[int, int, int]:
    value = max(0.0, min(1.0, value))

    for index in range(1, len(MAGMA_PALETTE)):
        left_stop, left_color = MAGMA_PALETTE[index - 1]
        right_stop, right_color = MAGMA_PALETTE[index]
        if value <= right_stop:
            span = right_stop - left_stop
            amount = 0.0 if span == 0 else (value - left_stop) / span
            return tuple(
                round(left_color[channel] + (right_color[channel] - left_color[channel]) * amount)
                for channel in range(3)
            )  # type: ignore[return-value]

    return MAGMA_PALETTE[-1][1]


class ChimeSynth:
    def __init__(
        self,
        volume: float,
        duration: float,
        sample_rate: int,
        max_pending: int,
        device: str,
    ) -> None:
        self.volume = volume
        self.duration = duration
        self.sample_rate = sample_rate
        self.pending: deque[tuple[float, float]] = deque(maxlen=max_pending)
        self.lock = threading.Lock()
        self.running = True
        self.process: subprocess.Popen[bytes] | None = None
        self.thread: threading.Thread | None = None
        self.device = device
        self._start()

    def _start(self) -> None:
        command = [
            "aplay",
            "-q",
            "-t",
            "raw",
            "-f",
            "S16_LE",
            "-r",
            str(self.sample_rate),
            "-c",
            "1",
        ]
        if self.device:
            command[1:1] = ["-D", self.device]

        try:
            self.process = subprocess.Popen(command, stdin=subprocess.PIPE)
        except OSError as error:
            print(f"Audio disabled: {error}", file=sys.stderr)
            self.running = False
            return

        self.thread = threading.Thread(target=self._audio_loop, daemon=True)
        self.thread.start()

    def trigger(self, x_pos: int, y_pos: int, intensity: float) -> None:
        if not self.running:
            return

        scale = (0, 2, 4, 7, 9, 12, 14, 16)
        degree = (x_pos * 3 + y_pos * 5) % len(scale)
        octave = max(0, min(3, (SIZE - 1 - y_pos) // 16))
        frequency = 174.61 * (2 ** ((scale[degree] + octave * 12) / 12))
        gain = self.volume * max(0.18, min(1.0, intensity))

        with self.lock:
            self.pending.append((frequency, gain))

    def stop(self) -> None:
        self.running = False
        if self.thread:
            self.thread.join(timeout=0.5)
        if self.process and self.process.stdin:
            self.process.stdin.close()
        if self.process:
            self.process.terminate()

    def _audio_loop(self) -> None:
        if not self.process or not self.process.stdin:
            return

        active: list[dict[str, float]] = []
        chunk_size = 512
        attack = 0.018

        while self.running:
            with self.lock:
                while self.pending:
                    frequency, gain = self.pending.popleft()
                    active.append({"frequency": frequency, "gain": gain, "phase": 0.0, "age": 0.0})

            chunk = bytearray()
            for _ in range(chunk_size):
                sample = 0.0
                for note in active:
                    age = note["age"]
                    if age < self.duration:
                        attack_level = min(1.0, age / attack)
                        envelope = attack_level * math.exp(-4.8 * age / self.duration)
                        sample += math.sin(note["phase"]) * note["gain"] * envelope
                        note["phase"] += math.tau * note["frequency"] / self.sample_rate
                    note["age"] += 1 / self.sample_rate

                sample = max(-1.0, min(1.0, sample))
                chunk.extend(struct.pack("<h", round(sample * 32767)))

            active = [note for note in active if note["age"] < self.duration]

            try:
                self.process.stdin.write(chunk)
                self.process.stdin.flush()
            except (BrokenPipeError, OSError):
                self.running = False
                break


class Kaleidoscope:
    def __init__(
        self,
        color: tuple[int, int, int],
        magma: bool,
        fade: float,
        ink: float,
        step_stride: int,
        turn_chance: float,
        curve_chance: float,
        speed: float,
        brush_radius: float,
        neighbor_boost_threshold: int,
        mirrors: int,
        spark_count: int,
        spark_chance: float,
        spark_brightness: float,
        spark_distance: float,
        spark_collision_threshold: float,
        chime_synth: ChimeSynth | None = None,
        chime_threshold: float = 0.12,
    ) -> None:
        self.random = random.SystemRandom()
        self.color = color
        self.magma = magma
        self.fade = fade
        self.ink = ink
        self.step_stride = step_stride
        self.turn_chance = turn_chance
        self.curve_chance = curve_chance
        self.speed = speed
        self.brush_radius = brush_radius
        self.neighbor_boost_threshold = neighbor_boost_threshold
        self.mirrors = max(1, mirrors)
        self.spark_count = max(0, spark_count)
        self.spark_chance = max(0.0, min(1.0, spark_chance))
        self.spark_brightness = max(0.0, min(0.08, spark_brightness))
        self.spark_distance = max(1.0, spark_distance)
        self.spark_collision_threshold = max(0.0, min(1.0, spark_collision_threshold))
        self.chime_synth = chime_synth
        self.chime_threshold = chime_threshold
        self.cells = [[0.0 for _ in range(SIZE)] for _ in range(SIZE)]
        self.x = 0.0
        self.y = 0.0
        self.heading = 0.0
        self.curl = 0.0
        self.phase = 0.0
        self.sparks: list[tuple[float, float, float, float, int]] = []
        self.reset(0.0)

    def reset(self, now: float) -> None:
        for row in self.cells:
            for x_pos in range(SIZE):
                row[x_pos] = 0.0
        self.sparks = []

        center = (SIZE - 1) / 2
        self.x = center + self.random.uniform(-4.0, 4.0)
        self.y = center + self.random.uniform(-4.0, 4.0)
        self.heading = self.random.random() * math.tau
        self.curl = self.random.uniform(-0.035, 0.035)
        self.phase = self.random.random() * math.tau
        self._seed_random_pattern()

    def update(self, _now: float) -> None:
        self._fade()
        self._move_sparks()
        for _ in range(self.step_stride):
            self._step()

    def render_pixels(self) -> list[tuple[int, int, int]]:
        pixels = [BLACK for _ in range(SIZE * SIZE)]
        red, green, blue = self.color

        for y_pos, row in enumerate(self.cells):
            for x_pos, value in enumerate(row):
                if value > 0.01:
                    if self.magma:
                        if value > 0.08 and self._lit_neighbor_count(x_pos, y_pos) >= self.neighbor_boost_threshold:
                            pixels[y_pos * SIZE + x_pos] = DEFAULT_COLOR
                        else:
                            pixels[y_pos * SIZE + x_pos] = magma_color(value)
                        continue

                    if value > 0.08 and self._lit_neighbor_count(x_pos, y_pos) >= self.neighbor_boost_threshold:
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
        center = (SIZE - 1) / 2
        dx = x_pos - center
        dy = y_pos - center
        points = []

        for index in range(self.mirrors):
            angle = math.tau * index / self.mirrors
            cos_angle = math.cos(angle)
            sin_angle = math.sin(angle)
            points.append((
                center + dx * cos_angle - dy * sin_angle,
                center + dx * sin_angle + dy * cos_angle,
            ))

        return points

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
                old_value = self.cells[y_cell][x_cell]
                added = amount * weight
                new_value = min(1.0, old_value + added)
                self.cells[y_cell][x_cell] = new_value

                if (
                    self.spark_count
                    and old_value >= self.spark_collision_threshold
                    and added > 0.04
                    and self.random.random() < self.spark_chance
                ):
                    self._emit_sparks(x_cell, y_cell)

                if (
                    self.chime_synth
                    and old_value < self.chime_threshold <= new_value
                    and added > 0.04
                ):
                    self.chime_synth.trigger(x_cell, y_cell, new_value)

    def _emit_sparks(self, x_pos: int, y_pos: int) -> None:
        center = (SIZE - 1) / 2
        if x_pos == center and y_pos == center:
            base_angle = self.random.random() * math.tau
        else:
            base_angle = math.atan2(y_pos - center, x_pos - center)

        for _ in range(self.spark_count):
            angle = base_angle + self.random.uniform(-0.9, 0.9)
            speed = self.random.uniform(0.8, 1.45)
            travel = self.random.uniform(2.5, self.spark_distance)
            life = max(2, round(travel / speed))
            spark_x = x_pos + math.cos(angle) * 0.9
            spark_y = y_pos + math.sin(angle) * 0.9
            spark = (
                spark_x,
                spark_y,
                math.cos(angle) * speed,
                math.sin(angle) * speed,
                life,
            )
            self.sparks.append(spark)
            self._draw_spark(spark_x, spark_y)

        if len(self.sparks) > 900:
            self.sparks = self.sparks[-900:]

    def _move_sparks(self) -> None:
        next_sparks = []

        for x_pos, y_pos, velocity_x, velocity_y, life in self.sparks:
            x_pos += velocity_x
            y_pos += velocity_y
            life -= 1

            if life <= 0:
                continue

            if self._draw_spark(x_pos, y_pos):
                next_sparks.append((
                    x_pos,
                    y_pos,
                    velocity_x * 0.96,
                    velocity_y * 0.96,
                    life,
                ))

        self.sparks = next_sparks

    def _draw_spark(self, x_pos: float, y_pos: float) -> bool:
        spark_x = round(x_pos)
        spark_y = round(y_pos)

        if not (0 <= spark_x < SIZE and 0 <= spark_y < SIZE):
            return False

        self.cells[spark_y][spark_x] = max(
            self.cells[spark_y][spark_x],
            self.spark_brightness,
        )
        return True

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
    color_value = value.strip()
    hex_value = color_value.removeprefix("#")
    if len(hex_value) in (3, 6) and all(char in "0123456789abcdefABCDEF" for char in hex_value):
        if len(hex_value) == 3:
            hex_value = "".join(char * 2 for char in hex_value)
        return (
            int(hex_value[0:2], 16),
            int(hex_value[2:4], 16),
            int(hex_value[4:6], 16),
        )

    parts = value.split(",")
    if len(parts) != 3:
        raise argparse.ArgumentTypeError("color must be #RRGGBB or R,G,B")

    try:
        color = tuple(max(0, min(255, int(part))) for part in parts)
    except ValueError as error:
        raise argparse.ArgumentTypeError("color must be #RRGGBB or numeric R,G,B") from error

    return color  # type: ignore[return-value]


def create_state(args: argparse.Namespace, chime_synth: ChimeSynth | None = None) -> Kaleidoscope:
    return Kaleidoscope(
        color=args.color,
        magma=args.magma,
        fade=args.fade,
        ink=args.ink,
        step_stride=args.step_stride,
        turn_chance=args.turn_chance,
        curve_chance=args.curve_chance,
        speed=args.speed,
        brush_radius=args.brush_radius,
        neighbor_boost_threshold=args.neighbor_boost_threshold,
        mirrors=args.mirrors,
        spark_count=args.spark_count,
        spark_chance=args.spark_chance,
        spark_brightness=args.spark_brightness,
        spark_distance=args.spark_distance,
        spark_collision_threshold=args.spark_collision_threshold,
        chime_synth=chime_synth,
        chime_threshold=args.chime_threshold,
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

    chime_synth = ChimeSynth(
        volume=args.chime_volume,
        duration=args.chime_duration,
        sample_rate=args.chime_sample_rate,
        max_pending=args.chime_max_pending,
        device=args.audio_device,
    ) if args.audio else None
    state = create_state(args, chime_synth)

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
        if chime_synth:
            chime_synth.stop()
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
    parser.add_argument("--mirrors", type=int, default=8)
    parser.add_argument("--spark-count", type=int, default=3)
    parser.add_argument("--spark-chance", type=float, default=1.0)
    parser.add_argument("--spark-brightness", type=float, default=0.02)
    parser.add_argument("--spark-distance", type=float, default=7.0)
    parser.add_argument("--spark-collision-threshold", type=float, default=0.16)
    parser.add_argument("--audio", action=argparse.BooleanOptionalAction, default=False)
    parser.add_argument("--audio-device", default="")
    parser.add_argument("--chime-volume", type=float, default=0.035)
    parser.add_argument("--chime-duration", type=float, default=0.18)
    parser.add_argument("--chime-sample-rate", type=int, default=22050)
    parser.add_argument("--chime-max-pending", type=int, default=56)
    parser.add_argument("--chime-threshold", type=float, default=0.14)
    parser.add_argument("--color", type=parse_color, default=DEFAULT_COLOR)
    parser.add_argument("--magma", action="store_true")
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
