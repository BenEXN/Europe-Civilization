"""Climate of metropolitan France since 1961: Météo-France's Safran-Isba (SIM2) monthly grid, ~8 km.

One CSV per year (every grid point × 12 months): mean temperature T (°C) and total precipitation PRETOTM (mm). For
each point: the 1991-2020 normals, and the change between 1961-1990 and the last thirty complete years. The grid's
shapefile gives each point's latitude and longitude. Overseas départements are not in this grid.
"""

from __future__ import annotations

import csv
import gzip
import io
import struct

from ..core.source import Source, SourceInfo

FIRST, LAST = 1961, 2025  # LAST = the last complete year
BASE = "https://meteofrance.s3.sbg.io.cloud.ovh.net/data/REF_CC/SIM_MENS/MENS_SIM2_{y}.csv.gz"
DATASET = "https://www.data.gouv.fr/api/1/datasets/65e040c50a5c6872ebebc711/"
PERIODS = {"old": (1961, 1990), "normal": (1991, 2020), "recent": (LAST - 29, LAST)}


def read_dbf(data: bytes) -> list[dict]:
    """A dBASE III table (the grid shapefile's attributes)."""
    n, hlen, rlen = struct.unpack("<IHH", data[4:12])
    fields = []
    for i in range(32, hlen - 1, 32):
        fields.append((data[i:i + 11].split(b"\0")[0].decode(), data[i + 16]))
    out = []
    for k in range(n):
        rec = data[hlen + k * rlen + 1: hlen + (k + 1) * rlen]
        row, pos = {}, 0
        for name, ln in fields:
            row[name] = rec[pos:pos + ln].decode("latin-1").strip()
            pos += ln
        out.append(row)
    return out


class MeteoSim(Source):
    info = SourceInfo(
        id="meteo_sim",
        title=f"Climat {FIRST}-{LAST} : réanalyse Safran-Isba (SIM2) mensuelle de Météo-France",
        publisher="Météo-France",
        homepage="https://www.data.gouv.fr/datasets/donnees-changement-climatique-sim-mensuelle",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Température moyenne et précipitations de chaque mois depuis 1961 sur une grille d'environ 8 km "
        "couvrant la métropole (analyse Safran, modèle Isba). Pour chaque point : les normales 1991-2020, et l'écart "
        f"entre les années {PERIODS['recent'][0]}-{LAST} et 1961-1990. Chaque hexagone prend la moyenne des points "
        "qu'il contient. L'outre-mer n'est pas couvert par cette grille.",
        used_for=["Lentilles Température, Réchauffement, Pluies et Évolution des pluies"],
    )

    def fetch(self, force=False):
        import json
        import urllib.request

        from ..core.fetch import USER_AGENT
        for y in range(FIRST, LAST + 1):
            self.download(BASE.format(y=y), f"MENS_SIM2_{y}.csv.gz", force=force, expect_binary=True)
        if force or not (self.raw_dir / "grid.dbf").exists():
            req = urllib.request.Request(DATASET, headers={"User-Agent": USER_AGENT})
            meta = json.loads(urllib.request.urlopen(req, timeout=60).read())
            url = next(r["url"] for r in meta["resources"] if r["title"].lower().endswith(".dbf"))
            self.download(url, "grid.dbf", force=True, expect_binary=True)

    def process(self):
        grid = {}
        for r in read_dbf((self.raw_dir / "grid.dbf").read_bytes()):
            grid[(int(r["lambx"]), int(r["lamby"]))] = (round(float(r["lat_dg"]), 4), round(float(r["lon_dg"]), 4))
        # per point and year: sum of monthly T, months counted, precipitation total
        acc: dict = {}
        for y in range(FIRST, LAST + 1):
            with gzip.open(self.raw_dir / f"MENS_SIM2_{y}.csv.gz", "rt", encoding="utf-8") as f:
                rows = csv.reader(f, delimiter=";")
                head = next(rows)
                ix, iy, it, ip = head.index("LAMBX"), head.index("LAMBY"), head.index("T"), head.index("PRETOTM")
                for r in rows:
                    if not r:
                        continue
                    key = (int(r[ix]), int(r[iy]))
                    if key not in grid:
                        continue
                    a = acc.setdefault(key, {})
                    yr = a.setdefault(y, [0.0, 0, 0.0])
                    yr[0] += float(r[it])
                    yr[1] += 1
                    yr[2] += float(r[ip])
        def mean(a, period, k):
            vals = [(v[0] / v[1] if k == 0 else v[2]) for y, v in a.items() if period[0] <= y <= period[1] and v[1] == 12]
            return sum(vals) / len(vals) if len(vals) >= (period[1] - period[0] + 1) * 0.9 else None
        points = []
        national = {y: [0.0, 0] for y in range(FIRST, LAST + 1)}
        for key, a in acc.items():
            lat, lon = grid[key]
            t = {p: mean(a, rng, 0) for p, rng in PERIODS.items()}
            pr = {p: mean(a, rng, 2) for p, rng in PERIODS.items()}
            if None in t.values() or None in pr.values():
                continue
            points.append([lat, lon, round(t["normal"], 2), round(t["recent"] - t["old"], 2), round(pr["normal"], 1),
                           round(pr["recent"] / pr["old"] - 1, 4) if pr["old"] else None])
            for y, v in a.items():
                if v[1] == 12:
                    national[y][0] += v[0] / 12
                    national[y][1] += 1
        series = {y: round(s / n, 2) for y, (s, n) in national.items() if n}
        warm = sum(p[3] for p in points) / len(points)
        print(f"    {len(points)} grid points; mean warming {warm:+.2f} °C ({PERIODS['recent'][0]}-{LAST} vs 1961-1990)")
        return {
            "vintage": f"Météo-France SIM2, {FIRST}-{LAST}",
            "_files": [f"MENS_SIM2_{y}.csv.gz" for y in range(FIRST, LAST + 1)] + ["grid.dbf"],
            "periods": PERIODS,
            "columns": ["lat", "lon", "t_normal", "warming", "rain_normal", "rain_change"],
            "points": points,
            "national_t": series,
        }
