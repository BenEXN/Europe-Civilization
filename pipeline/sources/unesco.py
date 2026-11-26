"""The World Heritage List, from UNESCO's own open data portal (data.unesco.org, dataset whc001): every inscribed
property with its category, inscription year, States Parties and the position of each of its components.
(whc.unesco.org's own XML export sits behind a browser challenge that scripts cannot pass.)"""

from __future__ import annotations

import json
import urllib.parse

from ..core.europe import COUNTRIES, FROM_ISO2
from ..core.source import Source, SourceInfo

FIELDS = ("id_no,name_en,date_inscribed,secondary_dates,date_end,danger,category,criteria_txt,states_names,iso_codes,"
          "transboundary,area_hectares,components_list,components_count,geo_point_2d")
URL = ("https://data.unesco.org/api/explore/v2.1/catalog/datasets/whc001/exports/json?"
       + urllib.parse.urlencode({"select": FIELDS}))
FILE = "whc001.json"


class Unesco(Source):
    info = SourceInfo(
        id="unesco",
        title="World Heritage List (UNESCO World Heritage Centre)",
        publisher="UNESCO World Heritage Centre, via the UNESCO open data portal",
        homepage="https://data.unesco.org/explore/dataset/whc001/",
        license="CC BY-SA 4.0",
        description="Every property on the World Heritage List: name, category (cultural, natural or mixed), year of "
        "inscription, States Parties, area, In Danger status and the position of each component of serial and "
        "transboundary properties. Only the properties with at least one State Party on the map are read.",
        used_for=["Wonders: UNESCO World Heritage properties"],
    )

    def fetch(self, force=False):
        self.download(URL, FILE, force=force)

    def process(self):
        rows = json.loads((self.raw_dir / FILE).read_text())
        out = []
        for r in rows:
            states = [FROM_ISO2.get(c, c) for c in (r.get("iso_codes") or [])]
            if not any(s in COUNTRIES for s in states) or r.get("date_end"):
                continue
            comps = []
            for c in json.loads(r.get("components_list") or "[]"):
                if c.get("latitude") is None or c.get("longitude") is None:
                    continue
                comps.append({"ref": c.get("ref") or "", "name": c.get("name") or "",
                              "lon": float(c["longitude"]), "lat": float(c["latitude"])})
            pt = r.get("geo_point_2d") or {}
            out.append({
                "id": str(r["id_no"]), "name": r["name_en"].strip(), "category": r["category"],
                "year": int(str(r["date_inscribed"])[:4]), "states": states, "states_names": r.get("states_names") or [],
                "transboundary": r.get("transboundary") == "true", "danger": r.get("danger") == "true",
                "area_ha": r.get("area_hectares"), "criteria": r.get("criteria_txt"), "components": comps,
                "centroid": [pt["lon"], pt["lat"]] if pt.get("lon") is not None else None,
            })
        out.sort(key=lambda s: int(s["id"]))
        print(f"    {len(out)} World Heritage properties with a State Party on the map (of {len(rows)} listed)")
        last = max(int(str(r["date_inscribed"])[:4]) for r in rows)
        return {"vintage": f"World Heritage List after the {last} session ({len(rows):,} properties)", "_files": [FILE],
                "properties": out}
