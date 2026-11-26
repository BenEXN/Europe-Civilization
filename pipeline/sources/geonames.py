"""GeoNames places of 5,000+ inhabitants in the map's countries: the towns of the countries GISCO's local units or
urban areas do not cover (the Western Balkans, Cyprus, Iceland, Liechtenstein), for the city banners and the search box.
For Bosnia and Herzegovina, Montenegro and Kosovo, which have no local units at all, also every populated place of the
country dumps (towns, villages, hamlets), for the map's place names, the search box and the density lens."""

from __future__ import annotations

import io
import re
import zipfile

from ..core.europe import COUNTRIES, FROM_ISO2
from ..core.names import latin
from ..core.source import Source, SourceInfo

URL = "https://download.geonames.org/export/dump/cities5000.zip"
DUMP = "https://download.geonames.org/export/dump/{c}.zip"
NO_LAU = ("BA", "ME", "XK")  # ISO codes of the countries without GISCO local units
# Populated places kept from the dumps: not sections of a city (PPLX), historical, abandoned or destroyed ones.
SETTLEMENTS = {"PPL", "PPLA", "PPLA2", "PPLA3", "PPLA4", "PPLC", "PPLL", "PPLS", "PPLF", "PPLR", "PPLG"}


class GeoNames(Source):
    info = SourceInfo(
        id="geonames",
        title="Places of 5,000+ inhabitants (GeoNames)",
        publisher="GeoNames",
        homepage="https://www.geonames.org/",
        license="CC BY 4.0",
        description="Populated places of 5,000+ inhabitants with their position and population. The cities of the "
        "countries without Urban Audit functional urban areas (Western Balkans, Cyprus, Iceland, Liechtenstein) come "
        "from here. Bosnia and Herzegovina, Montenegro and Kosovo have no local administrative units in GISCO: their "
        "towns, villages and hamlets come from the GeoNames country files, with the population GeoNames records.",
        used_for=["Cities of the Western Balkans, Cyprus, Iceland and Liechtenstein",
                  "Places of Bosnia and Herzegovina, Montenegro and Kosovo (map names, search, density)"],
    )

    def fetch(self, force=False):
        self.download(URL, "cities5000.zip", force=force, expect_binary=True)
        for c in NO_LAU:
            self.download(DUMP.format(c=c), f"{c}.zip", force=force, expect_binary=True)

    @staticmethod
    def _row(f: list) -> dict:
        name = f[1] if not re.search("[\u0370-\u04ff]", f[1]) else (f[2] or latin(f[1]))  # Latin letters
        return {"id": f[0], "name": name, "country": FROM_ISO2.get(f[8], f[8]), "lat": float(f[4]),
                "lon": float(f[5]), "pop": int(f[14] or 0), "code": f[7]}

    def process(self):
        rows = []
        with zipfile.ZipFile(self.raw_dir / "cities5000.zip") as z:
            text = z.read("cities5000.txt").decode("utf-8")
        for line in io.StringIO(text):
            f = line.rstrip("\n").split("\t")
            if len(f) < 15:
                continue
            country = FROM_ISO2.get(f[8], f[8])
            if country not in COUNTRIES or f[6] != "P":
                continue
            rows.append(self._row(f))
        settlements = []
        for c in NO_LAU:
            with zipfile.ZipFile(self.raw_dir / f"{c}.zip") as z:
                text = z.read(f"{c}.txt").decode("utf-8")
            for line in io.StringIO(text):
                f = line.rstrip("\n").split("\t")
                if len(f) >= 15 and f[6] == "P" and f[7] in SETTLEMENTS:
                    settlements.append(self._row(f))
        print(f"    {len(rows)} places of 5,000+; {len(settlements)} settlements in {', '.join(NO_LAU)}")
        return {"vintage": "GeoNames cities5000 and country files", "_files": ["cities5000.zip"] + [f"{c}.zip" for c in NO_LAU],
                "places": rows, "settlements": settlements}
