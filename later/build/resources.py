"""Tile resources: the real power plants and vineyards of France, placed on the hex map.

Like strategic resources on a Civ tile, but only meaningful sites: each type has a size threshold (stated in its
description). Plants come from the national register of electricity installations (ODRÉ), placed at the town hall
of their commune. Wind, solar and battery projects are filed as many installations, so they are summed per hex
first. Vineyards come from CORINE Land Cover: a hex whose land is mostly vines, thinned to a lattice so the map
shows a wine region, not a wall of icons. `types` is listed in rank order (rarest/most significant first).
"""

from __future__ import annotations

import re
from collections import defaultdict

from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.store import load_interim, write_web
from .cities import nearest_land

REQUIRES = ["_world", "fr_boundaries", "odre_registre", "insee_aav", "cities.json"]
PRODUCES = ["resources.json"]

PLANT_MIN = {"hydro": 100, "coal_plant": 100, "gas_plant": 300, "pumped_storage": 100}  # MW, per site (commune)
CLUSTER_MIN = {"wind": 50, "solar": 50, "battery": 30}  # MW, summed per hex
VINE_MIN = 0.25  # share of the hex's land in vineyards
SRC = "odre_registre"
IN_SERVICE = "Seules les installations en service comptent."
CLUSTER = "Les installations sont additionnées par hexagone (un parc est souvent déclaré en plusieurs tranches)."


def _t(id, name, category, color, unit, description, source=SRC):
    return {"id": id, "name": name, "category": category, "icon": f"r-{id}", "color": color,
            "unit": unit, "description": description, "source": source}


TYPES = [
    _t("nuclear", "Centrale nucléaire", "energy", "#e8d44d", "MW",
       f"Chaque centrale nucléaire en service ; la valeur est la puissance installée de ses réacteurs. {IN_SERVICE}"),
    _t("pumped_storage", "Station de pompage (STEP)", "energy", "#2f7fb8", "MW",
       f"Stations de transfert d'énergie par pompage d'au moins {PLANT_MIN['pumped_storage']} MW : deux réservoirs qui "
       "servent de batterie au réseau."),
    _t("tidal", "Usine marémotrice", "energy", "#3f8fd6", "MW", "L'usine marémotrice de la Rance."),
    _t("hydro", "Barrage hydroélectrique", "energy", "#3fa7d6", "MW",
       f"Centrales hydroélectriques (lac, éclusée, fil de l'eau) d'au moins {PLANT_MIN['hydro']} MW par commune. {IN_SERVICE}"),
    _t("coal_plant", "Centrale à charbon", "energy", "#5a5a5a", "MW",
       f"Centrales au charbon d'au moins {PLANT_MIN['coal_plant']} MW. {IN_SERVICE}"),
    _t("gas_plant", "Centrale à gaz", "energy", "#f08a24", "MW",
       f"Centrales au gaz (cycles combinés, turbines à combustion, cogénération) d'au moins {PLANT_MIN['gas_plant']} MW "
       f"par commune. {IN_SERVICE}"),
    _t("wind", "Parcs éoliens", "energy", "#9fd8cb", "MW",
       f"Éolien terrestre là où un hexagone totalise au moins {CLUSTER_MIN['wind']} MW, et chaque parc éolien en "
       f"mer (rattaché à la côte, sur l'hexagone de sa commune de raccordement). {CLUSTER} {IN_SERVICE}"),
    _t("solar", "Centrales solaires", "energy", "#ffc93c", "MW",
       f"Solaire au sol là où un hexagone totalise au moins {CLUSTER_MIN['solar']} MW (les toitures et petites "
       f"installations ne sont pas comptées). {CLUSTER} {IN_SERVICE}"),
    _t("battery", "Batteries", "energy", "#7bc96f", "MW",
       f"Stockage par batteries là où un hexagone totalise au moins {CLUSTER_MIN['battery']} MW. {CLUSTER}"),
    _t("wine", "Vignoble", "agri", "#8e2c55", "% de vignes",
       f"Hexagones dont au moins {round(VINE_MIN * 100)} % des terres sont des vignobles (CORINE Land Cover 2018, "
       "poste 221), éclaircis à environ un hexagone sur quatre sur une grille régulière ; la valeur est la part de "
       "vignes. Le nom est celui du grand vignoble du département.", "clc"),
]
RANK = {t["id"]: i for i, t in enumerate(TYPES)}

# Département → the wine region it is best known for (for the vineyard tooltip).
VIGNOBLES = {
    "33": "Bordelais", "24": "Bergerac", "47": "Côtes de Duras", "32": "Gascogne (Armagnac)", "40": "Tursan",
    "64": "Jurançon et Madiran", "16": "Cognac", "17": "Cognac", "51": "Champagne", "02": "Champagne",
    "10": "Champagne (Côte des Bar)", "21": "Bourgogne (Côte-d'Or)", "71": "Bourgogne (Mâconnais)",
    "89": "Chablis", "69": "Beaujolais", "67": "Alsace", "68": "Alsace", "26": "Côtes du Rhône",
    "84": "Côtes du Rhône et Ventoux", "30": "Costières et Côtes du Rhône", "07": "Côtes du Rhône",
    "34": "Languedoc", "11": "Corbières et Minervois", "66": "Roussillon", "83": "Côtes de Provence",
    "13": "Provence", "06": "Bellet", "2A": "Vins de Corse", "2B": "Vins de Corse", "49": "Anjou-Saumur",
    "37": "Touraine", "41": "Touraine", "44": "Muscadet", "18": "Sancerre", "58": "Pouilly",
    "39": "Jura", "73": "Savoie", "74": "Savoie", "46": "Cahors", "81": "Gaillac", "82": "Fronton",
    "31": "Fronton", "12": "Marcillac", "57": "Moselle", "54": "Côtes de Toul", "38": "Isère", "42": "Côte Roannaise",
    "63": "Côtes d'Auvergne", "79": "Haut-Poitou", "86": "Haut-Poitou", "85": "Fiefs Vendéens",
}


SMALL = {"de", "du", "des", "la", "le", "les", "en", "sur", "sous", "et", "aux", "au", "d", "l", "lès", "lez"}


def nice_case(n: str) -> str:
    """'DAMPIERRE-EN-BURLY' → 'Dampierre-en-Burly'; 'TRICASTIN (LE)' → 'Le Tricastin'."""
    m = re.match(r"^(.*?)\s*\((LE|LA|LES|L')\)\s*$", n, re.I)
    if m:
        art = m.group(2).capitalize()
        n = f"{art}{'' if art.endswith(chr(39)) else ' '}{m.group(1)}"
    parts = re.split(r"([ \-'’])", n.lower())
    out = []
    for k, w in enumerate(parts):
        out.append(w if (w in SMALL and k > 0) or not w else w[:1].upper() + w[1:])
    return "".join(out)


def site_name(name: str, kind: str) -> str:
    """'CRUA5N04 - GROUPE 04 DE LA CENTRALE NUCLEAIRE DE CRUAS' → 'Cruas';
    'G.MAIH-CENTRALE HYDRAULIQUE DE GRAND-MAISON-7' → 'Grand-Maison'."""
    n = re.sub(r"^[A-Z0-9]{4,8}\s*-\s*", "", name.strip())
    n = re.sub(r"^[A-Z]\.[A-Z]{3,5}-", "", n, flags=re.I)
    n = re.sub(r".*CENTRALE\s+(NUCL[EÉ]AIRE|HYDRAULIQUE|THERMIQUE|[EÉ]LECTRIQUE)?\s*D[EU]?\s*(LA |LE |L')?", "", n, flags=re.I)
    n = re.sub(r"\b(GROUPE|TRANCHE|TR|UNITE|UNITÉ)\s*\d+\b.*", "", n, flags=re.I)
    n = re.sub(r"[-\s]+\d+$", "", n).strip(" -")
    n = re.sub(r"\s*\((?!LE\)|LA\)|LES\)|L'\)).*?\)", "", n, flags=re.I)  # '(Belleville-sur-Loire)'
    return nice_case(n) if n else ""


def of(name: str) -> str:
    """French 'de' + name with contraction: 'Le Tricastin' → 'du Tricastin', 'Annecy' → "d'Annecy"."""
    if name.startswith("Le "):
        return "du " + name[3:]
    if name.startswith("Les "):
        return "des " + name[4:]
    if name[:1].upper() in "AEIOUYÉÈÂÎÔ":
        return "d'" + name
    return "de " + name


def offshore_name(name: str) -> str | None:
    m = re.search(r"Ferme [EÉ]olienne d[eu] (.+)$", name, re.I)
    return nice_case(m.group(1).replace("-", " ").replace("St ", "Saint-")) if m else None


def kind_of(p: dict) -> str | None:
    f, techno, fuel = p["filiere"], p.get("techno") or "", p.get("fuel") or ""
    if f == "NUCLE":
        return "nuclear"
    if f == "HYDLQ":
        return "pumped_storage" if "Pompage" in techno else "hydro"
    if f == "MARIN":
        return "tidal"
    if f == "EOLIE":
        return "offshore" if "mer" in techno else "wind"
    if f == "SOLAI":
        return "solar"
    if f == "STOCK":
        return "battery"
    if f == "THERM":
        return "coal_plant" if fuel == "Charbon" else "gas_plant" if fuel == "Gaz" else None
    return None


def build() -> None:
    world = load_interim("_world")
    bounds = load_interim("fr_boundaries")
    plants = load_interim("odre_registre")["plants"]
    aav = load_interim("insee_aav")
    import json
    from ..core.paths import WEB_DATA

    city_ids = {c["id"] for c in json.loads((WEB_DATA / "cities.json").read_text())}
    aav_of = {c["code"]: c["aav"] for c in aav["communes"]}
    proj = MapProjection(**world["projection"])
    grid = HexGrid(**world["grid"])
    owner = world["owner"]
    states = world["states"]
    state_index = {code: i for i, code in enumerate(states)}
    dep_of = {c["code"]: c["dep"] for c in bounds["communes"]}

    def place(commune: str, rings: int = 3):
        pt = bounds["mairies"].get(commune)
        if not pt:
            return None
        x, y = proj(*pt)
        cell = grid.cell_at(x, y)
        if cell < 0 or owner[cell] < 0:
            cell = nearest_land(grid, owner, max(cell, 0), x, y, state_index.get(dep_of.get(commune, ""), -1), rings)
        return (x, y, cell) if cell >= 0 else None

    def item(type_, name, commune, x, y, cell, value, detail):
        a = aav_of.get(commune)
        return {"type": type_, "name": name, "x": round(x, 1), "y": round(y, 1), "cell": cell,
                "value": round(value) if type_ != "wine" else value, "detail": detail,
                "state": dep_of.get(commune) or states[owner[cell]], "cbsa": a if a in city_ids else None}

    items = []
    live = [p for p in plants if p["status"] == "En service"]
    # Sites (one per commune and kind): nuclear, hydro, pumped storage, tidal, thermal, offshore wind.
    sites: dict[tuple, dict] = {}
    for p in live:
        k = kind_of(p)
        if k in (None, "wind", "solar", "battery"):
            continue
        s = sites.setdefault((k, p["commune"]), {"mw": 0.0, "n": 0, "names": [], "since": []})
        s["mw"] += p["kw"] / 1000
        s["n"] += p.get("units") or 1
        s["names"].append(p["name"])
        if p["since"]:
            s["since"].append(p["since"])
    for (k, commune), s in sites.items():
        if k in PLANT_MIN and s["mw"] < PLANT_MIN[k]:
            continue
        where = place(commune)
        if not where:
            continue
        town = next((m["name"] for m in bounds["communes"] if m["code"] == commune), commune)
        name = site_name(s["names"][0], k) or town
        years = sorted(s["since"])
        since = f", en service depuis {years[0]}" if years else ""
        if k == "nuclear":
            detail = f"{s['n']} réacteur{'s' if s['n'] > 1 else ''}{since}"
            name = f"Centrale {of(name)}" if not name.lower().startswith("centrale") else name
        elif k == "offshore":
            detail = f"Parc éolien en mer{since}"
            name = f"Éolien en mer {of(offshore_name(s['names'][0]) or name)}"
            k = "wind"
        else:
            detail = f"{s['n']} groupe{'s' if s['n'] > 1 else ''}{since}"
        items.append(item(k, name, commune, *where, s["mw"], detail))
    # Clusters summed per hex: onshore wind, solar, batteries.
    cluster: dict[tuple, dict] = defaultdict(lambda: {"mw": 0.0, "n": 0, "communes": defaultdict(float), "names": []})
    for p in live:
        k = kind_of(p)
        if k not in CLUSTER_MIN:
            continue
        where = place(p["commune"], 1)
        if not where:
            continue
        c = cluster[(k, where[2])]
        c["mw"] += p["kw"] / 1000
        c["n"] += 1
        c["communes"][p["commune"]] += p["kw"] / 1000
        c["names"].append(p["name"])
    for (k, cell), c in cluster.items():
        if c["mw"] < CLUSTER_MIN[k]:
            continue
        commune = max(c["communes"], key=c["communes"].get)
        x, y = grid.center(*grid.col_row(cell))
        town = next((m["name"] for m in bounds["communes"] if m["code"] == commune), commune)
        label = {"wind": "Éolien", "solar": "Solaire", "battery": "Batteries"}[k]
        items.append(item(k, f"{label} {of(town)}", commune, x, y, cell, c["mw"],
                          f"{c['n']} installation{'s' if c['n'] > 1 else ''} dans l'hexagone"))
    # Vineyards from CORINE, on a lattice (axial q and r both even) so a region shows as a field of icons.
    for i, counts in enumerate(world["clc"]):
        if owner[i] < 0 or not counts:
            continue
        land = sum(n for code, n in counts.items() if not str(code).startswith("5"))
        share = counts.get("221", counts.get(221, 0)) / land if land else 0
        if share < VINE_MIN:
            continue
        col, row = grid.col_row(i)
        q = col - (row - (row & 1)) // 2
        if q % 2 or row % 2:
            continue
        x, y = grid.center(col, row)
        dep = states[owner[i]]
        items.append({"type": "wine", "name": VIGNOBLES.get(dep, "Vignoble"), "x": round(x, 1), "y": round(y, 1),
                      "cell": i, "value": round(share, 2), "detail": f"{round(share * 100)} % des terres en vignes",
                      "state": dep, "cbsa": None})

    items.sort(key=lambda it: (RANK[it["type"]], -it["value"]))
    national = {t["id"]: {"count": 0, "value": 0, "unit": t["unit"]} for t in TYPES}
    by_state: dict[str, dict] = defaultdict(dict)
    for it in items:
        n = national[it["type"]]
        n["count"] += 1
        n["value"] += it["value"]
        s = by_state[it["state"]].setdefault(it["type"], {"count": 0, "value": 0, "unit": n["unit"]})
        s["count"] += 1
        s["value"] += it["value"]
    national["wine"]["value"] = None
    for s in by_state.values():
        if "wine" in s:
            s["wine"]["value"] = None
    counts = {t: national[t]["count"] for t in national}
    print(f"    {len(items)} resources: {counts}")
    write_web("resources.json", {
        "types": TYPES,
        "items": items,
        "summary": {
            "note": "Totaux des seuls sites cartographiés (chaque type a son seuil) : ce ne sont pas les capacités "
                    "totales du pays ou des départements.",
            "national": national,
            "states": by_state,
        },
    })
