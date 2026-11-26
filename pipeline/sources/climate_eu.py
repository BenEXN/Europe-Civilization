"""Climate of Europe 2000-2019 from OpenGeoHub's EcoDataCube: monthly mean air temperature (ERA5, downscaled to 1 km
with CHELSA) and monthly precipitation (CHELSA, 1 km), EPSG:3035 cloud-optimised GeoTIFFs.

The monthly files add up to several gigabytes, so fetch() reads them one by one and keeps only running sums on a coarse
grid: temperature sampled every 5 km (one pixel in 25), precipitation from each file's ~8 km overview (read by byte
ranges). It saves, per decade (2000-2009, 2010-2019), the mean monthly temperature and the mean yearly precipitation
(2010-2018 for precipitation: the series stops in June 2019), as float32 rasters in data/raw/climate_eu/."""

from __future__ import annotations

import array
import json
import os
import urllib.request

from ..core.cog import read_levels, tile_values
from ..core.fetch import USER_AGENT
from ..core.paths import INTERIM
from ..core.source import Source, SourceInfo

T_URL = ("https://s3.ecodatacube.eu/arco/clm_air.temp_era5.copernicus_av_1km_200..200cm_{y}{m:02d}01_{y}{m:02d}{d}"
         "_eumap_epsg3035_v0.1.tif")
P_URL = ("https://s3.ecodatacube.eu/arco/accum.precipitation_chelsa.montlhy_m_1km_s_{y}{m:02d}01_{y}{m:02d}{d}"
         "_eu_epsg.3035_v20240531.tif")
DAYS = [31, 28, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31]
DECADES = {"2000s": (2000, 2009), "2010s": (2010, 2019)}
P_LAST_FULL_YEAR = 2018
T_STEP = 5  # temperature: one pixel in 5 along each axis (5 km)
P_TARGET_M = 8000  # precipitation: the overview nearest 8 km (a few points per hex; rain is a smooth field)


def _days(y, m):
    return DAYS[m - 1]  # the file names give February 28 days, leap years included


class RangeReader:
    """Byte ranges of a remote file, fetched in 256 kB blocks and kept in memory for the file's lifetime."""

    BLOCK = 262144

    def __init__(self, url: str):
        self.url, self.blocks = url, {}

    def _block(self, k):
        if k not in self.blocks:
            req = urllib.request.Request(self.url, headers={"User-Agent": USER_AGENT,
                                                            "Range": f"bytes={k * self.BLOCK}-{(k + 1) * self.BLOCK - 1}"})
            with urllib.request.urlopen(req, timeout=120) as r:
                self.blocks[k] = r.read()
        return self.blocks[k]

    def __call__(self, off, n):
        out = b""
        while n > 0:
            k, o = divmod(off, self.BLOCK)
            chunk = self._block(k)[o:o + n]
            if not chunk:
                raise EOFError(self.url)
            out += chunk
            off += len(chunk)
            n -= len(chunk)
        return out


def _sample(url: str, target_m: float | None, step: int):
    """(grid meta, values array.array('f') with nan for no data) of one monthly file: the level nearest target_m
    (None = full resolution), every `step`-th pixel."""
    read = RangeReader(url)
    levels = read_levels(read)
    full = levels[0]
    lv = full if target_m is None else min(levels, key=lambda l: abs(full.scale[0] * full.width / l.width - target_m))
    px = full.scale[0] * full.width / lv.width
    nodata = float(lv.nodata) if lv.nodata not in (None, "") else None
    w, h = lv.width // step, lv.height // step
    out = array.array("f", [float("nan")]) * (w * h)
    for t, (off, cnt) in enumerate(zip(lv.offsets, lv.counts)):
        if not cnt:
            continue
        tr, tc = divmod(t, lv.tiles_across)
        vals = tile_values(lv, read(off, cnt))
        y0, x0 = tr * lv.tile_h, tc * lv.tile_w
        for rr in range((-y0) % step, lv.tile_h, step):
            gy = (y0 + rr) // step
            if gy >= h:
                break
            row = vals[rr * lv.tile_w:(rr + 1) * lv.tile_w]
            c0 = (-x0) % step
            picks = row[c0::step]
            gx0 = (x0 + c0) // step
            for k, v in enumerate(picks):
                gx = gx0 + k
                if gx >= w:
                    break
                if v != nodata:
                    out[gy * w + gx] = v / 10
    meta = {"x0": full.tie[3] + px * step / 2, "y0": full.tie[4] - px * step / 2, "step": px * step, "width": w,
            "height": h}
    return meta, out


class ClimateEu(Source):
    info = SourceInfo(
        id="climate_eu",
        title="Climate of Europe 2000-2019: monthly temperature (ERA5) and precipitation (CHELSA), OpenGeoHub EcoDataCube",
        publisher="OpenGeoHub Foundation, from Copernicus ERA5 (ECMWF) and CHELSA (WSL)",
        homepage="https://ecodatacube.eu/",
        license="CC BY 4.0 (data: Copernicus licence for ERA5, CC BY for CHELSA)",
        description="Monthly mean air temperature at 2 m (ERA5 reanalysis downscaled to 1 km with CHELSA) and monthly "
        "precipitation (CHELSA, 1 km), 2000 to 2019. Each month's file is read once: temperature sampled every 5 km, "
        "precipitation from its ~8 km overview; the decade means are kept (2000-2009 and 2010-2019; precipitation "
        "2010-2018, the series stopping in mid-2019). Each hex takes the mean of the grid points inside it.",
        used_for=["Temperature, warming, rainfall and rainfall change lenses"],
    )

    OUT = {"t_2000s": "t_2000s.bin", "t_2010s": "t_2010s.bin", "p_2000s": "p_2000s.bin", "p_2010s": "p_2010s.bin"}

    def fetch(self, force=False):
        meta_path = self.raw_dir / "grids.json"
        if meta_path.exists() and not force:
            return self._record()
        if self.offline:
            raise RuntimeError("climate_eu: not cached and --offline")
        self.raw_dir.mkdir(parents=True, exist_ok=True)
        grids, urls = {}, []
        for var, url_t, target, step in (("t", T_URL, None, T_STEP), ("p", P_URL, P_TARGET_M, 1)):
            for dec, (y0, y1) in DECADES.items():
                last = y1 if var == "t" else min(y1, P_LAST_FULL_YEAR)
                sums = cnts = meta = None
                for y in range(y0, last + 1):
                    for m in range(1, 13):
                        url = url_t.format(y=y, m=m, d=_days(y, m))
                        meta, vals = _sample(url, target, step)
                        urls.append(url)
                        if sums is None:
                            sums = array.array("f", [0.0]) * len(vals)
                            cnts = array.array("H", [0]) * len(vals)
                        for i, v in enumerate(vals):
                            if v == v:
                                sums[i] += v
                                cnts[i] += 1
                    print(f"    {var} {y} done", flush=True)
                months = (last - y0 + 1) * 12
                out = array.array("f", [float("nan")]) * len(sums)
                for i in range(len(sums)):
                    if cnts[i] >= months * 0.9:
                        mean = sums[i] / cnts[i]
                        out[i] = mean if var == "t" else mean * 12  # precipitation: mm per year
                name = self.OUT[f"{var}_{dec}"]
                tmp = self.raw_dir / f".{name}.tmp"
                tmp.write_bytes(out.tobytes())
                os.replace(tmp, self.raw_dir / name)
                grids[f"{var}_{dec}"] = {**meta, "file": name, "years": [y0, last]}
        meta_path.write_text(json.dumps({"grids": grids, "sources": urls[:2] + ["…"] + urls[-2:], "files": len(urls)}))
        self._record()

    def _record(self):
        """Cite the decade grids in the manifest: each is built from the monthly files of the EcoDataCube."""
        from ..core.fetch import record
        meta = json.loads((self.raw_dir / "grids.json").read_text())
        note = f"aggregated from {meta['files']} monthly cloud-optimised GeoTIFFs of the EcoDataCube"
        record(self.id, "grids.json", "https://s3.ecodatacube.eu/arco/", note)
        for key, g in meta["grids"].items():
            url = (T_URL if key.startswith("t") else P_URL).format(y=g["years"][0], m=1, d=31)
            record(self.id, g["file"], url, f"{note}; this one: {key}, {g['years'][0]}-{g['years'][1]}")

    def process(self):
        meta = json.loads((self.raw_dir / "grids.json").read_text())
        out = {}
        for key, g in meta["grids"].items():
            data = (self.raw_dir / g["file"]).read_bytes()
            INTERIM.mkdir(parents=True, exist_ok=True)
            (INTERIM / f"climate_{key}.bin").write_bytes(data)
            out[key] = {k: v for k, v in g.items() if k != "file"} | {"raster": f"climate_{key}.bin"}
        print(f"    {len(out)} decade grids from {meta['files']} monthly files")
        return {"vintage": "ERA5/CHELSA via EcoDataCube, 2000-2019", "_files": ["grids.json"] + [g["file"] for g in meta["grids"].values()],
                "grids": out}
