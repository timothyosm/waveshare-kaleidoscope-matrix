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
    from PIL import Image, ImageDraw, ImageFont
except ImportError as error:
    raise SystemExit("Pillow is required. Install it with: sudo apt install python3-pil") from error


SIZE = 64
LETTERS = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
DIRECTIONS = ((0, -1), (1, 0), (0, 1), (-1, 0))
BLACK = (0, 0, 0)
RED = (255, 0, 0)
DEFAULT_FONT = Path(__file__).parent / "assets/fonts/MonsieurLaDoulaise-Regular.ttf"


def point_key(point: tuple[int, int]) -> str:
    return f"{point[0]},{point[1]}"


def distance_squared(a: tuple[int, int], b: tuple[int, int]) -> int:
    dx = a[0] - b[0]
    dy = a[1] - b[1]
    return dx * dx + dy * dy


class LetterRenderer:
    def __init__(self, font_path: Path, font_size: int = 58, y_offset: int = 4) -> None:
        self.font_path = font_path
        self.font_size = font_size
        self.y_offset = y_offset
        self._font = self._load_font()
        self._cache: dict[str, list[tuple[int, int]]] = {}

    def _load_font(self) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
        if self.font_path.exists():
            return ImageFont.truetype(str(self.font_path), self.font_size)

        return ImageFont.load_default()

    def create_letter_reveal(self, letter: str) -> list[tuple[int, int]]:
        if letter in self._cache:
            return self._cache[letter]

        mask = self._create_letter_mask(letter)
        if not mask:
            self._cache[letter] = []
            return []

        skeleton = self._skeletonize(mask)
        isolated_cell = self._find_most_isolated_cell(mask)
        start_cell = self._find_nearest_cell(skeleton, isolated_cell)
        stroke_path = self._order_stroke_path(skeleton, start_cell)
        stroke_index = {point_key(cell): index for index, cell in enumerate(stroke_path)}

        reveal = [
            item["cell"]
            for item in sorted(
                (
                    {
                        "cell": cell,
                        "order": stroke_index.get(point_key(nearest), 0),
                        "distance": distance_squared(cell, nearest),
                    }
                    for cell in mask
                    for nearest in (self._find_nearest_cell(stroke_path, cell),)
                ),
                key=lambda item: (item["order"], item["distance"]),
            )
        ]
        self._cache[letter] = reveal
        return reveal

    def _create_letter_mask(self, letter: str) -> list[tuple[int, int]]:
        image = Image.new("L", (SIZE, SIZE), 0)
        draw = ImageDraw.Draw(image)
        bbox = draw.textbbox((0, 0), letter, font=self._font)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        x = (SIZE - text_width) / 2 - bbox[0]
        y = (SIZE - text_height) / 2 - bbox[1] + self.y_offset

        draw.text((x, y), letter, font=self._font, fill=255)
        pixels = image.load()

        return [
            (x_pos, y_pos)
            for y_pos in range(SIZE)
            for x_pos in range(SIZE)
            if pixels[x_pos, y_pos] > 12
        ]

    @staticmethod
    def _find_most_isolated_cell(mask: list[tuple[int, int]]) -> tuple[int, int]:
        most_isolated = mask[0]
        largest_nearest_distance = -1

        for cell in mask:
            nearest_distance = min(
                distance_squared(cell, other)
                for other in mask
                if cell is not other
            )

            if nearest_distance > largest_nearest_distance:
                largest_nearest_distance = nearest_distance
                most_isolated = cell

        return most_isolated

    @staticmethod
    def _build_binary_grid(mask: list[tuple[int, int]]) -> list[list[bool]]:
        grid = [[False for _ in range(SIZE)] for _ in range(SIZE)]

        for x_pos, y_pos in mask:
            grid[y_pos][x_pos] = True

        return grid

    @staticmethod
    def _neighbor_values(grid: list[list[bool]], x_pos: int, y_pos: int) -> tuple[bool, ...]:
        return (
            grid[y_pos - 1][x_pos],
            grid[y_pos - 1][x_pos + 1],
            grid[y_pos][x_pos + 1],
            grid[y_pos + 1][x_pos + 1],
            grid[y_pos + 1][x_pos],
            grid[y_pos + 1][x_pos - 1],
            grid[y_pos][x_pos - 1],
            grid[y_pos - 1][x_pos - 1],
        )

    def _transition_count(self, grid: list[list[bool]], x_pos: int, y_pos: int) -> int:
        neighbors = self._neighbor_values(grid, x_pos, y_pos)

        return sum(
            1
            for index, value in enumerate(neighbors)
            if not value and neighbors[(index + 1) % len(neighbors)]
        )

    def _thinning_pass(self, grid: list[list[bool]], second_pass: bool) -> bool:
        to_delete: list[tuple[int, int]] = []

        for y_pos in range(1, SIZE - 1):
            for x_pos in range(1, SIZE - 1):
                if not grid[y_pos][x_pos]:
                    continue

                neighbors = self._neighbor_values(grid, x_pos, y_pos)
                neighbor_count = sum(neighbors)
                transitions = self._transition_count(grid, x_pos, y_pos)
                p2, _p3, p4, _p5, p6, _p7, p8, _p9 = neighbors
                first_condition = not (p2 and p4 and p8) if second_pass else not (p2 and p4 and p6)
                second_condition = not (p2 and p6 and p8) if second_pass else not (p4 and p6 and p8)

                if (
                    2 <= neighbor_count <= 6
                    and transitions == 1
                    and first_condition
                    and second_condition
                ):
                    to_delete.append((x_pos, y_pos))

        for x_pos, y_pos in to_delete:
            grid[y_pos][x_pos] = False

        return len(to_delete) > 0

    def _skeletonize(self, mask: list[tuple[int, int]]) -> list[tuple[int, int]]:
        grid = self._build_binary_grid(mask)
        changed = True

        while changed:
            first_changed = self._thinning_pass(grid, False)
            second_changed = self._thinning_pass(grid, True)
            changed = first_changed or second_changed

        skeleton = [
            (x_pos, y_pos)
            for y_pos in range(SIZE)
            for x_pos in range(SIZE)
            if grid[y_pos][x_pos]
        ]

        return skeleton or mask

    @staticmethod
    def _find_nearest_cell(
        cells_to_search: list[tuple[int, int]],
        target: tuple[int, int],
    ) -> tuple[int, int]:
        return min(cells_to_search, key=lambda cell: distance_squared(cell, target))

    def _order_stroke_path(
        self,
        cells_to_order: list[tuple[int, int]],
        start_cell: tuple[int, int],
    ) -> list[tuple[int, int]]:
        remaining = {point_key(cell): cell for cell in cells_to_order}
        ordered: list[tuple[int, int]] = []
        current = start_cell

        while remaining:
            cell = remaining.pop(
                point_key(current),
                self._find_nearest_cell(list(remaining.values()), current),
            )
            ordered.append(cell)

            if remaining:
                current = self._find_nearest_cell(list(remaining.values()), cell)

        return ordered


class Kaleidoscope:
    def __init__(
        self,
        letter_renderer: LetterRenderer,
        letter_delay: float,
        letter_duration: float,
        letter_hold: float,
        color: tuple[int, int, int],
        twinkle_count: int,
        twinkle_chance: float,
    ) -> None:
        self.random = random.SystemRandom()
        self.letter_renderer = letter_renderer
        self.letter_delay = letter_delay
        self.letter_duration = letter_duration
        self.letter_hold = letter_hold
        self.color = color
        self.twinkle_count = twinkle_count
        self.twinkle_chance = twinkle_chance
        self.cells = [[False for _ in range(SIZE)] for _ in range(SIZE)]
        self.ant_x = 0
        self.ant_y = 0
        self.ant_direction = 0
        self.flash_active = False
        self.flash_mask: list[tuple[int, int]] = []
        self.flash_visible_count = 0
        self.next_letter_at = 0.0
        self.next_reveal_at = 0.0
        self.flash_done_at: float | None = None
        self.reveal_interval = 0.0
        self.reset(0.0)

    def reset(self, now: float) -> None:
        for row in self.cells:
            for x_pos in range(SIZE):
                row[x_pos] = False

        self.ant_x = self.random.randrange(SIZE)
        self.ant_y = self.random.randrange(SIZE)
        self.ant_direction = self.random.randrange(len(DIRECTIONS))
        self._seed_random_pattern()
        self.next_letter_at = now + self.letter_delay

    def update(self, now: float) -> None:
        if self.flash_active:
            self._update_flash(now)
            return

        self._step()

        if now >= self.next_letter_at:
            self._start_flash(now)

    def render_pixels(self) -> list[tuple[int, int, int]]:
        pixels = [BLACK for _ in range(SIZE * SIZE)]

        if self.flash_active:
            for x_pos, y_pos in self.flash_mask[: self.flash_visible_count]:
                pixels[y_pos * SIZE + x_pos] = self.color
            self._add_twinkle(pixels)
            return pixels

        for y_pos, row in enumerate(self.cells):
            for x_pos, enabled in enumerate(row):
                if enabled:
                    pixels[y_pos * SIZE + x_pos] = self.color

        ant_index = self.ant_y * SIZE + self.ant_x
        pixels[ant_index] = BLACK if self.cells[self.ant_y][self.ant_x] else self.color
        self._add_twinkle(pixels)
        return pixels

    def _add_twinkle(self, pixels: list[tuple[int, int, int]]) -> None:
        for _ in range(self.twinkle_count):
            if self.random.random() <= self.twinkle_chance:
                index = self.random.randrange(SIZE * SIZE)
                pixels[index] = self.color

    def _update_flash(self, now: float) -> None:
        while self.flash_visible_count < len(self.flash_mask) and now >= self.next_reveal_at:
            self.flash_visible_count += 1
            self.next_reveal_at += self.reveal_interval

        if self.flash_visible_count >= len(self.flash_mask):
            if self.flash_done_at is None:
                self.flash_done_at = now + self.letter_hold
            elif now >= self.flash_done_at:
                self.flash_active = False
                self.flash_visible_count = 0
                self.reset(now)

    def _start_flash(self, now: float) -> None:
        letter = self.random.choice(LETTERS)
        self.flash_mask = self.letter_renderer.create_letter_reveal(letter)
        self.flash_visible_count = 0
        self.flash_active = True
        self.flash_done_at = None
        self.reveal_interval = max(0.008, self.letter_duration / max(1, len(self.flash_mask)))
        self.next_reveal_at = now

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
        letter_renderer=LetterRenderer(args.font, args.font_size, args.letter_y_offset),
        letter_delay=args.letter_delay,
        letter_duration=args.letter_duration,
        letter_hold=args.letter_hold,
        color=args.color,
        twinkle_count=args.twinkle_count,
        twinkle_chance=args.twinkle_chance,
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
    parser.add_argument("--letter-delay", type=float, default=30.0)
    parser.add_argument("--letter-duration", type=float, default=5.0)
    parser.add_argument("--letter-hold", type=float, default=0.25)
    parser.add_argument("--twinkle-count", type=int, default=18)
    parser.add_argument("--twinkle-chance", type=float, default=0.7)
    parser.add_argument("--letter-y-offset", type=int, default=4)
    parser.add_argument("--font-size", type=int, default=58)
    parser.add_argument("--font", type=Path, default=DEFAULT_FONT)
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
