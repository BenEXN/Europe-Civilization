"""GeoNames places of 5,000+ inhabitants in the map's countries: the towns of the countries GISCO's local units or
urban areas do not cover (the Western Balkans, Cyprus, Iceland, Liechtenstein), for the city banners and the search box."""

from __future__ import annotations

import io
import re
import zipfile

from ..core.europe import COUNTRIES, FROM_ISO2
from ..core.names import latin
from ..core.source import Source, SourceInfo

URL = "https://download.geonames.org/export/dump/cities5000.zip"


class GeoNames(Source):
    info = SourceInfo(
        id="geonames",
        title="Places of 5,000+ inhabitants (GeoNames)",
        publisher="GeoNames",
        homepage="https://www.geonames.org/",
        license="CC BY 4.0",
        description="Populated places of 5,000+ inhabitants with their position and population. The cities of the "
        "countries without Urban Audit functional urban areas (Western Balkans, Cyprus, Iceland, Liechtenstein) come "
        "from here, and so do the searchable places of Bosnia and Herzegovina, Montenegro and Kosovo, which have no "
        "local administrative units in GISCO.",
        used_for=["Cities of the Western Balkans, Cyprus, Iceland and Liechtenstein",
                  "Place search in Bosnia and Herzegovina, Montenegro and Kosovo"],
    )

    def fetch(self, force=False):
        self.download(URL, "cities5000.zip", force=force, expect_binary=True)

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
            name = f[1] if not re.search("[\u0370-\u04ff]", f[1]) else (f[2] or latin(f[1]))  # Latin letters
            rows.append({"id": f[0], "name": name, "country": country, "lat": float(f[4]), "lon": float(f[5]),
                         "pop": int(f[14] or 0), "code": f[7]})
        print(f"    {len(rows)} places")
        return {"vintage": "GeoNames cities5000", "_files": ["cities5000.zip"], "places": rows}
