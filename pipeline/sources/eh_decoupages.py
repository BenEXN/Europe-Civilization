"""Économie Homéostatique — découpages transfrontaliers à superposer à la carte (rapport d'étape v1.1, §7 et §10.1).

Les zones tampons de l'EH relient les zones géographiques par la continuité des milieux. Elles sont à définir au
cours de la construction des indicateurs ; les découpages existants donnent des géométries réelles sur lesquelles
raisonner. Ce module télécharge ceux qui sont accessibles par un service ouvert :

* zones statistiques du CIEM (Conseil international pour l'exploration de la mer), sur lesquelles sont évalués les
  stocks halieutiques ;
* écorégions du CIEM, alignées par l'Agence européenne pour l'environnement sur les régions et sous-régions marines de
  la directive-cadre stratégie pour le milieu marin.

Les deux couches viennent du service WFS de Marine Regions (Flanders Marine Institute), en WGS 84. Les districts
hydrographiques (directive-cadre sur l'eau) et les régions biogéographiques (directive Habitats) sont publiés par
l'Agence européenne pour l'environnement sur des serveurs qui n'acceptent pas les connexions des machines de GitHub
Actions ; ils sont signalés comme manquants tant qu'une copie archivée n'est pas fournie (calibration/decoupages/)."""

from __future__ import annotations

import json
import urllib.parse
from pathlib import Path

from ..core.source import Source, SourceInfo
from .eh_lot import etat, telecharger

WFS = "https://geo.vliz.be/geoserver/MarineRegions/wfs"
ROOT = Path(__file__).resolve().parents[2]
ARCHIVES = ROOT / "calibration" / "decoupages"  # copies fournies à la main (GeoJSON WGS 84) et leur manifeste


def wfs(couche: str) -> str:
    q = {"service": "WFS", "version": "2.0.0", "request": "GetFeature", "typeNames": f"MarineRegions:{couche}",
         "outputFormat": "application/json", "srsName": "EPSG:4326"}
    return f"{WFS}?{urllib.parse.urlencode(q)}"


# id → description de la couche. nom / code / detail : champs candidats, le premier présent est retenu.
COUCHES = {
    "ciem_zones": {
        "couche": "ices_areas", "court": "Zones CIEM",
        "nom": "Zones statistiques du CIEM",
        "description": "Zones statistiques de l'Atlantique du Nord-Est sur lesquelles le CIEM évalue les stocks halieutiques.",
        "source": "CIEM, via Marine Regions (VLIZ)", "licence": "CC BY 4.0",
        "page": "https://www.marineregions.org/sources.php#ices",
        "champs_nom": ("area_full", "Area_Full", "ICESNAME", "ices_area"), "champs_code": ("area_27", "Area_27", "ICESCODE"),
        "champs_detail": ("subarea", "SubArea", "division", "Division"),
        "couleur": "#7fd3e6", "remplissage": "rgba(127,211,230,.18)", "tirets": [5, 4],
    },
    "ciem_ecoregions": {
        "couche": "ices_ecoregions", "court": "Écorégions marines",
        "nom": "Écorégions du CIEM (alignées sur la DCSMM)",
        "description": "Écorégions du CIEM, alignées sur les régions et sous-régions marines de la directive-cadre "
                       "stratégie pour le milieu marin.",
        "source": "CIEM, via Marine Regions (VLIZ)", "licence": "CC BY 4.0",
        "page": "https://www.marineregions.org/sources.php#ices",
        "champs_nom": ("ecoregion", "Ecoregion", "name", "Name"), "champs_code": ("ecoregion_id", "Ecoregion_ID", "id"),
        "champs_detail": (),
        "couleur": "#b9a4f0", "remplissage": "rgba(185,164,240,.16)", "tirets": [],
    },
}
REQUIS = tuple(COUCHES)

# Couches publiées par l'AEE, prises dans calibration/decoupages/<id>.geojson lorsqu'une copie y est archivée.
COUCHES_AEE = {
    "districts_hydro": {
        "court": "Districts hydrographiques", "nom": "Districts hydrographiques (directive-cadre sur l'eau)",
        "description": "Districts hydrographiques délimités pour les plans de gestion de la directive-cadre sur l'eau ; "
                       "les districts internationaux relient plusieurs États.",
        "source": "Agence européenne pour l'environnement (WISE WFD)", "licence": "réutilisation libre avec mention de la source",
        "page": "https://www.eea.europa.eu/en/datahub",
        "champs_nom": ("rbdName", "nameText", "RBD_NAME", "name"), "champs_code": ("thematicIdIdentifier", "euRBDCode", "RBD_CODE"),
        "champs_detail": ("internationalRBD", "countryCode"),
        "couleur": "#6fb2ff", "remplissage": "rgba(111,178,255,.16)", "tirets": [],
    },
    "regions_biogeo": {
        "court": "Régions biogéographiques", "nom": "Régions biogéographiques (directive Habitats)",
        "description": "Délimitations officielles de la directive Habitats et du réseau Émeraude ; l'état de conservation "
                       "de l'article 17 est rapporté par région et par pays.",
        "source": "Agence européenne pour l'environnement", "licence": "réutilisation libre avec mention de la source",
        "page": "https://www.eea.europa.eu/en/datahub/datahubitem-view/11db8d14-f167-4cd5-9205-95638dfd9618",
        "champs_nom": ("name", "short_name", "code"), "champs_code": ("code", "short_name"), "champs_detail": (),
        "couleur": "#9ed36a", "remplissage": "rgba(158,211,106,.16)", "tirets": [2, 3],
    },
}


def premier(props: dict, champs: tuple):
    bas = {k.lower(): v for k, v in props.items()}
    for c in champs:
        v = props.get(c, bas.get(c.lower()))
        if v not in (None, ""):
            return v
    return None


def entites(geo: dict, desc: dict) -> list:
    out = []
    for f in geo.get("features", []):
        p = f.get("properties") or {}
        nom = premier(p, desc["champs_nom"])
        code = premier(p, desc["champs_code"])
        detail = premier(p, desc["champs_detail"]) if desc["champs_detail"] else None
        out.append({"nom": str(nom if nom is not None else code if code is not None else f.get("id", "?")),
                    "code": None if code is None else str(code),
                    "detail": None if detail is None else str(detail), "geometry": f.get("geometry")})
    return out


def presentation(cle: str, desc: dict) -> dict:
    return {"id": cle, **{k: desc[k] for k in ("court", "nom", "description", "source", "licence", "page", "couleur",
                                              "remplissage", "tirets")}}


class EhDecoupages(Source):
    info = SourceInfo(
        id="eh_decoupages",
        title="Économie Homéostatique — découpages transfrontaliers (zones et écorégions du CIEM)",
        publisher="ICES, via Marine Regions (Flanders Marine Institute, VLIZ)",
        homepage="https://www.marineregions.org/",
        license="CC BY 4.0",
        description="Zones statistiques et écorégions du CIEM (service WFS de Marine Regions), à superposer aux pays pour "
        "raisonner sur les zones tampons de l'EH.",
        used_for=["Carte de l'Économie Homéostatique (découpages transfrontaliers)"],
    )

    def fetch(self, force=False):
        for cle, d in COUCHES.items():
            telecharger(self, cle, wfs(d["couche"]), force)

    def process(self):
        decoupages, tables, fichiers = [], {}, []
        manifeste = json.loads((self.raw_dir / "manifest.json").read_text()) if (self.raw_dir / "manifest.json").exists() else {}
        for cle, d in COUCHES.items():
            e = etat(self.raw_dir, cle)
            if not e["present"]:
                tables[cle] = {"requise": True, "disponible": False, "erreur": e["erreur"] or "non téléchargée"}
                continue
            geo = json.loads((self.raw_dir / f"{cle}.json").read_text())
            feats = entites(geo, d)
            champs = sorted({k for f in geo.get("features", []) for k in (f.get("properties") or {})})
            print(f"    {cle:16s} {len(feats)} entités ; champs : {', '.join(champs)}")
            m = manifeste.get(f"{cle}.json", {})
            tables[cle] = {"requise": True, "disponible": bool(feats), "perime": e["perime"], "recupere": e["recupere"],
                           "erreur": e["erreur"], "champs": champs}
            fichiers.append(f"{cle}.json")
            decoupages.append(presentation(cle, d) | {"url": m.get("url") or wfs(d["couche"]), "recupere": e["recupere"] or "",
                                                     "sha256": m.get("sha256"), "features": feats})
        manquants = []
        for cle, d in COUCHES_AEE.items():
            chemin = ARCHIVES / f"{cle}.geojson"
            if not chemin.exists():
                manquants.append({"id": cle, "nom": d["nom"], "raison": "serveurs de l'AEE injoignables depuis GitHub Actions ; "
                                  f"copie attendue dans calibration/decoupages/{cle}.geojson"})
                continue
            meta = json.loads((ARCHIVES / f"{cle}.json").read_text()) if (ARCHIVES / f"{cle}.json").exists() else {}
            feats = entites(json.loads(chemin.read_text()), d)
            print(f"    {cle:16s} {len(feats)} entités (copie archivée)")
            decoupages.append(presentation(cle, d) | {"url": meta.get("url", ""), "recupere": meta.get("recupere", ""),
                                                     "sha256": meta.get("sha256"), "features": feats})
        absents = [c for c in REQUIS if not tables.get(c, {}).get("disponible") or tables[c].get("perime")]
        if absents:
            from .eh_lot import LotIncomplet
            raise LotIncomplet(f"eh_decoupages : couches absentes ou périmées : {', '.join(absents)}")
        return {"vintage": "Marine Regions WFS, " + ", ".join(f"{c} {(t.get('recupere') or '')[:10]}" for c, t in tables.items()),
                "_files": fichiers, "decoupages": decoupages, "manquants": manquants, "tables": tables}
