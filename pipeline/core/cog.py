"""A minimal reader for tiled (Big)TIFF files such as cloud-optimised GeoTIFFs: enough to list the overview levels
and decode 8-bit DEFLATE tiles, standard library only. The bytes come from a `read(offset, n)` callable, so a source
can serve them from cached ranges of a remote file."""

from __future__ import annotations

import array
import struct
import sys
import zlib
from dataclasses import dataclass
from typing import Callable

TYPE_SIZE = {1: 1, 2: 1, 3: 2, 4: 4, 5: 8, 6: 1, 7: 1, 8: 2, 9: 4, 10: 8, 11: 4, 12: 8, 16: 8, 17: 8, 18: 8}
TYPE_FMT = {1: "B", 3: "H", 4: "I", 6: "b", 8: "h", 9: "i", 11: "f", 12: "d", 16: "Q", 17: "q", 18: "Q"}


@dataclass
class Level:
    width: int
    height: int
    tile_w: int
    tile_h: int
    compression: int
    offsets: list[int]
    counts: list[int]
    scale: tuple | None = None  # ModelPixelScale (full-resolution level only)
    tie: tuple | None = None  # ModelTiepoint
    bits: int = 8
    sample_format: int = 1  # 1 unsigned, 2 signed, 3 float
    predictor: int = 1
    nodata: str | None = None

    @property
    def tiles_across(self) -> int:
        return -(-self.width // self.tile_w)

    @property
    def tiles_down(self) -> int:
        return -(-self.height // self.tile_h)


def read_levels(read: Callable[[int, int], bytes]) -> list[Level]:
    """Every image of the file in IFD order (full resolution first, then the overviews)."""
    head = read(0, 16)
    bo = "<" if head[:2] == b"II" else ">"
    big = struct.unpack(bo + "H", head[2:4])[0] == 43
    off = struct.unpack(bo + "Q", head[8:16])[0] if big else struct.unpack(bo + "I", head[4:8])[0]
    esz, cfmt, ofmt = (20, "Q", "Q") if big else (12, "H", "I")
    levels = []
    while off:
        n = struct.unpack(bo + cfmt, read(off, 8 if big else 2))[0]
        body = read(off + (8 if big else 2), n * esz + (8 if big else 4))
        tags = {}
        for i in range(n):
            e = body[i * esz:(i + 1) * esz]
            tag, typ = struct.unpack(bo + "HH", e[:4])
            cnt = struct.unpack(bo + ("Q" if big else "I"), e[4:12] if big else e[4:8])[0]
            raw = e[12:20] if big else e[8:12]
            size = TYPE_SIZE.get(typ, 1) * cnt
            data = raw[:size] if size <= len(raw) else read(struct.unpack(bo + ofmt, raw)[0], size)
            if typ in TYPE_FMT:
                tags[tag] = struct.unpack(bo + TYPE_FMT[typ] * cnt, data)
            else:
                tags[tag] = data
        off = struct.unpack(bo + ofmt, body[n * esz:n * esz + (8 if big else 4)])[0]
        if 322 not in tags:
            continue  # a stripped image (masks, thumbnails): not used here
        nod = tags.get(42113)
        levels.append(Level(width=tags[256][0], height=tags[257][0], tile_w=tags[322][0], tile_h=tags[323][0],
                            compression=tags.get(259, (1,))[0], offsets=list(tags[324]), counts=list(tags[325]),
                            scale=tags.get(33550), tie=tags.get(33922), bits=tags.get(258, (8,))[0],
                            sample_format=tags.get(339, (1,))[0], predictor=tags.get(317, (1,))[0],
                            nodata=nod.rstrip(b"\0").decode() if isinstance(nod, bytes) else None))
    return levels


def decode_tile(level: Level, data: bytes) -> bytes:
    """One 8-bit tile, tile_w × tile_h bytes, rows top to bottom."""
    if level.compression in (8, 32946):
        out = zlib.decompress(data)
    elif level.compression == 1:
        out = data
    else:
        raise ValueError(f"TIFF compression {level.compression} is not supported")
    if len(out) != level.tile_w * level.tile_h:
        raise ValueError(f"tile decodes to {len(out)} bytes, expected {level.tile_w * level.tile_h}")
    return out


TYPECODE = {(8, 1): "B", (8, 2): "b", (16, 1): "H", (16, 2): "h", (32, 1): "I", (32, 2): "i", (32, 3): "f", (64, 3): "d"}


def tile_values(level: Level, data: bytes) -> array.array:
    """One tile as an array of numbers (tile_w × tile_h, rows top to bottom), any integer or float sample type, with
    the horizontal-differencing predictor undone for integers."""
    raw = zlib.decompress(data) if level.compression in (8, 32946) else data
    tc = TYPECODE[(level.bits, level.sample_format)]
    vals = array.array(tc)
    vals.frombytes(raw)
    if sys.byteorder != "little" and vals.itemsize > 1:
        vals.byteswap()
    if level.predictor == 2 and level.sample_format != 3:
        w = level.tile_w
        mask = (1 << level.bits) - 1
        for r in range(level.tile_h):
            base = r * w
            acc = vals[base]
            for c in range(1, w):
                acc = (acc + vals[base + c]) & mask if level.sample_format == 1 else acc + vals[base + c]
                vals[base + c] = acc
    elif level.predictor not in (1, 2):
        raise ValueError(f"TIFF predictor {level.predictor} is not supported")
    return vals
