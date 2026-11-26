"""Land cover of Europe in CORINE's 44 classes, 2018: OpenGeoHub's EU land-cover map (30 m, EPSG:3035), read from its
cloud-optimised GeoTIFF at full resolution and kept as a 480 m nearest-neighbour sample (its own overviews average
class numbers, which mixes up categories)."""

from __future__ import annotations

import json
import os
import re
import struct

from ..core.cog import read_levels
from ..core.paths import INTERIM
from ..core.source import Source, SourceInfo

YEAR = 2018
URL = (f"https://s3.ecodatacube.eu/arco/lcv_landcover.hcl_lucas.corine.eml_f_30m_0..0cm_{YEAR}0101_{YEAR}1231"
       "_eumap_epsg3035_v0.2.tif")
SLD_URL = "https://s3.ecodatacube.eu/arco/lcv_landcover.hcl_lucas.corine.eml_f_30m_0..0cm_eumap_epsg3035_v0.2.sld"
HEAD = 524288  # the overview IFDs and their tile tables sit in the first bytes
RASTER = "corine_eu.bin"  # the decoded raster, one byte per pixel, rows top to bottom (in data/interim/)

# CLC level-3 class → (French name, NLCD-like group code the world builder uses).
# NLCD-like codes: 11 water, 12 ice, 21 green urban, 22/23/24 built-up, 31 barren, 41/42/43 forest, 52 scrub,
# 71 grassland, 81 pasture, 82 crops, 95 wetland.
CLASSES = {
    111: ("Continuous urban fabric", 24), 112: ("Discontinuous urban fabric", 22),
    121: ("Industrial or commercial units", 23), 122: ("Road and rail networks", 23), 123: ("Port areas", 23),
    124: ("Airports", 23), 131: ("Mineral extraction sites", 31), 132: ("Dump sites", 23),
    133: ("Construction sites", 23), 141: ("Green urban areas", 21), 142: ("Sport and leisure facilities", 21),
    211: ("Non-irrigated arable land", 82), 212: ("Permanently irrigated land", 82), 213: ("Rice fields", 82),
    221: ("Vineyards", 82), 222: ("Fruit trees and berry plantations", 82), 223: ("Olive groves", 82),
    231: ("Pastures", 81), 241: ("Annual crops associated with permanent crops", 82),
    242: ("Complex cultivation patterns", 81), 243: ("Agriculture with significant natural vegetation", 81),
    244: ("Agro-forestry areas", 81), 311: ("Broad-leaved forest", 41), 312: ("Coniferous forest", 42),
    313: ("Mixed forest", 43), 321: ("Natural grasslands", 71), 322: ("Moors and heathland", 52),
    323: ("Sclerophyllous vegetation", 52), 324: ("Transitional woodland-shrub", 52),
    331: ("Beaches, dunes, sands", 31), 332: ("Bare rocks", 31), 333: ("Sparsely vegetated areas", 71),
    334: ("Burnt areas", 52), 335: ("Glaciers and perpetual snow", 12), 411: ("Inland marshes", 95),
    412: ("Peat bogs", 95), 421: ("Salt marshes", 95), 422: ("Salines", 95), 423: ("Intertidal flats", 95),
    511: ("Water courses", 11), 512: ("Water bodies", 11), 521: ("Coastal lagoons", 11), 522: ("Estuaries", 11),
    523: ("Sea and ocean", 11),
}


class CorineEu(Source):
    info = SourceInfo(
        id="corine_eu",
        title=f"Land cover of Europe {YEAR}, CORINE nomenclature (OpenGeoHub EcoDataCube)",
        publisher="OpenGeoHub Foundation (Geo-harmonizer project), from CORINE Land Cover (Copernicus) and LUCAS (Eurostat)",
        homepage="https://ecodatacube.eu/",
        license="CC BY 4.0",
        description=f"A {YEAR} land-cover map in the 44 classes of CORINE Land Cover, predicted at 30 m by machine "
        "learning on Landsat imagery, trained on CORINE and on the LUCAS survey points (Witjes et al., 2022). Its "
        "full-resolution tiles are read once and one 30 m pixel is kept every 480 m (the file's own overviews average "
        "class numbers, so they cannot be used for categories). Each hex's biome (forest, heath, grassland, cropland, "
        "wetland, town…) and its land shares come from a few hundred of those points inside it. The European "
        "Environment Agency's CORINE service could not be reached; this map uses the same nomenclature.",
        used_for=["Hex land cover (biomes)", "Shares of forest, cropland, pasture, built-up land"],
    )

    def _reader(self):
        head = (self.raw_dir / "head.bin").read_bytes()
        tail_start = struct.unpack("<Q", head[8:16])[0]
        tail_path = self.raw_dir / "tail.bin"
        tail = tail_path.read_bytes() if tail_path.exists() else b""

        def read(off, n):
            if off + n <= len(head):
                return head[off:off + n]
            if tail and tail_start <= off and off + n <= tail_start + len(tail):
                return tail[off - tail_start:off - tail_start + n]
            raise LookupError(f"bytes {off}-{off + n} are not cached")
        return read, tail_start

    STEP = 16  # one 30 m pixel in 16 along each axis: a 480 m nearest-neighbour sample of the full-resolution map
    SAMPLE = "sample_16.bin"

    def fetch(self, force=False):
        self.download(URL, "head.bin", force=force, headers={"Range": f"bytes=0-{HEAD - 1}"}, expect_binary=True)
        head = (self.raw_dir / "head.bin").read_bytes()
        if head[:4] != b"II+\x00":
            raise ValueError("the land-cover file is not a little-endian BigTIFF")
        tail_start = struct.unpack("<Q", head[8:16])[0]
        if tail_start >= HEAD:  # the full-resolution IFD was rewritten at the end of the file
            self.download(URL, "tail.bin", force=force, headers={"Range": f"bytes={tail_start}-"}, expect_binary=True)
        self.download(SLD_URL, "legend.sld", force=force)
        if (self.raw_dir / self.SAMPLE).exists() and not force:
            return
        if self.offline:
            raise RuntimeError("corine_eu: the full-resolution sample is not cached and --offline")
        self._sample_full_resolution()

    def _sample_full_resolution(self):
        """The file's overviews average class numbers (arable 12 and pasture 18 make "vineyard" 15), so they are not
        usable for a categorical map. Read every full-resolution tile instead (about 1 GB, one request per row of
        tiles, in parallel) and keep one pixel in STEP along each axis, centred in its block."""
        import concurrent.futures
        import urllib.request
        import zlib

        from ..core.fetch import USER_AGENT
        read, _ = self._reader()
        full = read_levels(read)[0]
        step, tw, th = self.STEP, full.tile_w, full.tile_h
        w, h = -(-full.width // step), -(-full.height // step)
        out = bytearray(w * h)
        per_tile = tw // step

        def fetch_row(tr):
            ids = [tr * full.tiles_across + tc for tc in range(full.tiles_across)]
            spans = [(full.offsets[t], full.counts[t]) for t in ids if full.counts[t]]
            if not spans:
                return tr, b"", 0
            start = min(o for o, _ in spans)
            end = max(o + n for o, n in spans)
            req = urllib.request.Request(URL, headers={"User-Agent": USER_AGENT, "Range": f"bytes={start}-{end - 1}"})
            for attempt in range(4):
                try:
                    with urllib.request.urlopen(req, timeout=300) as r:
                        return tr, r.read(), start
                except OSError:
                    if attempt == 3:
                        raise
            return tr, b"", 0

        done = 0
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            for tr, data, start in pool.map(fetch_row, range(full.tiles_down)):
                for tc in range(full.tiles_across):
                    t = tr * full.tiles_across + tc
                    off, n = full.offsets[t], full.counts[t]
                    if not n:
                        continue
                    tile = zlib.decompress(data[off - start:off - start + n])
                    for i in range(per_tile):
                        gy = tr * per_tile + i
                        if gy >= h:
                            break
                        row = tile[(i * step + step // 2) * tw:(i * step + step // 2 + 1) * tw][step // 2::step]
                        gx0 = tc * per_tile
                        k = min(per_tile, w - gx0)
                        out[gy * w + gx0:gy * w + gx0 + k] = row[:k]
                done += 1
                if done % 20 == 0:
                    print(f"    {done}/{full.tiles_down} rows of tiles", flush=True)
        tmp = self.raw_dir / f".{self.SAMPLE}.tmp"
        tmp.write_bytes(bytes(out))
        os.replace(tmp, self.raw_dir / self.SAMPLE)
        (self.raw_dir / "sample_16.json").write_text(json.dumps({"width": w, "height": h, "step": step,
                                                                 "pixel_m": full.scale[0] * step}))

    def process(self):
        read, _ = self._reader()
        full = read_levels(read)[0]
        meta = json.loads((self.raw_dir / "sample_16.json").read_text())
        values = {}
        for q, label in re.findall(r'quantity="(\d+)" label="([^"]+)"', (self.raw_dir / "legend.sld").read_text()):
            code = int(label.split(" - ")[1])
            if code in CLASSES:
                values[int(q)] = code
        raster = (self.raw_dir / self.SAMPLE).read_bytes()
        INTERIM.mkdir(parents=True, exist_ok=True)
        tmp = INTERIM / f".{RASTER}.{os.getpid()}.tmp"
        tmp.write_bytes(raster)
        os.replace(tmp, INTERIM / RASTER)
        w, h, pixel = meta["width"], meta["height"], meta["pixel_m"]
        counts = {}
        for v in raster[::97]:
            counts[v] = counts.get(v, 0) + 1
        print(f"    {w}×{h} pixels of {pixel:.0f} m (nearest sample of the 30 m map); values: "
              f"{sorted(counts.items(), key=lambda t: -t[1])[:8]}")
        files = ["head.bin", "legend.sld", self.SAMPLE, "sample_16.json"] + (["tail.bin"] if (self.raw_dir / "tail.bin").exists() else [])
        return {
            "vintage": f"OpenGeoHub EU land cover {YEAR} (CORINE classes), 30 m map sampled every {pixel:.0f} m",
            "_files": files,
            "raster": RASTER,
            "crs": "EPSG:3035",
            "width": w, "height": h, "pixel": pixel,
            # left and top edges of the sampled raster's first pixel block (EPSG:3035 metres); each pixel is the
            # 30 m value at the centre of its block
            "x0": full.tie[3], "y0": full.tie[4],
            "values": {str(v): code for v, code in values.items()},
            "classes": {str(code): name for code, (name, _) in CLASSES.items()},
            "nlcd": {str(code): nlcd for code, (_, nlcd) in CLASSES.items()},
        }
