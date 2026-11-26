"""French rivers from IGN BD CARTO (hydrographic segments 15 m wide or more), read through the Géoplateforme WFS."""

from __future__ import annotations

import json
import re
import urllib.parse

from ..core.geo import INSETS
from ..core.source import Source, SourceInfo

LAYER = "BDCARTO_V5:troncon_hydrographique"
# Width classes of 15 m and more. Wide rivers are drawn as water surfaces in BD CARTO, with a "fictitious" axis
# segment through them: those count too, as do the axes through reservoirs on a river.
WIDTHS = ("Entre 15 et 50 m", "Plus de 50 m", "Entre 50 et 250 m", "Entre 250 et 1250 m", "Plus de 1250 m")
WIDE = set(WIDTHS[1:])
FILTER = (f"(classe_de_largeur IN ({', '.join(repr(w) for w in WIDTHS)}) OR (classe_de_largeur='Sans objet' AND "
          "nature='Retenue')) AND code_du_pays='FR' AND cpx_toponyme_de_cours_d_eau IS NOT NULL")
PAGE = 5000  # the Géoplateforme caps a page at 5,000 features
BASE = "https://data.geopf.fr/wfs/ows?" + urllib.parse.urlencode({
    "SERVICE": "WFS", "VERSION": "2.0.0", "REQUEST": "GetFeature", "TYPENAMES": LAYER,
    "OUTPUTFORMAT": "application/json", "SORTBY": "cleabs", "COUNT": PAGE, "SRSNAME": "EPSG:4326",
    "PROPERTYNAME": "cleabs,cpx_toponyme_de_cours_d_eau,classe_de_largeur,nature,geometrie",
    "CQL_FILTER": FILTER,
})
BBOX = (-5.6, 41.2, 9.8, 51.3)
# The overseas départements' rivers go to their insets (core/geo.py INSETS).
BOXES = [BBOX] + [(d["lon"][0], d["lat"][0], d["lon"][1], d["lat"][1]) for d in INSETS]


def in_box(x: float, y: float) -> bool:
    return any(b[0] <= x <= b[2] and b[1] <= y <= b[3] for b in BOXES)
CANAL = re.compile(r"^(Bras du |Bras de )?(Canal|Rigole|Dérivation|Contre-canal)\b|^Grand Canal", re.I)


def river_name(raw: str) -> str:
    """'la Loire/Loire' → 'Loire'; "l'Isère" → 'Isère'."""
    n = raw.split("/")[0].strip()
    if n.lower().startswith("fleuve "):
        n = n[7:]
    for art in ("la ", "le ", "les ", "l'", "l’"):
        if n.lower().startswith(art):
            n = n[len(art):]
            break
    return n[:1].upper() + n[1:]


class IgnRivers(Source):
    info = SourceInfo(
        id="ign_rivers",
        title="BD CARTO : tronçons hydrographiques de 15 m de large ou plus",
        publisher="IGN (Géoplateforme)",
        homepage="https://geoservices.ign.fr/bdcarto",
        license="Licence Ouverte 2.0 (Etalab)",
        description="Les cours d'eau nommés d'au moins 15 m de large en France métropolitaine et dans les départements d'outre-mer (axes des fleuves larges et "
        "des retenues compris). Ils "
        "sont réunis par cours d'eau, raccordés bout à bout et classés par largeur et longueur ; les fleuves et "
        "rivières des pays voisins restent ceux de Natural Earth.",
        used_for=["Fleuves et rivières de France"],
    )

    def fetch(self, force=False):
        k = 0
        while True:
            path = self.download(BASE + f"&STARTINDEX={k * PAGE}", f"troncons_{k:02d}.json", force=force)
            n = len(json.loads(path.read_text())["features"])
            if n < PAGE:
                break
            k += 1

    def process(self):
        rivers: dict[str, dict] = {}
        files = sorted(p.name for p in self.raw_dir.glob("troncons_*.json"))
        segs = 0
        for name in files:
            for f in json.loads((self.raw_dir / name).read_text())["features"]:
                p, g = f["properties"], f["geometry"]
                if not g:
                    continue
                lines = [g["coordinates"]] if g["type"] == "LineString" else g["coordinates"]
                lines = [[(round(x, 5), round(y, 5)) for x, y, *_ in ln] for ln in lines if len(ln) >= 2]
                lines = [ln for ln in lines if any(in_box(x, y) for x, y in ln)]
                if not lines:
                    continue
                name_ = river_name(p["cpx_toponyme_de_cours_d_eau"])
                if CANAL.match(name_):
                    continue  # canals are drawn as waterways, not as rivers tapering to a mouth
                r = rivers.setdefault(name_, {"wide": False, "lines": []})
                r["wide"] = r["wide"] or p["classe_de_largeur"] in WIDE
                r["lines"].extend(lines)
                segs += 1
        print(f"    {segs} segments, {len(rivers)} named rivers")
        return {"vintage": "BD CARTO (Géoplateforme)", "_files": files,
                "rivers": [{"name": n, "wide": r["wide"], "lines": r["lines"]} for n, r in sorted(rivers.items())]}
