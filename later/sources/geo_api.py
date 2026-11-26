"""Legal populations of the communes, from the API Découpage administratif (geo.api.gouv.fr).

Used only where the Insee comparateur has no 2023 figure: Mayotte, whose census runs on its own calendar (the
legal populations there come from the 2017 census). Also a cross-check of the comparateur's populations.
"""

from __future__ import annotations

import json

from ..core.source import Source, SourceInfo

URL = "https://geo.api.gouv.fr/communes?fields=code,nom,population,codeDepartement&format=json"
FILE = "communes.json"


class GeoApiCommunes(Source):
    info = SourceInfo(
        id="geo_api_communes",
        title="Populations légales des communes (API Découpage administratif)",
        publisher="Etalab / DINUM, d'après l'Insee",
        homepage="https://geo.api.gouv.fr/decoupage-administratif",
        license="Licence Ouverte 2.0 (Etalab)",
        description="La population légale de chaque commune. Elle complète les chiffres de l'Insee là où le "
        "comparateur n'a pas d'année 2023 : à Mayotte, dont le recensement suit un autre calendrier, c'est la "
        "population légale issue du recensement de 2017.",
        used_for=["Population de Mayotte (recensement 2017)", "Contrôle des populations communales"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        rows = json.loads((self.raw_dir / FILE).read_text())
        pop = {r["code"]: r["population"] for r in rows if r.get("population") is not None}
        print(f"    {len(pop)} communes with a legal population")
        return {"vintage": "Populations légales (geo.api.gouv.fr)", "_files": [FILE], "communes": pop}
