"""Eurostat GISCO geography: NUTS 2024 regions, the countries around them, Urban Audit 2021 functional urban areas and
cities, and the local administrative units (LAU 2021, the communes) with their population."""

from __future__ import annotations

import json

from ..core.europe import COUNTRIES, FROM_ISO2, mapped
from ..core.geo import geojson_rings
from ..core.names import latin
from ..core.source import Source, SourceInfo

BASE = "https://gisco-services.ec.europa.eu/distribution/v2"
FILES = {
    "nuts": (f"{BASE}/nuts/geojson/NUTS_RG_03M_2024_4326.geojson", "NUTS_RG_03M_2024_4326.geojson"),
    "countries": (f"{BASE}/countries/geojson/CNTR_RG_03M_2024_4326.geojson", "CNTR_RG_03M_2024_4326.geojson"),
    "fua": (f"{BASE}/urau/geojson/URAU_RG_100K_2021_4326_FUA.geojson", "URAU_RG_100K_2021_4326_FUA.geojson"),
    "cities": (f"{BASE}/urau/geojson/URAU_LB_2021_4326_CITIES.geojson", "URAU_LB_2021_4326_CITIES.geojson"),
    "lau": (f"{BASE}/lau/geojson/LAU_RG_01M_2021_4326.geojson", "LAU_RG_01M_2021_4326.geojson"),
}
BBOX = (-45.0, 24.0, 50.0, 82.0)  # lon/lat window of the map and its insets' neighbourhood (Morocco, Atlantic)


GERMAN_KINDS = ((", Kreisfreie Stadt", " (city)"), (", Stadtkreis", " (city)"), (", Landkreis", " (district)"),
                (", Kreis", " (district)"))


def region_name(name: str) -> str:
    """'Heilbronn, Stadtkreis' → 'Heilbronn (city)', 'Heilbronn, Landkreis' → 'Heilbronn (district)': German NUTS 3
    names keep the city/district distinction in a form an English reader parses."""
    name = name.strip()
    for tail, kind in GERMAN_KINDS:
        if name.endswith(tail):
            return name[: -len(tail)] + kind
    return name


def thin(ring, step=0.01):
    """Drop vertices closer than `step` degrees (about 1 km) to the last kept one."""
    out = [ring[0]]
    for p in ring[1:-1]:
        if abs(p[0] - out[-1][0]) + abs(p[1] - out[-1][1]) >= step:
            out.append(p)
    out.append(ring[-1])
    return out if len(out) >= 4 else ring


def centroid(rings):
    """Area-weighted centroid of the largest ring (a commune's main part), else its first vertex."""
    best, best_a, best_c = None, 0.0, None
    for r in rings:
        a = cx = cy = 0.0
        for (x0, y0), (x1, y1) in zip(r, r[1:] + r[:1]):
            f = x0 * y1 - x1 * y0
            a += f
            cx += (x0 + x1) * f
            cy += (y0 + y1) * f
        if abs(a) > best_a and a:
            best, best_a, best_c = r, abs(a), (cx / (3 * a), cy / (3 * a))
    if best_c is None:
        return rings[0][0] if rings and rings[0] else (None, None)
    return round(best_c[0], 5), round(best_c[1], 5)


def in_bbox(ring):
    x0, y0, x1, y1 = BBOX
    return any(x0 <= x <= x1 and y0 <= y <= y1 for x, y in ring)


class Gisco(Source):
    info = SourceInfo(
        id="gisco",
        title="NUTS 2024 regions, countries, urban areas and local units (Eurostat GISCO)",
        publisher="Eurostat GISCO (European Commission)",
        homepage="https://ec.europa.eu/eurostat/web/gisco/geodata",
        license="Free reuse with attribution: © EuroGeographics for the administrative boundaries",
        description="1:3 million outlines of the NUTS 2024 regions (the countries and their NUTS 1, 2 and 3 regions), "
        "of the neighbouring countries (drawn in the haze), of the Urban Audit 2021 functional urban areas (a core "
        "city and its commuting zone), the core cities, and the local administrative units (LAU 2021: communes, "
        "Gemeinden, comuni…) with their 2021 census population.",
        used_for=["Countries and regions on the map", "Cities (functional urban areas)", "Place search",
                  "Neighbouring countries"],
    )

    def fetch(self, force=False):
        for url, name in FILES.values():
            self.download(url, name, force=force)

    def _features(self, key):
        with open(self.raw_dir / FILES[key][1], encoding="utf-8") as f:
            return json.load(f)["features"]

    def process(self):
        nuts = []
        feats = [f for f in self._features("nuts") if mapped(f["properties"]["NUTS_ID"])]
        # The map's "counties" are the NUTS 3 regions; a country without them (Bosnia and Herzegovina) uses its
        # deepest level.
        deepest: dict = {}
        for f in feats:
            p = f["properties"]
            deepest[p["CNTR_CODE"]] = max(deepest.get(p["CNTR_CODE"], 0), p["LEVL_CODE"])
        for f in feats:
            p = f["properties"]
            code = p["NUTS_ID"]
            row = {"code": code, "level": p["LEVL_CODE"], "country": p["CNTR_CODE"], "name": region_name(p["NAME_LATN"]),
                   "local": p.get("NUTS_NAME"), "mount": p.get("MOUNT_TYPE"), "urban": p.get("URBN_TYPE"),
                   "coast": p.get("COAST_TYPE")}
            if p["LEVL_CODE"] == deepest[p["CNTR_CODE"]]:
                row["county"] = True
                row["rings"] = [thin(r, 0.004) for r in geojson_rings(f["geometry"])]
            nuts.append(row)

        foreign = []
        for f in self._features("countries"):
            p = f["properties"]
            iso = p.get("CNTR_ID")
            if FROM_ISO2.get(iso) in COUNTRIES:
                continue
            rings = [thin(r, 0.004) for r in geojson_rings(f["geometry"]) if in_bbox(r)]
            if rings:
                foreign.append({"iso": iso, "name": p.get("NAME_FREN") or p.get("NAME_ENGL"), "rings": rings})

        fuas = []
        for f in self._features("fua"):
            p = f["properties"]
            if p["CNTR_CODE"] not in COUNTRIES:
                continue
            name = p["URAU_NAME"].removeprefix("FUA ").strip()
            fuas.append({"code": p["URAU_CODE"], "name": name, "country": p["CNTR_CODE"], "nuts3": p.get("NUTS3_2021"),
                         "rings": [thin(r) for r in geojson_rings(f["geometry"])]})

        cities = []
        for f in self._features("cities"):
            p = f["properties"]
            lon, lat = f["geometry"]["coordinates"][:2]
            cities.append({"code": p["URAU_CODE"], "name": p["URAU_NAME"], "fua": p.get("FUA_CODE"),
                           "country": p["CNTR_CODE"], "capital": bool(p.get("CITY_CPTL")), "nuts3": p.get("NUTS3_2021"),
                           "lon": round(lon, 5), "lat": round(lat, 5)})

        lau = {"columns": ["id", "country", "name", "pop", "area", "lon", "lat"], "rows": []}
        for f in self._features("lau"):
            p = f["properties"]
            if p["CNTR_CODE"] not in COUNTRIES or not f.get("geometry"):
                continue
            lon, lat = centroid(geojson_rings(f["geometry"]))
            if lon is None:
                continue
            area = p.get("AREA_KM2")
            lau["rows"].append([p["GISCO_ID"], p["CNTR_CODE"], latin(p["LAU_NAME"]), p.get("POP_2021"),
                                round(area, 2) if area is not None else None, lon, lat])
        print(f"    {len(nuts)} NUTS regions ({sum(1 for n in nuts if n['level'] == 3)} NUTS 3), {len(foreign)} other "
              f"countries, {len(fuas)} FUAs, {len(cities)} cities, {len(lau['rows'])} LAUs")
        return {
            "vintage": "GISCO: NUTS 2024, countries 2024, Urban Audit 2021, LAU 2021",
            "_files": [name for _, name in FILES.values()],
            "nuts": nuts,
            "foreign": foreign,
            "fuas": fuas,
            "cities": cities,
            "lau": lau,
        }
