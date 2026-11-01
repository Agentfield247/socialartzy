"""Placeholder artwork generator (pure standard library, no Pillow needed).

The repository ships a ready-made ``art/placeholder.png``; this script is only
here so you can see how it was produced. Run it from the repository root when
you want to regenerate the placeholder:

    python tests/make_placeholder.py

Real artwork simply gets dropped into ``art/`` and referenced from
``content/queue.csv`` - this generator is not used by the posting workflow.
"""

from __future__ import annotations

import math
import struct
import zlib
from pathlib import Path

WIDTH, HEIGHT = 1080, 1350


def _smoothstep(edge0: float, edge1: float, x: float) -> float:
    t = min(1.0, max(0.0, (x - edge0) / (edge1 - edge0)))
    return t * t * (3 - 2 * t)


def _lerp(a, b, t):
    return tuple(a[i] + (b[i] - a[i]) * t for i in range(3))


def _build_pixels() -> bytearray:
    top = (16, 26, 43)          # deep navy
    bottom = (244, 217, 176)    # warm sand
    blobs = (
        # (cx, cy, radius, colour, strength)
        (0.26, 0.32, 0.42, (193, 102, 107), 0.55),   # rust
        (0.74, 0.58, 0.38, (47, 111, 107), 0.50),    # teal
        (0.52, 0.16, 0.30, (246, 214, 160), 0.45),   # pale gold
        (0.18, 0.78, 0.26, (245, 236, 220), 0.35),   # chalk
    )

    pixels = bytearray(WIDTH * HEIGHT * 3)
    index = 0
    for y in range(HEIGHT):
        v = y / (HEIGHT - 1)
        base = _lerp(top, bottom, _smoothstep(0.0, 1.0, v))
        for x in range(WIDTH):
            u = x / (WIDTH - 1)
            r, g, b = base
            for cx, cy, radius, colour, strength in blobs:
                dx, dy = u - cx, v - cy
                distance = math.hypot(dx, dy * 0.8)
                weight = math.exp(-((distance / radius) ** 2) * 2.2) * strength
                if weight > 0.002:
                    r += (colour[0] - r) * weight
                    g += (colour[1] - g) * weight
                    b += (colour[2] - b) * weight
            # gentle vignette so the piece reads like a photograph of a canvas
            vignette = 1.0 - 0.28 * (((u - 0.5) ** 2 + (v - 0.5) ** 2) ** 1.15) * 4.0
            pixels[index] = max(0, min(255, int(r * vignette)))
            pixels[index + 1] = max(0, min(255, int(g * vignette)))
            pixels[index + 2] = max(0, min(255, int(b * vignette)))
            index += 3
    return pixels


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def write_png(path: Path, pixels: bytearray) -> None:
    raw = bytearray()
    stride = WIDTH * 3
    for row in range(HEIGHT):
        raw.append(0)  # filter type 0 (None)
        raw += pixels[row * stride : (row + 1) * stride]

    header = struct.pack(">IIBBBBB", WIDTH, HEIGHT, 8, 2, 0, 0, 0)  # 8-bit RGB
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("wb") as handle:
        handle.write(b"\x89PNG\r\n\x1a\n")
        handle.write(_chunk(b"IHDR", header))
        handle.write(_chunk(b"IDAT", zlib.compress(bytes(raw), 9)))
        handle.write(_chunk(b"IEND", b""))


def main() -> None:
    target = Path(__file__).resolve().parent.parent / "art" / "placeholder.png"
    write_png(target, _build_pixels())
    print(f"Wrote {target} ({target.stat().st_size / 1024:.0f} KiB, {WIDTH}x{HEIGHT})")


if __name__ == "__main__":
    main()