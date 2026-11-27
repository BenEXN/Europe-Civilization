"""Économie Homéostatique — données de la carte (web/data/eh.json).

  python3 analyse/carte_eh.py

Rassemble, pour l'extension web/js/ext/eh :

* les résultats de l'analyse de sensibilité de l'IED (calibration/sensibilite_ied.json) : les 480 configurations de la
  grille, la configuration de référence, l'enveloppe de chaque pays, les mesures et leurs rapports aux repères ;
* les découpages transfrontaliers téléchargés par la source eh_decoupages (data/interim/eh_decoupages.json), projetés
  dans le repère de la carte et simplifiés pour l'affichage.

Aucune valeur n'est recalculée ici, à une exception près, signalée dans le fichier : le rapport de la RMC totale aux
repères matière, qui portent sur le même périmètre (variante de périmètre du rapport d'étape, §6.3)."""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from pipeline.core.geo import MapProjection  # noqa: E402

CAL = ROOT / "calibration"
WEB = ROOT / "web" / "data"
INTERIM = ROOT / "data" / "interim" / "eh_decoupages.json"

# Repère de la carte (pipeline/build/world.py) : LAEA sphérique centrée sur 52° N 10° E, 2,5 unités par km, marge de
# 400 unités. min_x et max_y sont ceux du _world.json qui a produit web/data/world.json ; verifier_projection()
# les confronte aux sites UNESCO de web/data/wonders.json.
PROJECTION = {"min_x": -1680.7, "max_y": 2200.2, "margin": 400.0}
CONTROLES_PROJECTION = {  # nom dans wonders.json → (lon, lat)
    "Aachen Cathedral": (6.0839, 50.7747),
    "Mont-Saint-Michel and its Bay": (-1.5114, 48.6361),
    "Acropolis, Athens": (23.7257, 37.9715),
    "Historic Centre of Prague": (14.4206, 50.0875),
}
TOLERANCE = 2.5      # unités carte (1 km) : simplification de Douglas-Peucker
AIRE_MIN = 120.0     # unités² (≈ 19 km²) : anneaux plus petits omis à l'affichage

NOMS = {
    "AT": "Autriche", "BE": "Belgique", "BG": "Bulgarie", "CY": "Chypre", "CZ": "Tchéquie", "DE": "Allemagne",
    "DK": "Danemark", "EE": "Estonie", "EL": "Grèce", "ES": "Espagne", "FI": "Finlande", "FR": "France",
    "HR": "Croatie", "HU": "Hongrie", "IE": "Irlande", "IT": "Italie", "LT": "Lituanie", "LU": "Luxembourg",
    "LV": "Lettonie", "MT": "Malte", "NL": "Pays-Bas", "PL": "Pologne", "PT": "Portugal", "RO": "Roumanie",
    "SE": "Suède", "SI": "Slovénie", "SK": "Slovaquie",
}
COURT = {"irnr_rmc_abiotique": "Empreinte matière non renouvelable", "iee_co2_empreinte": "Empreinte CO2",
         "iee_azote": "Azote fixé", "iee_phosphore": "Phosphore minéral", "irnr_rmc_totale": "Empreinte matière totale"}
OPTIONS = ("normalisation", "agregation", "poids", "seuil_irnr", "ibd")

AVERTISSEMENT = ("Aucune valeur de cette carte n'est une mesure de l'IED : chacune dépend de choix de construction "
                 "explicites (repères, normalisation, agrégation, pondérations) et d'un IBD supposé, faute de mesure.")
TEXTE_DECOUPAGES = ("Découpages existants, superposés aux pays : ils ne fixent pas la règle de l'EH, ils donnent des "
                    "géométries réelles sur lesquelles raisonner pour définir les zones tampons. Les indicateurs restent "
                    "calculés par État membre, échelle de publication des statistiques.")
TEXTE_METHODE = ("Repères normatifs absolus répartis à parts égales par habitant (O'Neill et al. 2018 ; Bringezu 2015). "
                 "Normalisation sur [0, 2] sous trois formes construites pour l'analyse ; agrégation aux deux étages "
                 "(sous-indicateurs de l'IEE, puis composantes de l'IED). Une série absente pour l'année retenue est "
                 "remplacée par la plus récente des trois années précédentes ; les termes d'une somme ou d'un ratio "
                 "sont de la même année.")


# ----------------------------------------------------------------------------------------------- géométrie

def projection() -> MapProjection:
    return MapProjection(PROJECTION["min_x"], PROJECTION["max_y"], PROJECTION["margin"])


def verifier_projection(proj: MapProjection, tol: float = 2.0) -> float:
    """Écart maximal (unités carte) entre la projection et les sites de contrôle de wonders.json."""
    sites = {w["name"]: w for w in json.loads((WEB / "wonders.json").read_text())["wonders"]}
    ecart = 0.0
    for nom, (lon, lat) in CONTROLES_PROJECTION.items():
        x, y = proj(lon, lat)
        ecart = max(ecart, math.hypot(x - sites[nom]["x"], y - sites[nom]["y"]))
    if ecart > tol:
        raise SystemExit(f"projection : écart de {ecart:.1f} unités avec wonders.json ; le repère de la carte a changé")
    return ecart


def douglas_peucker(pts: list, tol: float) -> list:
    if len(pts) < 4:
        return pts
    garde = [False] * len(pts)
    garde[0] = garde[-1] = True
    pile = [(0, len(pts) - 1)]
    while pile:
        a, b = pile.pop()
        (x1, y1), (x2, y2) = pts[a], pts[b]
        dx, dy = x2 - x1, y2 - y1
        n = math.hypot(dx, dy) or 1e-12
        dmax, imax = 0.0, -1
        for i in range(a + 1, b):
            x0, y0 = pts[i]
            d = abs(dy * x0 - dx * y0 + x2 * y1 - y2 * x1) / n if n > 1e-9 else math.hypot(x0 - x1, y0 - y1)
            if d > dmax:
                dmax, imax = d, i
        if dmax > tol and imax > 0:
            garde[imax] = True
            pile += [(a, imax), (imax, b)]
    return [p for p, g in zip(pts, garde) if g]


def aire(pts: list) -> float:
    return abs(sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(pts, pts[1:] + pts[:1]))) / 2


def decouper(pts: list, x0: float, y0: float, x1: float, y1: float) -> list:
    """Sutherland–Hodgman : l'anneau découpé par le cadre de la carte."""
    def clip(p, dedans, inter):
        out = []
        for i, b in enumerate(p):
            a = p[i - 1]
            if dedans(b):
                if not dedans(a):
                    out.append(inter(a, b))
                out.append(b)
            elif dedans(a):
                out.append(inter(a, b))
        return out

    def ix(a, b, x):
        t = (x - a[0]) / (b[0] - a[0])
        return (x, a[1] + t * (b[1] - a[1]))

    def iy(a, b, y):
        t = (y - a[1]) / (b[1] - a[1])
        return (a[0] + t * (b[0] - a[0]), y)

    for dedans, inter in ((lambda p: p[0] >= x0, lambda a, b: ix(a, b, x0)),
                          (lambda p: p[0] <= x1, lambda a, b: ix(a, b, x1)),
                          (lambda p: p[1] >= y0, lambda a, b: iy(a, b, y0)),
                          (lambda p: p[1] <= y1, lambda a, b: iy(a, b, y1))):
        pts = clip(pts, dedans, inter)
        if not pts:
            return []
    return pts


def anneaux(geom: dict) -> list:
    if not geom:
        return []
    if geom["type"] == "Polygon":
        return list(geom["coordinates"])
    if geom["type"] == "MultiPolygon":
        return [r for poly in geom["coordinates"] for r in poly]
    return []


def projeter_entite(geom: dict, proj, cadre) -> tuple[list, list] | None:
    """Anneaux à plat [x0, y0, x1, y1, …] en unités carte (arrondis au dixième), et l'emprise ; None si rien ne reste."""
    out = []
    for ring in anneaux(geom):
        if len(ring) < 4:
            continue
        # Les antiméridiens et les territoires lointains sortent du cadre : on écarte d'abord ce qui en est loin.
        pts = [proj(lon, lat) for lon, lat, *_ in ring if -45 <= lon <= 70 and 25 <= lat <= 85]
        if len(pts) < 4:
            continue
        pts = decouper(douglas_peucker(pts, TOLERANCE), *cadre)
        if len(pts) < 3 or aire(pts) < AIRE_MIN:
            continue
        out.append([round(c, 1) for p in pts for c in p])
    if not out:
        return None
    xs = [v for r in out for v in r[0::2]]
    ys = [v for r in out for v in r[1::2]]
    return out, [min(xs), min(ys), max(xs), max(ys)]


def decoupages(proj) -> tuple[list, list]:
    if not INTERIM.exists():
        print("  découpages : data/interim/eh_decoupages.json absent ; la carte n'aura que les indicateurs")
        return [], []
    world = json.loads((WEB / "world.json").read_text())
    cadre = (0.0, 0.0, float(world["width"]), float(world["height"]))
    src = json.loads(INTERIM.read_text())["data"]
    out = []
    for k, d in enumerate(src["decoupages"]):
        feats = []
        for f in d["features"]:
            r = projeter_entite(f["geometry"], proj, cadre)
            if r is None:
                continue
            feats.append({"nom": f["nom"], "code": f.get("code"), "detail": f.get("detail"), "rings": r[0], "bbox": r[1]})
        print(f"  {d['id']:16s} {len(d['features'])} entités téléchargées, {len(feats)} sur la carte")
        out.append({k2: v for k2, v in d.items() if k2 != "features"} | {"ordre": k, "features": feats})
    return out, src.get("manquants", [])


# ----------------------------------------------------------------------------------------------- indicateurs

def indicateurs() -> dict:
    s = json.loads((CAL / "sensibilite_ied.json").read_text())
    lot = json.loads((CAL / "provenance" / "lot.json").read_text())
    res = s["resultats"]
    options = {k: list(dict.fromkeys(r[k] for r in res)) for k in OPTIONS}
    idx = {k: {v: i for i, v in enumerate(vs)} for k, vs in options.items()}
    cle = {"normalisation": "n", "agregation": "a", "poids": "p", "seuil_irnr": "s", "ibd": "b"}
    comp = s.get("composantes", {})
    composantes = {
        "iee": [{"n": idx["normalisation"][c["normalisation"]], "a": idx["agregation"][c["agregation"]], "valeurs": c["valeurs"]}
                for c in comp.get("iee", [])],
        "irnr": [{"n": idx["normalisation"][c["normalisation"]], "s": idx["seuil_irnr"][c["seuil_irnr"]], "valeurs": c["valeurs"]}
                 for c in comp.get("irnr", [])],
    }
    scenarios = []
    for r in res:
        if r["agregation_iee"] != r["agregation"] or r["agregation_ied"] != r["agregation"]:
            continue  # la grille agrège aux deux étages avec la même fonction ; les expériences à un étage sont à part
        scenarios.append({cle[k]: idx[k][r[k]] for k in OPTIONS} | {"ied": r["ied"]})
    ref = s["configuration_reference"]
    reference_indices = {cle[k]: idx[k][ref[k if k != "agregation" else "agregation"]] for k in OPTIONS}

    sous = {}
    for k, v in s["sous_indicateurs"].items():
        seuils = {lbl: t | {"nature_texte": s["natures_des_reperes"].get(t["nature"], t["nature"])}
                  for lbl, t in v["seuils"].items()}
        sous[k] = {"composante": v["composante"], "libelle": v["libelle"], "court": COURT.get(k, v["libelle"]),
                   "unite": v["unite"], "note": v.get("note", ""), "seuils": seuils}
    # Variante de périmètre : RMC totale (biomasse comprise), rapportée aux repères matière de même périmètre.
    base = s["sous_indicateurs"]["irnr_rmc_abiotique"]["seuils"]
    sous["irnr_rmc_totale"] = {
        "composante": "IRNR", "court": COURT["irnr_rmc_totale"], "unite": "t/hab",
        "libelle": "Empreinte matière totale (RMC, biomasse comprise)",
        "note": "Variante de périmètre : la RMC totale porte sur le même périmètre que les repères matière ; "
                "elle mesure la pression matérielle totale, et non la seule consommation de ressources non renouvelables.",
        "seuils": {lbl: t | {"nature_texte": s["natures_des_reperes"].get(t["nature"], t["nature"])} for lbl, t in base.items()},
    }

    marques = {}
    for st in s["statuts_utilises"]:
        marques.setdefault(st["pays"], set()).add(st["code"])
    pays = {}
    for a, mes in s["mesures"].items():
        rap = {k: dict(v) for k, v in s["rapport_au_seuil"].get(a, {}).items()}
        if "irnr_rmc_totale" in mes:
            rap["irnr_rmc_totale"] = {lbl: round(mes["irnr_rmc_totale"] / t["valeur"], 3) for lbl, t in base.items()}
        pays[a] = {"nom": NOMS.get(a, a), "mesures": mes, "rapports": rap, "complet": a in s["pays_complets"],
                   "plage": s["plages"].get(a), "plage_ibd_reference": s["plages_ibd_reference"].get(a),
                   "marques": " ".join(sorted(marques.get(a, ())))}
    return {
        "annee": s["annee"], "lot": lot["lot"], "nb_configurations": s["configurations"],
        "pays_complets": s["pays_complets"], "options": options, "scenarios": scenarios, "composantes": composantes,
        "reference": ref, "reference_indices": reference_indices,
        "sous_indicateurs": sous,
        "sous_indicateurs_ordre": ["iee_co2_empreinte", "irnr_rmc_abiotique", "irnr_rmc_totale", "iee_azote", "iee_phosphore"],
        "pays": pays, "sources": s["sources"],
        "variante_rmc_totale": s["perimetre_irnr_total"], "ibd_heterogene": s["ibd_heterogene"],
    }


def main() -> None:
    proj = projection()
    print(f"  projection : écart maximal {verifier_projection(proj):.2f} unité avec wonders.json")
    out = {
        "version": 1,
        "avertissement": AVERTISSEMENT, "texte_decoupages": TEXTE_DECOUPAGES, "texte_methode": TEXTE_METHODE,
        "depot": "https://github.com/BenEXN/Europe-Civilization/tree/main/calibration",
        "rapport": "https://github.com/BenEXN/Europe-Civilization/blob/main/calibration/Rapport_etape_calibration_EH_2026-11-27_v1.2.pdf",
        **indicateurs(),
    }
    out["decoupages"], out["decoupages_manquants"] = decoupages(proj)
    (WEB / "eh.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"  web/data/eh.json : {(WEB / 'eh.json').stat().st_size / 1e3:.0f} ko, {len(out['scenarios'])} configurations")


if __name__ == "__main__":
    main()
