#!/usr/bin/env python3
"""Draw the app icons (a ring with one marker dot) as PNGs, standard library only.

    python tools/make_icons.py   # writes app/icons/*.png
"""
import math
import struct
import zlib
from pathlib import Path

BG = (138, 59, 110)      # plum
FG = (255, 255, 255)
OUT = Path(__file__).resolve().parent.parent / "app" / "icons"


def coverage(x: float, y: float) -> float:
    """1.0 where the foreground shape is, in unit coordinates centred on 0."""
    r = math.hypot(x, y)
    ring = abs(r - 0.27) < 0.035
    # marker dot at the top of the ring
    dot = math.hypot(x, y + 0.27) < 0.075
    return 1.0 if ring or dot else 0.0


def render(size: int, ss: int = 4) -> bytes:
    rows = []
    for py in range(size):
        row = bytearray([0])  # filter type 0
        for px in range(size):
            acc = 0.0
            for sy in range(ss):
                for sx in range(ss):
                    x = (px + (sx + 0.5) / ss) / size - 0.5
                    y = (py + (sy + 0.5) / ss) / size - 0.5
                    acc += coverage(x, y)
            a = acc / (ss * ss)
            row += bytes(round(BG[i] * (1 - a) + FG[i] * a) for i in range(3))
        rows.append(bytes(row))
    return b"".join(rows)


def png(size: int) -> bytes:
    def chunk(kind: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xFFFFFFFF)

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0)  # 8-bit RGB
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr)
            + chunk(b"IDAT", zlib.compress(render(size), 9)) + chunk(b"IEND", b""))


def main() -> None:
    OUT.mkdir(parents=True, exist_ok=True)
    for name, size in [("icon-192.png", 192), ("icon-512.png", 512), ("apple-touch-icon.png", 180)]:
        (OUT / name).write_bytes(png(size))
        print(f"wrote {OUT / name}")


if __name__ == "__main__":
    main()
