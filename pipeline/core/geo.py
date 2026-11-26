"""Small, dependency-free geometry helpers.

Everything on the map lives in "map units": a Lambert azimuthal equal-area projection
of Europe (the spherical form of EPSG:3035, centred on 52° N 10° E), multiplied by SCALE
and shifted so the top-left of the map is (0, 0) and y points *down* (like screen
coordinates). Both the hex grid and the browser use this space. The art and the camera
were tuned (in usaciv) for 25-unit hexes, so one map unit is 1 / SCALE real kilometres
(world.json `km_per_unit`): hexes are 10 km in radius, about 17 km across.
"""

from __future__ import annotations

import json
import math
import xml.etree.ElementTree as ET
from collections import defaultdict
from dataclasses import dataclass
from typing import IO, Iterable, Iterator

R_EARTH_KM = 6371.0088


SCALE = 2.5  # map units per real km


class Laea:
    """Lambert azimuthal equal-area on the sphere, centred like EPSG:3035 (ETRS89-LAEA Europe). Output in km, y up."""

    def __init__(self, lon0=10.0, lat0=52.0):
        self.lon0, self.lat0 = math.radians(lon0), math.radians(lat0)
        self.sin0, self.cos0 = math.sin(self.lat0), math.cos(self.lat0)

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        lam, phi = math.radians(lon) - self.lon0, math.radians(lat)
        sp, cp, cl = math.sin(phi), math.cos(phi), math.cos(lam)
        k = math.sqrt(2 / max(1e-12, 1 + self.sin0 * sp + self.cos0 * cp * cl))
        return R_EARTH_KM * k * cp * math.sin(lam), R_EARTH_KM * k * (self.cos0 * sp - self.sin0 * cp * cl)

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        """km → (lon, lat)."""
        rho = math.hypot(x, y)
        if rho < 1e-9:
            return math.degrees(self.lon0), math.degrees(self.lat0)
        c = 2 * math.asin(min(1.0, rho / (2 * R_EARTH_KM)))
        sc, cc = math.sin(c), math.cos(c)
        lat = math.asin(max(-1.0, min(1.0, cc * self.sin0 + y * sc * self.cos0 / rho)))
        lon = self.lon0 + math.atan2(x * sc, rho * self.cos0 * cc - y * self.sin0 * sc)
        return math.degrees(lon), math.degrees(lat)

class Albers:
    """Albers equal-area conic, parameters for metropolitan France (Corsica included)."""

    def __init__(self, lat1=43.0, lat2=49.5, lat0=46.5, lon0=2.5):
        p1, p2, p0 = map(math.radians, (lat1, lat2, lat0))
        self.lon0 = math.radians(lon0)
        self.n = (math.sin(p1) + math.sin(p2)) / 2
        self.c = math.cos(p1) ** 2 + 2 * self.n * math.sin(p1)
        self.rho0 = R_EARTH_KM * math.sqrt(self.c - 2 * self.n * math.sin(p0)) / self.n

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        rho = R_EARTH_KM * math.sqrt(self.c - 2 * self.n * math.sin(math.radians(lat))) / self.n
        theta = self.n * (math.radians(lon) - self.lon0)
        return rho * math.sin(theta), self.rho0 - rho * math.cos(theta)

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        """Albers km → (lon, lat)."""
        dy = self.rho0 - y
        rho = math.hypot(x, dy)
        theta = math.atan2(x, dy)
        s = (self.c - (rho * self.n / R_EARTH_KM) ** 2) / (2 * self.n)
        return math.degrees(self.lon0 + theta / self.n), math.degrees(math.asin(max(-1.0, min(1.0, s))))


class Laea3035:
    """EPSG:3035 (ETRS89-LAEA Europe, GRS80 ellipsoid; Snyder 1987, eqs. 24-1..24-15), (lon, lat) → metres with the
    false origin. Used to look up rasters published in that grid (CORINE)."""

    def __init__(self, lat0=52.0, lon0=10.0, x0=4321000.0, y0=3210000.0, a=6378137.0, inv_f=298.257222101):
        f = 1 / inv_f
        self.a, self.e2 = a, f * (2 - f)
        self.e = math.sqrt(self.e2)
        self.lon0, self.x0, self.y0 = math.radians(lon0), x0, y0
        p1 = math.radians(lat0)
        self.qp = self._q(math.pi / 2)
        self.rq = a * math.sqrt(self.qp / 2)
        b1 = math.asin(self._q(p1) / self.qp)
        self.sb1, self.cb1 = math.sin(b1), math.cos(b1)
        m1 = math.cos(p1) / math.sqrt(1 - self.e2 * math.sin(p1) ** 2)
        self.d = a * m1 / (self.rq * self.cb1)

    def _q(self, phi: float) -> float:
        s, e = math.sin(phi), self.e
        return (1 - self.e2) * (s / (1 - self.e2 * s * s) - math.log((1 - e * s) / (1 + e * s)) / (2 * e))

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        beta = math.asin(max(-1.0, min(1.0, self._q(math.radians(lat)) / self.qp)))
        sb, cb = math.sin(beta), math.cos(beta)
        dl = math.radians(lon) - self.lon0
        b = self.rq * math.sqrt(2 / (1 + self.sb1 * sb + self.cb1 * cb * math.cos(dl)))
        return (self.x0 + b * self.d * cb * math.sin(dl),
                self.y0 + (b / self.d) * (self.cb1 * sb - self.sb1 * cb * math.cos(dl)))


class AlbersEllipsoid:
    """Ellipsoidal Albers equal-area (Snyder 1987, eqs. 14-3..14-6), output in metres.

    Defaults are EPSG:5070 (NAD83 / Conus Albers): GRS80, lat0 23, lon0 -96,
    standard parallels 29.5 and 45.5. Used to look up rasters such as NLCD.
    """

    def __init__(self, lat1=29.5, lat2=45.5, lat0=23.0, lon0=-96.0, a=6378137.0, inv_f=298.257222101):
        f = 1 / inv_f
        self.a = a
        self.e2 = f * (2 - f)
        self.e = math.sqrt(self.e2)
        self.lon0 = math.radians(lon0)
        p1, p2, p0 = map(math.radians, (lat1, lat2, lat0))
        m1, m2 = self._m(p1), self._m(p2)
        q1, q2, q0 = self._q(p1), self._q(p2), self._q(p0)
        self.n = (m1 * m1 - m2 * m2) / (q2 - q1)
        self.c = m1 * m1 + self.n * q1
        self.rho0 = a * math.sqrt(self.c - self.n * q0) / self.n

    def _m(self, phi: float) -> float:
        s = math.sin(phi)
        return math.cos(phi) / math.sqrt(1 - self.e2 * s * s)

    def _q(self, phi: float) -> float:
        s, e = math.sin(phi), self.e
        return (1 - self.e2) * (s / (1 - self.e2 * s * s) - math.log((1 - e * s) / (1 + e * s)) / (2 * e))

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        rho = self.a * math.sqrt(self.c - self.n * self._q(math.radians(lat))) / self.n
        theta = self.n * (math.radians(lon) - self.lon0)
        return rho * math.sin(theta), self.rho0 - rho * math.cos(theta)


# The outermost regions (core/europe.py INSETS) are drawn in insets laid on open sea. Each inset is a lon/lat window
# projected equirectangularly at k times the main scale, its frame's top-left corner at (x, y) map units, the content
# `pad` units inside. A point inside a window is projected into its inset, everything else with the main projection;
# inverse() does the reverse for points inside a frame.
from .europe import INSETS  # noqa: E402

INSET_PAD = 30.0
KM_PER_DEG_LAT = 110.57
KM_PER_DEG_LON_EQ = 111.32


class Inset:
    def __init__(self, d: dict, scale: float = SCALE):
        self.d = d
        self.lon0, self.lon1 = d["lon"]
        self.lat0, self.lat1 = d["lat"]
        latc = math.radians((self.lat0 + self.lat1) / 2)
        self.kx = KM_PER_DEG_LON_EQ * math.cos(latc) * scale * d["k"]  # map units per degree of longitude
        self.ky = KM_PER_DEG_LAT * scale * d["k"]
        self.ox, self.oy = d["x"] + INSET_PAD, d["y"] + INSET_PAD  # content origin (the window's NW corner)
        self.w = (self.lon1 - self.lon0) * self.kx + 2 * INSET_PAD
        self.h = (self.lat1 - self.lat0) * self.ky + 2 * INSET_PAD
        self.frame = (d["x"], d["y"], d["x"] + self.w, d["y"] + self.h)

    def holds(self, lon: float, lat: float) -> bool:
        return self.lon0 <= lon <= self.lon1 and self.lat0 <= lat <= self.lat1

    def in_frame(self, x: float, y: float) -> bool:
        x0, y0, x1, y1 = self.frame
        return x0 <= x <= x1 and y0 <= y <= y1

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        return self.ox + (lon - self.lon0) * self.kx, self.oy + (self.lat1 - lat) * self.ky

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        return self.lon0 + (x - self.ox) / self.kx, self.lat1 - (y - self.oy) / self.ky

    def to_dict(self) -> dict:
        x0, y0, x1, y1 = self.frame
        return {**self.d, "frame": [round(x0, 1), round(y0, 1), round(x1, 1), round(y1, 1)],
                "km_per_unit": round(1 / (SCALE * self.d["k"]), 6)}


def clip_ring_to_window(ring: list, lon0: float, lat0: float, lon1: float, lat1: float) -> list:
    """Sutherland–Hodgman clip of a lon/lat ring to a window (a ring crossing an inset's edge would otherwise mix two
    projections)."""
    def clip(pts, inside, cut):
        out = []
        for i, cur in enumerate(pts):
            prev = pts[i - 1]
            if inside(cur):
                if not inside(prev):
                    out.append(cut(prev, cur))
                out.append(cur)
            elif inside(prev):
                out.append(cut(prev, cur))
        return out
    def at_x(a, b, x):
        t = (x - a[0]) / (b[0] - a[0])
        return (x, a[1] + t * (b[1] - a[1]))
    def at_y(a, b, y):
        t = (y - a[1]) / (b[1] - a[1])
        return (a[0] + t * (b[0] - a[0]), y)
    pts = [tuple(p) for p in ring]
    for inside, cut in ((lambda p: p[0] >= lon0, lambda a, b: at_x(a, b, lon0)),
                        (lambda p: p[0] <= lon1, lambda a, b: at_x(a, b, lon1)),
                        (lambda p: p[1] >= lat0, lambda a, b: at_y(a, b, lat0)),
                        (lambda p: p[1] <= lat1, lambda a, b: at_y(a, b, lat1))):
        if not pts:
            break
        pts = clip(pts, inside, cut)
    return pts


@dataclass
class MapProjection:
    """lon/lat → map units (origin top-left, y down). min_x/max_y are LAEA km; margin is in map units.
    Points in an inset window go to its inset (INSETS)."""

    min_x: float
    max_y: float
    margin: float
    scale: float = SCALE
    insets: list | None = None

    def __post_init__(self):
        self._albers = Laea()  # the attribute keeps its usaciv name
        self._insets = [Inset(d, self.scale) for d in (self.insets or [])]  # world.py passes INSETS

    def inset_of(self, lon: float, lat: float):
        for ins in self._insets:
            if ins.holds(lon, lat):
                return ins
        return None

    def __call__(self, lon: float, lat: float) -> tuple[float, float]:
        if lon > 40 or lon < -40 or (lon < -12.5 and lat < 40.5):  # the inset windows only (a cheap test first)
            ins = self.inset_of(lon, lat)
            if ins is not None:
                return ins(lon, lat)
        x, y = self._albers(lon, lat)
        return (x - self.min_x) * self.scale + self.margin, (self.max_y - y) * self.scale + self.margin

    def inverse(self, x: float, y: float) -> tuple[float, float]:
        """map units → (lon, lat)."""
        for ins in self._insets:
            if ins.in_frame(x, y):
                return ins.inverse(x, y)
        return self._albers.inverse((x - self.margin) / self.scale + self.min_x, self.max_y - (y - self.margin) / self.scale)

    def frame_of(self, x: float, y: float):
        """The inset whose frame holds map point (x, y), or None (the main map)."""
        for ins in self._insets:
            if ins.in_frame(x, y):
                return ins
        return None

    def to_dict(self) -> dict:
        return {"min_x": self.min_x, "max_y": self.max_y, "margin": self.margin, "scale": self.scale,
                "insets": [ins.d for ins in self._insets]}

    def insets_dict(self) -> list[dict]:
        return [ins.to_dict() for ins in self._insets]


def ring_contains(ring: list[tuple[float, float]], x: float, y: float) -> bool:
    inside = False
    j = len(ring) - 1
    for i in range(len(ring)):
        xi, yi = ring[i]
        xj, yj = ring[j]
        if (yi > y) != (yj > y) and x < (xj - xi) * (y - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


class Shape:
    """A (multi)polygon as a bag of rings; even-odd rule handles holes."""

    def __init__(self, rings: Iterable[list[tuple[float, float]]]):
        self.rings = [r for r in rings if len(r) >= 3]
        xs = [p[0] for r in self.rings for p in r] or [0]
        ys = [p[1] for r in self.rings for p in r] or [0]
        self.bbox = (min(xs), min(ys), max(xs), max(ys))

    def contains(self, x: float, y: float) -> bool:
        x0, y0, x1, y1 = self.bbox
        if x < x0 or x > x1 or y < y0 or y > y1:
            return False
        inside = False
        for r in self.rings:
            if ring_contains(r, x, y):
                inside = not inside
        return inside


class ShapeIndex:
    """Bucket shapes by coarse grid square so point lookups only test a few shapes."""

    def __init__(self, shapes: list[Shape], cell_km: float = 100.0):
        self.shapes = shapes
        self.cell = cell_km
        self.buckets: dict[tuple[int, int], list[int]] = defaultdict(list)
        for k, s in enumerate(shapes):
            x0, y0, x1, y1 = s.bbox
            for gx in range(int(x0 // cell_km), int(x1 // cell_km) + 1):
                for gy in range(int(y0 // cell_km), int(y1 // cell_km) + 1):
                    self.buckets[(gx, gy)].append(k)

    def locate(self, x: float, y: float) -> int:
        for k in self.buckets.get((int(x // self.cell), int(y // self.cell)), ()):
            if self.shapes[k].contains(x, y):
                return k
        return -1


# --- file formats -----------------------------------------------------------

KML_NS = "{http://www.opengis.net/kml/2.2}"


def read_kml_placemarks(fileobj: IO[bytes]) -> Iterator[tuple[dict, list[list[tuple[float, float]]]]]:
    """Yield (properties, rings) for each Placemark in a Census cartographic KML."""
    for _, el in ET.iterparse(fileobj):
        if el.tag != KML_NS + "Placemark":
            continue
        props = {sd.get("name"): (sd.text or "") for sd in el.iter(KML_NS + "SimpleData")}
        rings = []
        for coords in el.iter(KML_NS + "coordinates"):
            pts = []
            for tok in (coords.text or "").split():
                lon, lat = tok.split(",")[:2]
                pts.append((round(float(lon), 5), round(float(lat), 5)))
            rings.append(pts)
        yield props, rings
        el.clear()


def geojson_rings(geom: dict) -> list[list[tuple[float, float]]]:
    t, c = geom["type"], geom["coordinates"]
    polys = [c] if t == "Polygon" else c if t == "MultiPolygon" else []
    return [[(round(x, 5), round(y, 5)) for x, y, *_ in ring] for poly in polys for ring in poly]


def geojson_lines(geom: dict) -> list[list[tuple[float, float]]]:
    t, c = geom["type"], geom["coordinates"]
    lines = [c] if t == "LineString" else c if t == "MultiLineString" else []
    return [[(round(x, 5), round(y, 5)) for x, y, *_ in line] for line in lines]


def load_geojson(path) -> list[dict]:
    with open(path, encoding="utf-8") as f:
        return json.load(f)["features"]


def bbox_intersects(points: Iterable[tuple[float, float]], bbox: tuple[float, float, float, float]) -> bool:
    x0, y0, x1, y1 = bbox
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in points)
