"""A minimal PNG reader (8-bit RGB/RGBA/grey/palette, non-interlaced), standard library only.

Enough to read the raster images that web map services (WMS GetMap) return.
"""

from __future__ import annotations

import struct
import zlib

_CHANNELS = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}


def read_png(data: bytes) -> tuple[int, int, int, list[bytes], list[tuple[int, int, int]] | None]:
    """(width, height, channels, rows, palette): each row holds `width * channels` bytes after unfiltering."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("not a PNG file")
    pos, idat, palette = 8, [], None
    width = height = depth = ctype = interlace = None
    while pos < len(data):
        n, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + n]
        if kind == b"IHDR":
            width, height, depth, ctype, _, _, interlace = struct.unpack(">IIBBBBB", body)
        elif kind == b"PLTE":
            palette = [tuple(body[k:k + 3]) for k in range(0, n, 3)]
        elif kind == b"IDAT":
            idat.append(body)
        elif kind == b"IEND":
            break
        pos += 12 + n
    if depth != 8 or interlace or ctype not in _CHANNELS:
        raise ValueError(f"unsupported PNG: depth {depth}, colour type {ctype}, interlace {interlace}")
    bpp = _CHANNELS[ctype]
    stride = width * bpp
    raw = zlib.decompress(b"".join(idat))
    rows: list[bytes] = []
    prev = bytes(stride)
    p = 0
    for _ in range(height):
        f = raw[p]
        line = bytearray(raw[p + 1:p + 1 + stride])
        p += 1 + stride
        if f == 1:
            for x in range(bpp, stride):
                line[x] = (line[x] + line[x - bpp]) & 255
        elif f == 2:
            line = bytearray((a + b) & 255 for a, b in zip(line, prev))
        elif f == 3:
            for x in range(stride):
                left = line[x - bpp] if x >= bpp else 0
                line[x] = (line[x] + ((left + prev[x]) >> 1)) & 255
        elif f == 4:
            for x in range(stride):
                a = line[x - bpp] if x >= bpp else 0
                b = prev[x]
                c = prev[x - bpp] if x >= bpp else 0
                pa, pb, pc = abs(b - c), abs(a - c), abs(a + b - 2 * c)
                line[x] = (line[x] + (a if pa <= pb and pa <= pc else b if pb <= pc else c)) & 255
        elif f != 0:
            raise ValueError(f"bad PNG filter {f}")
        rows.append(bytes(line))
        prev = line
    return width, height, bpp, rows, palette
