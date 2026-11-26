from ..core.europe import COUNTRIES, FROM_ISO2, INSETS
from ..core.geo import bbox_intersects, clip_ring_to_window, geojson_lines, geojson_rings, load_geojson
from ..core.source import Source, SourceInfo

# Pinned to a release tag so the content (and sha256) cannot change under the same URL.
TAG = "v5.1.2"
BASE = f"https://raw.githubusercontent.com/nvkelso/natural-earth-vector/{TAG}/geojson"
BBOX = (-40.0, 26.0, 66.0, 82.0)  # lon/lat window of the map rectangle


class NaturalEarth(Source):
    info = SourceInfo(
        id="natural_earth",
        title="Natural Earth 1:10m (lakes, rivers, neighbours of the outermost regions)",
        publisher="Natural Earth",
        homepage="https://www.naturalearthdata.com/",
        license="Domaine public",
        description="Lakes and rivers, with the European supplements, and the countries next to the outermost regions "
        "in their insets (Morocco, Suriname, Brazil). "
        f"Files pinned to natural-earth-vector {TAG}.",
        used_for=["Lakes", "Rivers", "Neighbouring countries in the insets"],
    )

    FILES = ["ne_10m_admin_0_countries", "ne_10m_lakes", "ne_10m_lakes_europe",
             "ne_10m_rivers_lake_centerlines", "ne_10m_rivers_europe"]

    def _path(self, name):
        return f"{TAG}/{name}.geojson"

    def fetch(self, force=False):
        for name in self.FILES:
            self.download(f"{BASE}/{name}.geojson", self._path(name), force=force)

    def _features(self, name):
        return load_geojson(self.raw_dir / self._path(name))

    def process(self):
        # The main map's other countries come from GISCO (gisco.foreign). Here only the neighbours of an outermost
        # region (Morocco by the Canaries, Suriname and Brazil around Guyane), cut to its inset window so each ring is
        # projected into the inset as a whole. The map's own countries come from the NUTS outlines.
        countries = []
        for f in self._features("ne_10m_admin_0_countries"):
            p = f["properties"]
            if FROM_ISO2.get(p.get("ISO_A2")) in COUNTRIES or p.get("ADM0_A3") in ("FRA", "PRT", "ESP"):
                continue
            all_rings = geojson_rings(f["geometry"])
            for d in INSETS:
                box = (d["lon"][0], d["lat"][0], d["lon"][1], d["lat"][1])
                cut = [c for c in (clip_ring_to_window(r, *box) for r in all_rings if bbox_intersects(r, box)) if len(c) >= 3]
                if cut:
                    countries.append({"name": f["properties"]["ADMIN"], "rings": cut, "inset": d["dep"]})
        lakes = []
        for name in ("ne_10m_lakes", "ne_10m_lakes_europe"):
            for f in self._features(name):
                rings = geojson_rings(f["geometry"])
                if rings and bbox_intersects(rings[0], BBOX):
                    lakes.append({"name": f["properties"].get("name"), "rings": rings})
        rivers = []
        for name in ("ne_10m_rivers_lake_centerlines", "ne_10m_rivers_europe"):
            for f in self._features(name):
                p = f["properties"]
                for line in geojson_lines(f["geometry"]):
                    if bbox_intersects(line, BBOX):
                        rivers.append({"name": p.get("name_en") or p.get("name"), "rank": p.get("scalerank", 10),
                                       "featurecla": p.get("featurecla"), "line": line})
        return {
            "vintage": f"Natural Earth {TAG} (1:10m)",
            "_files": [self._path(n) for n in self.FILES],
            "countries": countries,
            "lakes": lakes,
            "rivers": rivers,
        }


class NaturalEarthRoads(Source):
    """Natural Earth 1:10m roads and railroads (tile improvements). A separate source from the 1:50m set so the
    map's land and water (which the `world` builder reads) do not depend on these two ~45 MB files."""

    info = SourceInfo(
        id="natural_earth_roads",
        title="Natural Earth 1:10m roads and railroads",
        publisher="Natural Earth",
        homepage="https://www.naturalearthdata.com/",
        license="Public domain",
        description="Motorways, major roads and main railways, as 1:10m lines. They are drawn as map decoration "
        "(roads and rails from hex centre to hex centre), not as statistics: the lines come from older Natural Earth "
        f"releases and carry no traffic or operator. Files pinned to natural-earth-vector {TAG}.",
        used_for=["Motorways and major roads on the map", "Railways on the map"],
    )

    FILES = ["ne_10m_roads", "ne_10m_railroads"]

    def _path(self, name):
        return f"{TAG}/{name}.geojson"

    def fetch(self, force=False):
        for name in self.FILES:
            self.download(f"{BASE}/{name}.geojson", self._path(name), force=force)

    def process(self):
        roads, rail, types = [], [], {}
        for f in load_geojson(self.raw_dir / self._path("ne_10m_roads")):
            p = f["properties"]
            if p.get("featurecla") == "Ferry":
                continue
            types[p.get("type")] = types.get(p.get("type"), 0) + 1
            if p.get("type") == "Ferry Route":
                continue
            lines = [ln for ln in geojson_lines(f["geometry"]) if bbox_intersects(ln, BBOX)]
            if not lines:
                continue
            roads.append({
                "level": p.get("level") or None,
                "label2": p.get("label2") or None,        # national road number in Europe (A6, N193)
                "local": p.get("local") or p.get("label") or None,  # e.g. Hungary's M0 when label2 is empty
                "type": p.get("type") or None,            # Major Highway, Secondary Highway, Beltway, ...
                "name": (str(p.get("name")).strip() or None) if p.get("name") not in (None, "") else None,
                "expressway": 1 if p.get("expressway") == 1 else 0,
                "scalerank": p.get("scalerank"),
                "lines": [[(round(x, 4), round(y, 4)) for x, y in ln] for ln in lines],
            })
        for f in load_geojson(self.raw_dir / self._path("ne_10m_railroads")):
            p = f["properties"]
            # No country field: the bbox keeps neighbouring countries' lines too; the builder clips to French land.
            lines = [ln for ln in geojson_lines(f["geometry"]) if bbox_intersects(ln, BBOX)]
            if lines:
                rail.append({"scalerank": p.get("scalerank"), "category": p.get("category"),
                             "lines": [[(round(x, 4), round(y, 4)) for x, y in ln] for ln in lines]})
        print(f"    {len(roads)} road features ({types}), {len(rail)} rail features in the map window")
        return {
            "vintage": f"Natural Earth {TAG} (1:10m)",
            "_files": [self._path(n) for n in self.FILES],
            "roads": roads,
            "rail": rail,
        }
