"""Économie Homéostatique — données de la carte (web/data/eh.json).

  python3 analyse/carte_eh.py

Rassemble, pour l'extension web/js/ext/eh :

* les résultats de l'analyse de sensibilité de l'IED (calibration/sensibilite_ied.json) : les 480 configurations de la
  grille, la configuration de référence, l'enveloppe de chaque pays, les mesures et leurs rapports aux repères ;
* l'exercice monétaire (calibration/ecodotations.json) : par pays, la population, le PIB et l'assiette 𝒴 de chaque
  variante, en euros constants 2017, et l'IED de zone de chaque configuration ; la carte en tire les écodotations
  e = Φ(IED) · e_base pour le canal, l'échelle, la forme de Φ et l'affichage choisis ;
* les découpages transfrontaliers téléchargés par la source eh_decoupages (data/interim/eh_decoupages.json), projetés
  dans le repère de la carte et simplifiés pour l'affichage.

Aucune valeur n'est recalculée ici, à une exception près, signalée dans le fichier : la conversion du PIB et de 𝒴 en
euros constants 2017 par le facteur de déflation de β_pub. Les IED des scénarios et de la zone sont repris sans
arrondi, pour que les écodotations calculées par la carte partent des valeurs non arrondies ; l'arrondi est fait à
l'affichage."""

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
COURT = {"irnr_rmc_abiotique": "Empreinte matière non renouvelable (variante)", "iee_co2_empreinte": "Empreinte CO2",
         "iee_azote": "Azote fixé", "iee_phosphore": "Phosphore minéral",
         "irnr_rmc_totale": "Empreinte matière totale (mesure de l'IRNR)"}
OPTIONS = ("normalisation", "agregation", "poids", "seuil_irnr", "ibd")

AVERTISSEMENT = ("Aucune valeur de cette carte n'est une mesure de l'IED : chacune dépend de choix de construction "
                 "explicites (repères, normalisation, agrégation, pondérations) et d'un IBD supposé, faute de mesure.")
TEXTE_DECOUPAGES = ("Découpages existants, superposés aux pays : ils ne fixent pas la règle de l'EH, ils donnent des "
                    "géométries réelles sur lesquelles raisonner pour définir les zones tampons. Les indicateurs restent "
                    "calculés par État membre, échelle de publication des statistiques.")
TEXTE_METHODE = ("Repères normatifs absolus répartis à parts égales par habitant (O'Neill et al. 2018 ; Bringezu 2015). "
                 "L'IRNR est calculé sur l'empreinte matière totale (RMC, biomasse comprise), périmètre des repères : "
                 "il mesure la pression matérielle totale, non le seul objet IRNR du WP (la biomasse, renouvelable, "
                 "recoupe l'IEE). "
                 "Normalisation sur [0, 2] sous trois formes construites pour l'analyse ; agrégation aux deux étages "
                 "(sous-indicateurs de l'IEE, puis composantes de l'IED). Une série absente pour l'année retenue est "
                 "remplacée par la plus récente des trois années précédentes ; les termes d'une somme ou d'un ratio "
                 "sont de la même année.")


TEXTE_MONNAIE = ("Exercice : les écodotations que donneraient les formules exploratoires du WP (§4.2) appliquées aux "
                 "données publiques. DETA = u × β_pub × c ; la dotation totale des citoyens d'un État est égale à sa "
                 "dotation publique ; DENT = u × 𝒴 ; dotation globale DG = DTETA + DTCIT + DTENT, avec u = Φ(IED). "
                 "L'exercice rend visibles les ordres de grandeur et le poids relatif des canaux, que le WP renvoie au "
                 "calibrage. Aucun montant n'est une prévision ni une proposition budgétaire : β_pub, l'assiette 𝒴, la "
                 "parité entre canaux et Φ sont des points de calibration initiaux, et la relation entre création "
                 "monétaire, production réelle et valeur de la monnaie relève du programme de recherche (E2). La masse "
                 "monétaire M, la fonte et la création secondaire ne sont pas représentées : M est une variable "
                 "contrefactuelle.")
TEXTE_ECHANGES = ("Les échanges commerciaux entre zones ne sont pas représentés dans le calcul des écodotations ; "
                  "certains sous-indicateurs (empreinte CO2, empreinte matière) attribuent toutefois aux pays les "
                  "pressions liées à leur consommation.")
TEXTE_HARMONISATION = ("β_pub est un même montant par citoyen pour tous les pays. Rapporté au PIB par habitant, il fait "
                       "apparaître la question de l'harmonisation du système entre économies de niveaux de production "
                       "et de prix différents.")
TEXTE_PHI = ("Φ₀(z) = z est la fonction candidate du WP. Les autres formes sont construites pour l'illustration et "
             "vérifient les propriétés minimales que le WP fixe pour Φ : continue, croissante au sens large, Φ(0) = 0 "
             "et Φ(1) = 1. Le WP borne le coefficient de régulation à U = [0, u_max], avec u_max ≥ 1 : sur un IED "
             "compris entre 0 et 2, Φ₀ et √z demandent u_max ≥ 2, z² demande u_max ≥ 4, min(z, 1) convient à "
             "u_max = 1.")


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

def codes_ied(s: dict) -> dict:
    """Codes Eurostat des termes qui entrent dans l'IED de chaque pays (sous-indicateurs de l'IEE et mesure de l'IRNR) :
    {pays: ["sous-indicateur terme année : code", …]}. Ils accompagnent les dotations qui dépendent de l'IED."""
    utiles = {k for k, v in s["sous_indicateurs"].items() if v["composante"] == "IEE"} | {s["cle_irnr"]}
    out = {}
    for st in s["statuts_utilises"]:
        if st["sous_indicateur"] in utiles:
            out.setdefault(st["pays"], set()).add(f"{st['terme']} {st['annee']} : {st['code']}")
    return {g: sorted(v) for g, v in out.items()}


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
        scenarios.append({cle[k]: idx[k][r[k]] for k in OPTIONS} | {"ied": r.get("ied_brut", r["ied"])})
    ref = s["configuration_reference"]
    reference_indices = {cle[k]: idx[k][ref[k if k != "agregation" else "agregation"]] for k in OPTIONS}

    sous = {}
    for k, v in s["sous_indicateurs"].items():
        seuils = {lbl: t | {"nature_texte": s["natures_des_reperes"].get(t["nature"], t["nature"])}
                  for lbl, t in v["seuils"].items()}
        sous[k] = {"composante": v["composante"], "libelle": v["libelle"], "court": COURT.get(k, v["libelle"]),
                   "unite": v["unite"], "note": v.get("note", ""), "seuils": seuils}
    marques = {}
    for st in s["statuts_utilises"]:
        marques.setdefault(st["pays"], set()).add(st["code"])
    pays = {}
    for a, mes in s["mesures"].items():
        rap = {k: dict(v) for k, v in s["rapport_au_seuil"].get(a, {}).items()}
        pays[a] = {"nom": NOMS.get(a, a), "mesures": mes, "rapports": rap, "complet": a in s["pays_complets"],
                   "plage": s["plages"].get(a), "plage_ibd_reference": s["plages_ibd_reference"].get(a),
                   "marques": " ".join(sorted(marques.get(a, ())))}
    return {
        "annee": s["annee"], "lot": lot["lot"], "nb_configurations": s["configurations"],
        "pays_complets": s["pays_complets"], "options": options, "scenarios": scenarios, "composantes": composantes,
        "reference": ref, "reference_indices": reference_indices,
        "sous_indicateurs": sous,
        "sous_indicateurs_ordre": ["iee_co2_empreinte", s["cle_irnr"], "irnr_rmc_abiotique", "iee_azote", "iee_phosphore"],
        "pays": pays, "sources": s["sources"], "codes_ied": codes_ied(s),
        "variante_irnr_abiotique": s["variante_irnr_abiotique"], "ibd_heterogene": s["ibd_heterogene"],
    }


def monnaie(scenarios_idx, codes: dict | None = None) -> dict | None:
    """Exercice monétaire : bases par pays (euros constants 2017) et IED de zone indexé comme les scénarios.

    codes : codes Eurostat des termes de l'IED par pays (codes_ied) ; ils sont joints aux dotations nationales
    (codes_ied de chaque pays) et, pour l'IED de zone, réunis pour tous les pays de la zone."""
    chemin = CAL / "ecodotations.json"
    if not chemin.exists():
        return None
    codes = codes or {}
    e = json.loads(chemin.read_text())
    f = e["facteur_deflation"]  # euros courants de l'année → euros constants 2017 (déflateur de β_pub)
    pays = {}
    for g, r in e["pays"].items():
        if not r.get("disponible") or g not in NOMS:
            continue
        pays[g] = {"population_milliers": r["population_milliers"], "pib_mio_eur2017": round(r["pib_mio_eur"] * f, 1),
                   "y_mio_eur2017": {c: round(a["y_mio_eur"] * f, 1) for c, a in r["assiettes"].items()},
                   "codes": r["codes"] + sorted({f"{t['terme']} {t['annee']} : {t['code']}"
                                                  for a in r["assiettes"].values() for t in a["codes"]}),
                   "codes_ied": codes.get(g, [])}
    zone = None
    if e.get("zone"):
        z = e["zone"]
        zone = {"pays": z["pays"], "methode": z["methode"], "mesures_par_habitant": z["mesures_par_habitant"],
                "ied": {scenarios_idx(g): g.get("ied_brut", g["ied"]) for g in z["grille"]},
                "codes_ied": sorted(f"{g} {c}" for g in z["pays"] for c in codes.get(g, []))}
    return {"annee": e["annee"], "beta_pub_eur2017": e["beta_pub_eur_constants_2017"], "facteur_deflation": f,
            "lissage_y": e["lissage_y"], "assiettes": e["assiettes"], "pays": pays, "zone": zone,
            "texte": TEXTE_MONNAIE, "texte_echanges": TEXTE_ECHANGES, "texte_harmonisation": TEXTE_HARMONISATION,
            "texte_phi": TEXTE_PHI}


def main() -> None:
    proj = projection()
    print(f"  projection : écart maximal {verifier_projection(proj):.2f} unité avec wonders.json")
    out = {
        "version": 1,
        "avertissement": AVERTISSEMENT, "texte_decoupages": TEXTE_DECOUPAGES, "texte_methode": TEXTE_METHODE,
        "depot": "https://github.com/BenEXN/Europe-Civilization/tree/main/calibration",
        "rapport": "https://github.com/BenEXN/Europe-Civilization/blob/main/calibration/Rapport_etape_calibration_EH_2026-11-27_v1.5.pdf",
        **indicateurs(),
    }
    idx = {k: {v: i for i, v in enumerate(vs)} for k, vs in out["options"].items()}
    cle = lambda g: "".join(str(idx[k][g[k]]) for k in OPTIONS)  # noqa: E731 — même ordre que le lien #eh=ied.napsb
    out["monnaie"] = monnaie(cle, out["codes_ied"])
    out["decoupages"], out["decoupages_manquants"] = decoupages(proj)
    (WEB / "eh.json").write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")))
    print(f"  web/data/eh.json : {(WEB / 'eh.json').stat().st_size / 1e3:.0f} ko, {len(out['scenarios'])} configurations")


if __name__ == "__main__":
    main()
