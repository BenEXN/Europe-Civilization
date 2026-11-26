"""Wonders: national parks, World Heritage sites, great universities and a few landmarks, each picked by a published
rule.

* national_park: the national parks of metropolitan France (Wikidata).
* unesco: the UNESCO World Heritage properties located in metropolitan France (Wikidata), placed at the main
  item's position; serial properties (Vauban, Le Corbusier, the mining basin) appear once.
* museum: the most-visited museums (« musées de France » attendance, ministry of culture), at most two per aire
  d'attraction; a museum that is already a wonder (Versailles, Fontainebleau) gives its visits to that wonder instead.
* research_university: the public universities with the most students (SISE), at most two per aire d'attraction.
* landmark: a short hand-picked list of landmarks, marked curated.
Writes web/data/wonders.json (loaded eagerly; a few tens of kB).
"""

from __future__ import annotations

import json
import re
import unicodedata
from collections import Counter

from ..core.geo import MapProjection, Shape, ShapeIndex
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, load_interim_payload, write_web

REQUIRES = ["_world", "wikidata_wonders", "universities", "museums", "insee_aav", "fr_boundaries", "cities.json"]
PRODUCES = ["wonders.json"]

N_UNIVERSITIES, PER_CITY = 15, 2
N_MUSEUMS = 10
DUP_KM = 120  # map units (~35 km): a museum this close to a wonder sharing a name word is the same site
SITE_RINGS = 2
NATURAL_WHS = {"258", "773", "1133", "1434", "1153"}  # natural or mixed properties (the rest are cultural)
CURATED = {"tour Eiffel": "Tour Eiffel", "viaduc de Millau": "Viaduc de Millau", "dune du Pilat": "Dune du Pilat",
           "gorges du Verdon": "Gorges du Verdon", "mont Blanc": "Mont Blanc", "falaises d'Étretat": "Falaises d'Étretat",
           "pont de Normandie": "Pont de Normandie", "château de Chenonceau": "Château de Chenonceau"}
CURATED_KIND = {"tour Eiffel": "landmark", "viaduc de Millau": "landmark", "dune du Pilat": "natural",
                "gorges du Verdon": "natural", "mont Blanc": "natural", "falaises d'Étretat": "natural",
                "pont de Normandie": "landmark", "château de Chenonceau": "landmark"}
SHORT = {  # map labels for long official names
    "80": "Mont-Saint-Michel", "85": "Grottes de la Vézère", "163": "Théâtre antique d'Orange",
    "164": "Arles romaine et romane", "203": "Salines royales", "228": "Avignon", "229": "Places de Nancy",
    "258": "Golfe de Porto", "600": "Rives de la Seine", "601": "Reims", "773": "Pyrénées-Mont Perdu",
    "868": "Chemins de Compostelle", "932": "Saint-Émilion", "933": "Val de Loire", "943": "Beffrois",
    "1153": "Causses et Cévennes", "1181": "Le Havre", "1256": "Bordeaux, port de la Lune",
    "1283": "Fortifications de Vauban", "1321": "Le Corbusier", "1337": "Albi", "1360": "Bassin minier",
    "1363": "Palafittes", "1425": "Climats de Bourgogne", "1434": "Chaîne des Puys", "1465": "Champagne",
    "1581": "Plages du Débarquement", "1613": "Villes d'eaux (Vichy)", "1625": "Phare de Cordouan",
    "1635": "Nice", "1725": "Alignements de Carnac", "495": "Strasbourg", "872": "Vieux Lyon",
    "1133": "Hêtraies anciennes", "873": "Provins",
}
RULES = [
    {"id": "national_park", "kind": "natural", "kinds": ["natural"],
     "text": "Les parcs nationaux de France métropolitaine (Wikidata), placés à leur point de référence ; la valeur "
             "est leur superficie."},
    {"id": "unesco", "kind": "landmark", "kinds": ["landmark", "natural"],
     "text": "Les biens du patrimoine mondial de l'UNESCO situés en France métropolitaine (Wikidata), avec leur année "
             "d'inscription. Un bien en série (fortifications de Vauban, œuvre de Le Corbusier, bassin minier) "
             "n'apparaît qu'une fois, à la position de l'élément principal."},
    {"id": "museum", "kind": "landmark", "kinds": ["landmark"],
     "text": f"Les {N_MUSEUMS} musées de France les plus visités (entrées de la dernière année complète, ministère de la "
             f"Culture), au plus {PER_CITY} par aire d'attraction. Un musée qui est déjà une merveille (le château de "
             "Versailles, celui de Fontainebleau) lui apporte ses entrées au lieu d'apparaître deux fois."},
    {"id": "research_university", "kind": "university", "kinds": ["university"],
     "text": f"Les {N_UNIVERSITIES} universités publiques qui comptent le plus d'étudiants inscrits (SISE), au plus "
             f"{PER_CITY} par aire d'attraction, placées à leur siège."},
    {"id": "landmark", "kind": "landmark", "kinds": ["landmark", "natural"], "curated": True,
     "text": "Quelques monuments et sites choisis à la main par ce projet, sans ordre d'importance."},
]


def uni_short(name: str) -> str:
    """'Université de Lille' → 'Lille'; 'Aix-Marseille Université' → 'Aix-Marseille'; 'Lyon-I université' → 'Lyon 1'."""
    n = re.sub(r"\s*[Uu]niversité\s*", " ", name).strip(" -")
    n = re.sub(r"^(de |d'|du )", "", n).replace("Lyon-I", "Lyon 1").replace("Lyon-II", "Lyon 2").strip()
    return n or name


# Map labels for long museum names, by Muséofile id; nameless rows of the attendance file, by commune.
MUSEUM_SHORT = {
    "M5031": "Louvre", "M5060": "Musée d'Orsay", "M5050": "Centre Pompidou", "M7003": "Muséum d'histoire naturelle",
    "M1111": "Petit Palais", "M5025": "Musée de l'Armée", "M5055": "Quai Branly", "M5030": "Orangerie",
    "M1104": "Carnavalet", "M5021": "Arts décoratifs", "M7042": "Musée des Confluences", "M5044": "Musée Rodin",
    "M0659": "Mémorial de Caen", "M0655": "Tapisserie de Bayeux", "M5002": "MuCEM", "M0629": "Palais des beaux-arts de Lille",
    "M0744": "Château des ducs de Bretagne", "M0271": "Château royal de Blois", "M5052": "Musée Condé (Chantilly)",
}
MUSEUM_BY_COMMUNE = {"62498": "Louvre-Lens"}
STOP = {"musee", "musees", "museum", "national", "nationale", "nationaux", "chateau", "chateaux", "palais", "parc",
        "maison", "centre", "art", "arts", "histoire", "ville", "beaux", "site", "sites", "place", "places", "fondation",
        "france", "moderne", "contemporain", "civilisations", "paris", "ville", "petit", "grand", "royal", "musee"}


def words(name: str) -> set[str]:
    s = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode().lower()
    return {w for w in re.findall(r"[a-z]{4,}", s) if w not in STOP}


def museum_short(m: dict) -> str:
    if m.get("id") in MUSEUM_SHORT:
        return MUSEUM_SHORT[m["id"]]
    n = re.sub(r"\s*\(.*?\)", "", cap(m["name"])).split(" - ")[0].split(", ")[0]
    return n if len(n) <= 32 else n[:31].rstrip() + "…"


def cap(s: str) -> str:
    return s[:1].upper() + s[1:] if s else s


def build() -> None:
    world = load_interim("_world")
    wd_payload = load_interim_payload("wikidata_wonders")
    wd = wd_payload["data"]
    unis = load_interim_payload("universities")
    aav = load_interim("insee_aav")
    grid, proj, owner = HexGrid(**world["grid"]), MapProjection(**world["projection"]), world["owner"]
    states, communes, samples = world["states"], world["communes"], world["commune_samples"]
    city_ids = {c["id"] for c in json.loads((WEB_DATA / "cities.json").read_text())}
    aav_of = {c["code"]: c["aav"] for c in aav["communes"] if c["aav"] in city_ids}
    bounds = load_interim("fr_boundaries")
    coms = bounds["communes"]
    com_idx = ShapeIndex([Shape([[proj(lon, lat) for lon, lat in r] for r in c["rings"]]) for c in coms], cell_km=20)

    def place(lon, lat):
        x, y = proj(lon, lat)
        cell = grid.cell_at(x, y)
        if cell < 0:
            return None
        if owner[cell] < 0:
            near = [n for n in grid.neighbours(cell) if owner[n] >= 0]
            if not near:  # one ring further (an island or a cape site)
                near = [m for n in grid.neighbours(cell) for m in grid.neighbours(n) if owner[m] >= 0]
            if not near:
                return None
            cell = min(near, key=lambda n: (grid.center(*grid.col_row(n))[0] - x) ** 2 + (grid.center(*grid.col_row(n))[1] - y) ** 2)
        k = com_idx.locate(x, y)  # the commune under the site itself (a hex can straddle a border)
        if k >= 0:
            commune, dep, epci = coms[k]["code"], coms[k]["dep"], coms[k]["epci"]
        else:
            smp = samples[cell]
            commune = communes[smp[0]] if smp and smp[0] >= 0 else None
            dep, ci = states[owner[cell]], world["county"][cell]
            epci = world["counties"][ci] if ci >= 0 else None
        return {"x": round(x, 1), "y": round(y, 1), "cell": cell, "cells": None, "county": epci,
                "cbsa": aav_of.get(commune), "state": dep}

    wonders = []
    parks = sorted(wd["parks"], key=lambda p: -(p["area_km2"] or 0))
    for k, p in enumerate(parks, 1):
        at = place(p["lon"], p["lat"])
        if not at:
            continue
        wonders.append({"id": f"pn-{p['qid']}", "name": cap(p["name"]), "short": cap(p["name"]).replace("Parc national ", "").replace("des ", "").replace("de la ", "").replace("du ", "").replace("de ", ""),
                        "kind": "natural", "rule": "national_park", "rank": k,
                        "metrics": {"visits": None, "year": p["year"], "area_km2": p["area_km2"], "unit_type": "Parc national"},
                        "curated": False, **at})
    whs = [s for s in wd["unesco"]]
    whs.sort(key=lambda s: (s["year"] or 9999, int(s["id"])))
    for k, s in enumerate(whs, 1):
        at = place(s["lon"], s["lat"])
        if not at:
            continue
        name = cap(s["name"])
        wonders.append({"id": f"whs-{s['id']}", "name": name, "short": SHORT.get(s["id"], name),
                        "kind": "natural" if s["id"] in NATURAL_WHS else "landmark", "rule": "unesco", "rank": k,
                        "metrics": {"inscribed": s["year"], "whs_id": s["id"], "visits": None},
                        "curated": False, **at})
    # Landmarks first (they are listed last, but a museum must not repeat one).
    landmarks = []
    marks = sorted(wd["landmarks"], key=lambda m: CURATED.get(m["name"], m["name"]))
    for m in marks:
        if m["name"] not in CURATED:
            continue
        at = place(m["lon"], m["lat"])
        if not at:
            continue
        landmarks.append({"id": f"lm-{m['qid']}", "name": CURATED[m["name"]], "short": CURATED[m["name"]],
                          "kind": CURATED_KIND[m["name"]], "rule": "landmark", "rank": len(landmarks) + 1,
                          "metrics": {}, "curated": True, **at})

    # Museums: the most visited, at most PER_CITY per area; one that is already a wonder lends it its visits.
    museums, museum_visits, museum_year = [], 0, None
    try:
        mus = load_interim_payload("museums")["data"]
    except FileNotFoundError:
        mus = None
        print("    museums interim missing: no museum wonders")
    per_city_m: Counter = Counter()
    for m in (mus or {}).get("museums", []):
        if len(museums) >= N_MUSEUMS:
            break
        name = m["name"] or MUSEUM_BY_COMMUNE.get(m["commune"])
        if not name:
            continue
        m = {**m, "name": name}
        pt = (m["lon"], m["lat"]) if m["lon"] is not None else bounds["mairies"].get(m["commune"])
        at = place(*pt) if pt else None
        if not at:
            continue
        mw = words(name)
        twin = next((w for w in wonders + landmarks if mw & words(w["name"] + " " + w["short"])
                     and (w["x"] - at["x"]) ** 2 + (w["y"] - at["y"]) ** 2 < DUP_KM ** 2), None)
        if twin:
            if twin["metrics"].get("visits") is None:
                twin["metrics"]["visits"], twin["metrics"]["visits_year"] = m["visits"], mus["year"]
                twin["metrics"]["visits_of"] = cap(name)
            continue
        if at["cbsa"] and per_city_m[at["cbsa"]] >= PER_CITY:
            continue

        per_city_m[at["cbsa"]] += 1
        museum_visits += m["visits"]
        museum_year = mus["year"]
        museums.append({"id": f"mus-{m['id'] or m['commune']}", "name": cap(name), "short": museum_short(m),
                        "kind": "landmark", "rule": "museum", "rank": len(museums) + 1,
                        "metrics": {"visits": m["visits"], "year": mus["year"]}, "curated": False, **at})
    wonders += museums

    per_city: Counter = Counter()
    k = 0
    for u in unis["data"]["universities"]:
        at = place(u["lon"], u["lat"])
        if not at:
            continue
        if at["cbsa"] and per_city[at["cbsa"]] >= PER_CITY:
            continue
        per_city[at["cbsa"]] += 1
        k += 1
        wonders.append({"id": f"univ-{u['id']}", "name": u["name"], "short": uni_short(u["name"]),
                        "kind": "university", "rule": "research_university", "rank": k,
                        "metrics": {"enrollment": u["students"], "enrollment_year": unis["data"]["year"], "year": unis["data"]["year"], "rd_usd": None},
                        "curated": False, **at})
        if k >= N_UNIVERSITIES:
            break
    wonders += landmarks
    # One wonder per hex, in rule order: a wonder whose hex is taken moves to the nearest free land hex (one ring,
    # then two); x/y keep the true position. Dense places (Paris, Lyon, Caen) otherwise stack their glyphs.
    taken: set[int] = set()
    moved = 0
    for w in wonders:
        if w["cell"] in taken:
            ring1 = [n for n in grid.neighbours(w["cell"]) if owner[n] >= 0]
            ring2 = [m for n in ring1 for m in grid.neighbours(n) if owner[m] >= 0]
            for ring in (ring1, ring2):
                free = [n for n in ring if n not in taken]
                if free:
                    w["cell"] = min(free, key=lambda n: (grid.center(*grid.col_row(n))[0] - w["x"]) ** 2
                                    + (grid.center(*grid.col_row(n))[1] - w["y"]) ** 2)
                    moved += 1
                    break
        taken.add(w["cell"])
    for w in wonders:
        w["key"] = w["id"]
    write_web("wonders.json", {
        "version": 1,
        "vintage": {"parks": wd_payload["vintage"], "unesco": wd_payload["vintage"], "universities": unis["vintage"],
                    "landmarks": wd_payload["vintage"],
                    "museums": f"Fréquentation des musées de France {museum_year}" if museum_year else None},
        "sources": ["wikidata_wonders", "universities"] + (["museums"] if mus else []),
        "rules": RULES,
        "national": {"park_visits": None, "park_visits_year": None, "whs": sum(1 for w in wonders if w["rule"] == "unesco"),
                     "museum_visits": museum_visits or None, "museum_visits_year": museum_year},
        "wonders": wonders,
    })
    print(f"    {moved} wonders moved to a free neighbouring hex")
    print(f"    {len(wonders)} wonders: " + ", ".join(f"{r['id']} {sum(1 for w in wonders if w['rule'] == r['id'])}" for r in RULES))
