import gzip
import json

from ..core.geo import geojson_rings
from ..core.source import Source, SourceInfo

YEAR = 2026
BASE = f"https://etalab-datasets.geo.data.gouv.fr/contours-administratifs/{YEAR}/geojson"
FILES = {
    "regions": "regions-100m",
    "departements": "departements-100m",
    "epci": "epci-100m",
    "communes": "communes-100m",
    "mairies": "mairies",
}


OVERSEAS = {"971", "972", "973", "974", "976"}  # the five overseas départements, drawn in insets (core/geo.py INSETS)


def is_metro(code: str) -> bool:
    """Metropolitan France (with Corsica): département codes 01-95, 2A, 2B; not 971-989."""
    return not code.startswith("97") and not code.startswith("98")


def is_mapped(code: str) -> bool:
    """On the map: metropolitan France and the five overseas départements (not the collectivités, 975, 977-989)."""
    return is_metro(code) or code in OVERSEAS


class FrBoundaries(Source):
    info = SourceInfo(
        id="fr_boundaries",
        title=f"Contours administratifs {YEAR} (régions, départements, EPCI, communes)",
        publisher="Etalab, d'après IGN Admin Express",
        homepage="https://etalab-datasets.geo.data.gouv.fr/contours-administratifs/",
        license="Licence Ouverte 2.0 (Etalab)",
        description=f"Contours des régions, départements, intercommunalités (EPCI) et communes au 1er janvier {YEAR}, "
        "simplifiés à 100 m. Ils décident à quel département, quelle intercommunalité et quelles communes appartient "
        "chaque hexagone.",
        used_for=["Carte : terre et mer", "Frontières des départements", "Intercommunalités et communes des lentilles",
                  "Position des villes (mairie de la commune-centre)"],
    )

    def _path(self, name):
        return f"{YEAR}/{FILES[name]}.geojson.gz"

    def fetch(self, force=False):
        for name in FILES:
            self.download(f"{BASE}/{FILES[name]}.geojson.gz", self._path(name), force=force, expect_binary=True)

    def _features(self, name):
        with gzip.open(self.raw_dir / self._path(name), "rt", encoding="utf-8") as f:
            return json.load(f)["features"]

    def process(self):
        communes = []
        epci_of_metro = set()
        for f in self._features("communes"):
            p = f["properties"]
            if not is_mapped(p["departement"]):
                continue
            communes.append({
                "code": p["code"], "name": p["nom"], "dep": p["departement"], "region": p["region"],
                "epci": p.get("epci") or None, "rings": geojson_rings(f["geometry"]),
            })
            if p.get("epci"):
                epci_of_metro.add(p["epci"])
        deps = [
            {"code": f["properties"]["code"], "name": f["properties"]["nom"], "region": f["properties"]["region"],
             "rings": geojson_rings(f["geometry"])}
            for f in self._features("departements") if is_mapped(f["properties"]["code"])
        ]
        dep_regions = {d["region"] for d in deps}
        regions = [
            {"code": f["properties"]["code"], "name": f["properties"]["nom"], "rings": geojson_rings(f["geometry"])}
            for f in self._features("regions") if f["properties"]["code"] in dep_regions
        ]
        epci = [
            {"code": f["properties"]["code"], "name": f["properties"]["nom"], "rings": geojson_rings(f["geometry"])}
            for f in self._features("epci") if f["properties"]["code"] in epci_of_metro
        ]
        mairies = {}
        for f in self._features("mairies"):
            p = f["properties"]
            if f["geometry"] and f["geometry"]["type"] == "Point" and (p.get("type") == "mairie" or p["commune"] not in mairies):
                lon, lat = f["geometry"]["coordinates"][:2]
                mairies[p["commune"]] = (round(lon, 5), round(lat, 5))
        print(f"    {len(mairies)} mairies")
        print(f"    {len(regions)} régions, {len(deps)} départements, {len(epci)} EPCI, {len(communes)} communes")
        return {
            "vintage": f"Contours administratifs au 1er janvier {YEAR}",
            "_files": [self._path(n) for n in FILES],
            "regions": regions,
            "departements": deps,
            "epci": epci,
            "communes": communes,
            "mairies": mairies,
        }
