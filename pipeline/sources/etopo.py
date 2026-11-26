import csv

from ..core.europe import INSETS
from ..core.source import Source, SourceInfo

# ETOPO1 (1 arc-minute, ~1.9 km) via NOAA ERDDAP. The main window covers the whole map rectangle (the LAEA rectangle
# spans 37° W to 65° E at its northern corners), every second point (~3.7 km, about thirty per hex), in six slices so
# each request stays small. Plus one window per inset (core/europe.py INSETS), a little wider, every point.
LAT = (30.0, 74.0)
SLICES = [(-37.0, -20.0), (-20.0, -3.0), (-3.0, 14.0), (14.0, 31.0), (31.0, 48.0), (48.0, 66.0)]
WINDOWS = [(LAT, lon, 2) for lon in SLICES] + [
    ((round(d["lat"][0] - 0.2, 2), round(d["lat"][1] + 0.2, 2)), (round(d["lon"][0] - 0.2, 2), round(d["lon"][1] + 0.2, 2)), 1)
    for d in INSETS]


def _url(lat, lon, stride):
    return ("https://coastwatch.pfeg.noaa.gov/erddap/griddap/etopo180.csv"
            f"?altitude%5B({lat[0]}):{stride}:({lat[1]})%5D%5B({lon[0]}):{stride}:({lon[1]})%5D")


def _file(lat, lon, stride):
    return f"etopo_lat{lat[0]}_{lat[1]}_lon{lon[0]}_{lon[1]}_stride{stride}.csv"


class Etopo(Source):
    info = SourceInfo(
        id="etopo",
        title="ETOPO1 global relief model",
        publisher="NOAA National Centers for Environmental Information (via ERDDAP)",
        homepage="https://www.ncei.noaa.gov/products/etopo-global-relief-model",
        license="Public domain (U.S. Government work)",
        description="Land elevation and sea depth, one point every two arc-minutes (~3.7 km; every arc-minute in the "
        "insets). Each hex's relief (flat, hills, mountains, peaks) comes from the mean and the spread (standard "
        "deviation) of the land points inside it.",
        used_for=["Relief (hills, mountains)", "Hill shading", "Sea depth"],
    )

    def fetch(self, force=False):
        for la, lo, st in WINDOWS:
            self.download(_url(la, lo, st), _file(la, lo, st), force=force)

    def process(self):
        lat, lon, alt = [], [], []
        for la, lo, st in WINDOWS:
            with open(self.raw_dir / _file(la, lo, st), newline="") as f:
                rows = csv.reader(f)
                next(rows), next(rows)  # header + units
                for a, o, al in rows:
                    if al == "NaN":
                        continue  # (neighbouring slices share their edge meridian: a few duplicate samples, harmless)
                    lat.append(round(float(a), 4))
                    lon.append(round(float(o), 4))
                    alt.append(int(float(al)))
        return {
            "vintage": "ETOPO1, 1 arc-minute (every second point outside the insets)",
            "_files": [_file(la, lo, st) for la, lo, st in WINDOWS],
            "lat": lat,
            "lon": lon,
            "alt": alt,
        }
