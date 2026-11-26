"""Canopy height of Europe from ETH Zurich's global map (Lang et al., 2023): a deep network trained on NASA's GEDI
spaceborne LiDAR, which measures canopy height from the ISS, and applied to Sentinel-2 images, 10 m, year 2020.

The map is a set of 3° × 3° cloud-optimised GeoTIFFs (EPSG:4326, LZW, 255 = no data). For each tile holding forest
on the CORINE map, the 1/32 overview (1125 × 1125 pixels, about 300 m: each pixel the resampled height of its
block) is read by byte ranges, decoded and kept in data/interim/canopy_eth.bin, one byte per pixel (metres), tile
after tile; the interim JSON lists each tile's corner, size and offset. The lens builder reads it at the hex's
forest land-cover points.
"""

from __future__ import annotations

import base64
import concurrent.futures
import json
import os
import urllib.error
import urllib.request

from ..core.cog import Level, read_levels, tile_values
from ..core.fetch import USER_AGENT, record
from ..core.geo import Laea3035
from ..core.paths import INTERIM
from ..core.source import Source, SourceInfo
from ..core.store import load_interim

SHARE = "cO8or7iOe5dT2Rt"  # the dataset's public libdrive share (read over WebDAV, which serves byte ranges)
BASE = "https://libdrive.ethz.ch/public.php/webdav/3deg_cogs/"
PAGE = f"https://libdrive.ethz.ch/index.php/s/{SHARE}"
NAME = "ETH_GlobalCanopyHeight_10m_2020_{tile}_Map.tif"
OVERVIEW = 32  # read the 1/32 overview: 36000 / 32 = 1125 pixels per tile side
LON, LAT = (-27, 45), (33, 72)  # tiles tried (3° steps); only those with CORINE forest are read
FOREST = {311, 312, 313}
RASTER = "canopy_eth.bin"


def tile_name(lon0: int, lat0: int) -> str:
    """ETH tiles are named after their south-west corner: N48E000 covers 48-51° N, 0-3° E."""
    return f"{'N' if lat0 >= 0 else 'S'}{abs(lat0):02d}{'E' if lon0 >= 0 else 'W'}{abs(lon0):03d}"


class CanopyEth(Source):
    info = SourceInfo(
        id="canopy_eth",
        title="Global canopy height 2020, 10 m (ETH Zurich)",
        publisher="EcoVision Lab, ETH Zurich (Lang, Jetz, Schindler and Wegner, Nature Ecology & Evolution, 2023)",
        homepage="https://langnico.github.io/globalcanopyheight/",
        license="CC BY 4.0",
        description="The height of the canopy everywhere on Earth in 2020 at 10 m, predicted from Sentinel-2 images by "
        "a deep network trained on the canopy heights NASA's GEDI LiDAR measured from the International Space "
        "Station. Read from the dataset's 3° tiles at their 1/32 overview (about 300 m), for the tiles that hold "
        "forest on the CORINE map.",
        used_for=["Lens \"Forest height\""],
    )

    def _get(self, url: str, start: int, end: int) -> bytes:
        auth = base64.b64encode(f"{SHARE}:".encode()).decode()
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Authorization": f"Basic {auth}",
                                                   "Range": f"bytes={start}-{end - 1}"})
        for attempt in range(4):
            try:
                with urllib.request.urlopen(req, timeout=300) as r:
                    return r.read()
            except urllib.error.HTTPError as e:
                if e.code == 404:
                    raise
                if attempt == 3:
                    raise
            except OSError:
                if attempt == 3:
                    raise
        return b""

    def _wanted(self) -> list[tuple[int, int]]:
        """Tiles where a 0.1° lattice meets a CORINE forest pixel."""
        clc = load_interim("corine_eu")
        raster = (INTERIM / clc["raster"]).read_bytes()
        rw, rh, px, rx0, ry0 = clc["width"], clc["height"], clc["pixel"], clc["x0"], clc["y0"]
        forest = {int(v) for v, c in clc["values"].items() if c in FOREST}
        laea = Laea3035()
        out = []
        for lat0 in range(LAT[0], LAT[1], 3):
            for lon0 in range(LON[0], LON[1], 3):
                hit = False
                for j in range(30):
                    for i in range(30):
                        X, Y = laea(lon0 + (i + 0.5) / 10, lat0 + (j + 0.5) / 10)
                        c, r = int((X - rx0) / px), int((ry0 - Y) / px)
                        if 0 <= c < rw and 0 <= r < rh and raster[r * rw + c] in forest:
                            hit = True
                            break
                    if hit:
                        break
                if hit:
                    out.append((lon0, lat0))
        return out

    def fetch(self, force=False):
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        tiles = self._wanted()
        print(f"    {len(tiles)} tiles with forest")

        def one(t):
            name = tile_name(*t)
            data_path, meta_path = self.raw_dir / f"{name}.ov{OVERVIEW}.bin", self.raw_dir / f"{name}.ov{OVERVIEW}.json"
            if meta_path.exists() and data_path.exists() and not force:
                return name, "cached"
            url = BASE + NAME.format(tile=name)
            try:
                head = self._get(url, 0, 1 << 20)
            except urllib.error.HTTPError:
                return name, "missing"

            def read(off, n):
                return head[off:off + n] if off + n <= len(head) else self._get(url, off, off + n)

            levels = read_levels(read)
            lv = min(levels, key=lambda L: abs(L.width - levels[0].width // OVERVIEW))
            start = min(lv.offsets)
            end = max(o + n for o, n in zip(lv.offsets, lv.counts))
            blob = self._get(url, start, end)
            tmp = self.raw_dir / f".{name}.tmp"
            tmp.write_bytes(blob)
            os.replace(tmp, data_path)
            meta_path.write_text(json.dumps({
                "tile": name, "url": url, "width": lv.width, "height": lv.height, "tile_w": lv.tile_w,
                "tile_h": lv.tile_h, "compression": lv.compression, "bits": lv.bits,
                "sample_format": lv.sample_format, "predictor": lv.predictor, "nodata": lv.nodata,
                "offsets": [o - start for o in lv.offsets], "counts": lv.counts,
                "origin": [levels[0].tie[3], levels[0].tie[4]],
                "deg": levels[0].scale[0] * levels[0].width / lv.width,
            }))
            return name, f"{len(blob) / 1e6:.1f} MB"

        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            for k, (name, what) in enumerate(pool.map(one, tiles), 1):
                if what != "cached":
                    print(f"    {k}/{len(tiles)} {name}: {what}", flush=True)
        for meta_path in sorted(self.raw_dir.glob(f"*.ov{OVERVIEW}.json")):
            meta = json.loads(meta_path.read_text())
            record(self.id, meta_path.name.replace(".json", ".bin"), meta["url"],
                   f"1/{OVERVIEW} overview tiles of the COG, byte range of the file")

    def process(self):
        tiles, chunks, offset = [], [], 0
        for meta_path in sorted(self.raw_dir.glob(f"*.ov{OVERVIEW}.json")):
            m = json.loads(meta_path.read_text())
            blob = (self.raw_dir / meta_path.name.replace(".json", ".bin")).read_bytes()
            lv = Level(width=m["width"], height=m["height"], tile_w=m["tile_w"], tile_h=m["tile_h"],
                       compression=m["compression"], offsets=m["offsets"], counts=m["counts"], bits=m["bits"],
                       sample_format=m["sample_format"], predictor=m["predictor"], nodata=m["nodata"])
            w, h = lv.width, lv.height
            img = bytearray(b"\xff" * (w * h))
            for k, (o, n) in enumerate(zip(lv.offsets, lv.counts)):
                if not n:
                    continue
                vals = tile_values(lv, blob[o:o + n]).tobytes()
                tx, ty = k % lv.tiles_across, k // lv.tiles_across
                for r in range(lv.tile_h):
                    y = ty * lv.tile_h + r
                    if y >= h:
                        break
                    x0 = tx * lv.tile_w
                    k_w = min(lv.tile_w, w - x0)
                    img[y * w + x0:y * w + x0 + k_w] = vals[r * lv.tile_w:r * lv.tile_w + k_w]
            tiles.append({"tile": m["tile"], "west": m["origin"][0], "north": m["origin"][1], "deg": m["deg"],
                          "width": w, "height": h, "offset": offset})
            chunks.append(bytes(img))
            offset += w * h
        INTERIM.mkdir(parents=True, exist_ok=True)
        tmp = INTERIM / f".{RASTER}.{os.getpid()}.tmp"
        with open(tmp, "wb") as f:
            for c in chunks:
                f.write(c)
        os.replace(tmp, INTERIM / RASTER)
        print(f"    {len(tiles)} tiles of {tiles[0]['width'] if tiles else 0}² pixels → data/interim/{RASTER}")
        return {
            "vintage": "ETH Global Canopy Height 2020 (10 m), 1/32 overview",
            "_files": [p.name.replace(".json", ".bin") for p in sorted(self.raw_dir.glob(f"*.ov{OVERVIEW}.json"))],
            "raster": RASTER, "nodata": 255, "unit": "m",
            # each tile: west and north edges (degrees), pixel size (degrees), size, byte offset in the raster
            "tiles": tiles,
        }
