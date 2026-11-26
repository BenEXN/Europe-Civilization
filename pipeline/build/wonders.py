"""Wonders: the UNESCO World Heritage properties of the map's countries, picked by a published rule.

* unesco: from UNESCO's World Heritage List (sources/unesco.py): every natural and mixed property, the cultural
  properties inscribed up to CULTURAL_UNTIL, and, for a country still without a wonder, its earliest inscription.
  A serial or transboundary property appears once, at its first component (by UNESCO reference number) that lies on
  the land of one of its States Parties on this map; properties with no such component (New Caledonia, Curaçao…)
  are left out.

The rule id stays "unesco" (the France port's id, which the browser's tooltips and the Culture advisor key on).
Writes web/data/wonders.json (loaded eagerly; a few tens of kB).
"""

from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path

from ..core.europe import COUNTRIES
from ..core.geo import MapProjection
from ..core.hexgrid import HexGrid
from ..core.paths import WEB_DATA
from ..core.store import load_interim, load_interim_payload, write_web
from .cities import ring_search

REQUIRES = ["_world", "_places", "unesco", "cities.json"]
PRODUCES = ["wonders.json"]

RULE = "unesco"
CULTURAL_UNTIL = 1996  # cultural properties inscribed up to this year (the list's first two decades)
SNAP_RINGS = 3  # a component in the sea or across a border looks this many hexes away for its country's land
PLACE_KM = 25  # a point's country is that of the nearest local unit this close (see country_at)
BUCKET = 100.0  # map units per bucket of the local-unit index
RULES = [
    {"id": RULE, "kind": "landmark", "kinds": ["landmark", "natural"],
     "text": "UNESCO World Heritage properties of the map's countries (World Heritage List, UNESCO): every natural "
             f"and mixed property, the cultural properties inscribed from 1978 to {CULTURAL_UNTIL}, and for each "
             "country still without one its earliest-inscribed property. A serial or transboundary property appears "
             "once, at its first listed component (by UNESCO reference number) on a State Party's land; properties "
             "outside the map (New Caledonia, Curaçao…) are left out. Ranked by year of inscription."},
]

# Map labels for long official names, by UNESCO id (the rest are shortened by short_name()).
SHORT = {
    "91": "Rome", "203": "Royal Saltworks", "549": "Caserta", "732": "Kutná Hora", "1758": "Limfjord fossils",
    "93": "The Last Supper", "400": "Budapest", "623": "Rammelsberg and Goslar", "1133": "Primeval beech forests",
    "31": "Auschwitz-Birkenau", "228": "Avignon", "618": "Banská Štiavnica", "669": "Camino Francés",
    "601": "Reims", "809": "Poreč", "1657": "Mount Pelée", "755": "Oporto", "826": "Cinque Terre", "367": "Trier",
    "758": "Pannonhalma", "163": "Orange", "258": "Gulf of Porto", "229": "Places of Nancy", "659": "Brú na Bóinne",
    "829": "Pompeii", "804": "Palau de la Música", "169": "Würzburg Residence", "206": "Angra do Heroísmo",
    "310": "Altamira", "670": "Sassi of Matera", "85": "Vézère valley caves", "263": "Belém", "537": "Daphni",
    "620": "Spiš Castle", "1604": "Vatnajökull", "97": "Split", "187": "Hildesheim", "699": "Luxembourg",
    "456": "Thessalonika", "690": "Zelená Hora", "712": "Vicenza", "806": "Hallstatt", "535": "Quedlinburg",
    "1195": "Geirangerfjord", "312": "Oviedo", "383": "Seville", "729": "Bauhaus", "733": "Ferrara",
    "780": "Aigai (Vergina)", "99": "Ohrid", "827": "Modena", "596": "Fortified churches", "288": "Brühl",
    "348": "Ávila", "125": "Kotor", "1317": "Réunion", "1434": "Chaîne des Puys", "401": "Hollókő",
    "665": "Guadalupe", "783": "Luther memorials", "314": "Alhambra", "318": "El Escorial", "269": "Müstair",
    "230": "Saint-Savin", "725": "Aggtelek caves", "55": "Røros", "532": "Potsdam", "697": "Jelling",
    "784": "Salzburg", "824": "Padua botanical garden", "847": "Malbork", "32": "Wieliczka", "345": "Carcassonne",
    "351": "Troodos churches", "823": "Savoy residences", "164": "Arles", "789": "Pienza", "822": "Tallinn",
    "311": "Segovia", "392": "Bassae", "788": "Ravenna", "805": "San Millán", "491": "Epidaurus",
    "495": "Strasbourg", "763": "Lednice-Valtice", "818": "Kinderdijk", "347": "Santiago de Compostela",
    "595": "Samos", "664": "Mérida", "160": "Fontainebleau", "515": "Lorsch", "550": "San Gimignano",
    "617": "Český Krumlov", "762": "Gammelstad", "786": "Schönbrunn", "831": "Agrigento", "898": "High Coast",
    "417": "Ibiza", "751": "Verla", "782": "Lonja de Valencia", "1719": "Mount Olympus", "378": "Mudéjar Aragon",
    "511": "Mystras", "517": "Olympia", "781": "Cuenca", "45": "Ivanovo", "80": "Mont-Saint-Michel",
    "83": "Versailles", "344": "Pont du Gard", "393": "Delphi", "430": "Roman frontiers", "559": "Drottningholm",
    "908": "Aeolian Islands", "94": "Valcamonica", "98": "Plitvice Lakes", "165": "Fontenay", "723": "Sintra",
    "1179": "Sardona", "132": "Megalithic temples", "174": "Florence", "546": "Maulbronn", "265": "Tomar",
    "313": "Córdoba", "359": "Sveshtari", "739": "Schokland", "29": "Kraków", "30": "Warsaw", "44": "Kazanlak",
    "271": "Wies", "616": "Prague", "726": "Naples", "759": "Water defence lines",
    "787": "Alberobello", "1037": "Jungfrau-Aletsch", "1314": "Wadden Sea", "1187": "Struve Arc",
    "1363": "Pile dwellings", "1613": "Great Spa Towns", "33": "Białowieża", "773": "Pyrénées-Mont Perdu",
    "994": "Curonian Spit", "772": "Neusiedlersee", "1090": "Monte San Giorgio", "1153": "Causses and Cévennes",
    "1692": "Apennine gypsum karst", "395": "Pisa", "264": "Batalha", "505": "Alcobaça", "557": "Tanum",
    "600": "Banks of the Seine", "583": "Suomenlinna",
}


def short_name(pid: str, name: str) -> str:
    """A map label: SHORT, else the name without 'Historic Centre of' and the like, cut at its first clause."""
    if pid in SHORT:
        return SHORT[pid]
    n = re.sub(r"^The ", "", name.strip())
    n = re.sub(r"^(Historic(al)?|Old|Medieval|Ancient)\s+(Centre|Center|City|Town|Quarter)( \(Old Town\))? of (the )?",
               "", n)
    n = re.sub(r"^(Hanseatic )?(City|Town) of ", "", n)
    n = re.split(r" – | - |: |, ", n)[0].strip()
    n = re.sub(r" (National Park|Nature Reserve|Historic Centre|and its Lagoon|Fossil Site)$", "", n)
    return n if len(n) <= 30 else n[:29].rstrip() + "…"


def _ref_key(ref: str) -> tuple:
    m = re.search(r"-(\d+)", ref)
    return (int(m.group(1)) if m else 0, ref)


def build() -> None:
    world = load_interim("_world")
    payload = load_interim_payload("unesco")
    props = payload["data"]["properties"]
    grid, proj, owner = HexGrid(**world["grid"]), MapProjection(**world["projection"]), world["owner"]
    states, counties, county = world["states"], world["counties"], world["county"]
    state_index = {c: i for i, c in enumerate(states)}
    places = load_interim("_places")
    col = {k: i for i, k in enumerate(places["columns"])}
    buckets: dict[tuple, list] = {}
    for r in places["rows"]:
        x, y, k = r[col["x"]], r[col["y"]], state_index.get(r[col["country"]])
        if x is not None and k is not None:
            buckets.setdefault((int(x // BUCKET), int(y // BUCKET)), []).append((x, y, k))
    cities = json.loads((WEB_DATA / "cities.json").read_text())
    city_of: dict[int, str] = {}
    for c in sorted(cities, key=lambda c: -(c.get("population") or 0)):
        for cell in c.get("footprint") or [c["cell"]]:
            city_of.setdefault(cell, c["id"])

    def nearest(cell: int, x: float, y: float, ok, rings: int):
        """The land cell nearest (x, y) within `rings` of `cell` that passes ok(), or None."""
        best = None
        for ring, c in ring_search(grid, cell, rings):
            if best is not None and ring > best[0]:
                break
            if owner[c] >= 0 and ok(c):
                cx, cy = grid.center(*grid.col_row(c))
                d = (cx - x) ** 2 + (cy - y) ** 2
                if best is None or d < best[1]:
                    best = (ring, d, c)
        return best[2] if best else None

    def country_at(x: float, y: float) -> int | None:
        """Index of the country a point lies in: that of the nearest local unit within PLACE_KM (a hex's owner is
        the majority of its land, which on a narrow strip such as Dubrovnik's can be the neighbour)."""
        bx, by = int(x // BUCKET), int(y // BUCKET)
        best = None
        for i in range(bx - 1, bx + 2):
            for j in range(by - 1, by + 2):
                for px, py, k in buckets.get((i, j), ()):
                    d = (px - x) ** 2 + (py - y) ** 2
                    if d <= (PLACE_KM * proj.scale) ** 2 and (best is None or d < best[0]):
                        best = (d, k)
        return best[1] if best else None

    def place(p: dict, only: str | None = None):
        """(x, y, cell): the first component (by reference number) on a State Party's land; one in the sea, in a hex
        the neighbour owns, or on a border river, moves to that party's nearest land. Failing that (Kosovo's monuments, inscribed by
        Serbia), the first component on any map country's land. `only` restricts the search to one country."""
        parties = {state_index[only]} if only else {state_index[s] for s in p["states"] if s in state_index}
        pts = []
        for c in sorted(p["components"], key=lambda c: _ref_key(c["ref"])) + (
                [{"lon": p["centroid"][0], "lat": p["centroid"][1]}] if p["centroid"] else []):
            x, y = proj(c["lon"], c["lat"])
            cell = grid.cell_at(x, y)
            if cell >= 0:
                pts.append((x, y, cell))
        for x, y, cell in pts:
            if owner[cell] in parties:
                return x, y, cell
        for x, y, cell in pts:  # in the sea or in the party's own land: up to SNAP_RINGS; else (a border river) 1
            where = country_at(x, y)
            rings = SNAP_RINGS if where in parties or (owner[cell] < 0 and where is None) else 1
            near = nearest(cell, x, y, lambda c: owner[c] in parties, rings)
            if near is not None:
                return x, y, near
        if only:
            return None
        for x, y, cell in pts:
            near = nearest(cell, x, y, lambda c: True, SNAP_RINGS)
            if near is not None:
                return x, y, near
        return None

    def wonder(p: dict, at: tuple) -> dict:
        x, y, cell = at
        here = states[owner[cell]]
        w = {"id": f"whs-{p['id']}", "name": p["name"], "short": short_name(p["id"], p["name"]),
             "kind": "landmark" if p["category"] == "Cultural" else "natural", "rule": RULE, "rank": 0,
             "metrics": {"inscribed": p["year"], "whs_id": p["id"], "category": p["category"],
                         "area_km2": round(p["area_ha"] / 100, 1 if p["area_ha"] >= 1000 else 3) if p["area_ha"] else None,
                         "in_danger": p["danger"], "visits": None,
                         "states_parties": [s for s in p["states"]] if p["transboundary"] else None},
             "x": round(x, 1), "y": round(y, 1), "cell": cell, "cells": None,
             "county": counties[county[cell]] if county[cell] >= 0 else None, "cbsa": city_of.get(cell),
             "state": here, "curated": False}
        if here not in p["states"]:
            w["state_note"] = (f"Inscribed by {', '.join(p['states_names'])}; the site lies in "
                               f"{COUNTRIES[here][0]} on this map.")
        return w

    chosen, skipped = [], []
    for p in props:
        if p["category"] != "Cultural" or p["year"] <= CULTURAL_UNTIL:
            at = place(p)
            if at:
                chosen.append(wonder(p, at))
            else:
                skipped.append(p["name"])
    # Every country with a World Heritage property shows at least one: its earliest inscription, placed on its land.
    have = {w["state"] for w in chosen}
    taken_ids = {w["id"] for w in chosen}
    added = []
    for code in COUNTRIES:
        if code in have:
            continue
        for p in sorted((p for p in props if code in p["states"]), key=lambda p: (p["year"], int(p["id"]))):
            if f"whs-{p['id']}" in taken_ids:
                continue
            at = place(p, only=code)
            if at:
                chosen.append(wonder(p, at))
                taken_ids.add(f"whs-{p['id']}")
                added.append(f"{code}: {short_name(p['id'], p['name'])} ({p['year']})")
                break
    chosen.sort(key=lambda w: (w["metrics"]["inscribed"], int(w["metrics"]["whs_id"])))
    for k, w in enumerate(chosen, 1):
        w["rank"] = k
    # One wonder per hex, in rank order: a wonder whose hex is taken moves to the nearest free hex of the same
    # country (one ring, then two); x/y keep the true position. Dense places (Rome, Venice, Florence) otherwise stack
    # their glyphs. Malta, a single hex, keeps its three on one.
    taken: set[int] = set()
    moved = 0
    for w in chosen:
        if w["cell"] in taken:
            own = owner[w["cell"]]
            ring1 = [n for n in grid.neighbours(w["cell"]) if owner[n] == own]
            ring2 = [m for n in ring1 for m in grid.neighbours(n) if owner[m] == own]
            for ring in (ring1, ring2):
                free = [n for n in ring if n not in taken]
                if free:
                    w["cell"] = min(free, key=lambda n: (grid.center(*grid.col_row(n))[0] - w["x"]) ** 2
                                    + (grid.center(*grid.col_row(n))[1] - w["y"]) ** 2)
                    moved += 1
                    break
        taken.add(w["cell"])
    for w in chosen:
        w["key"] = w["id"]
    listed = sum(1 for p in props if any(s in COUNTRIES for s in p["states"]))
    write_web("wonders.json", {
        "version": 1,
        "vintage": {"unesco": payload["vintage"]},
        "sources": ["unesco"],
        "rules": RULES,
        "national": {"park_visits": None, "park_visits_year": None, "whs": len(chosen), "whs_listed": listed,
                     "museum_visits": None, "museum_visits_year": None},
        "wonders": chosen,
    })
    kinds = Counter(w["kind"] for w in chosen)
    print(f"    {len(chosen)} wonders ({dict(kinds)}) of {listed} properties listed; {moved} moved to a free hex")
    if added:
        print(f"    earliest inscription added for: {'; '.join(added)}")
    if skipped:
        print(f"    {len(skipped)} off the map: {'; '.join(skipped)}")


# ------------------------------------------------------------------ check


def check(web_dir: Path) -> list[tuple[str, str]]:
    path = Path(web_dir) / "wonders.json"
    if not path.exists():
        return [("NOTE", "wonders.json not built (optional; run: build wonders)")]
    doc = json.loads(path.read_text())
    out: list[tuple[str, str]] = []
    for k in ("version", "vintage", "sources", "rules", "national", "wonders"):
        if k not in doc:
            out.append(("FAIL", f"wonders.json lacks '{k}'"))
    if out:
        return out
    rules = {r.get("id"): r for r in doc["rules"]}
    if any(not r.get("text") or not r.get("kinds") for r in rules.values()):
        out.append(("FAIL", "wonders.json: every rule needs a text and kinds"))
    wpath = Path(web_dir) / "world.json"
    world = json.loads(wpath.read_text()) if wpath.exists() else {}
    owner = world.get("owner") or []
    abbrs = {s.get("abbr") for s in world.get("states", [])}
    geoids = {c.get("geoid") for c in world.get("counties", [])}
    cpath = Path(web_dir) / "cities.json"
    city_ids = {c.get("id") for c in json.loads(cpath.read_text())} if cpath.exists() else None
    keys = {"id", "name", "short", "kind", "rule", "rank", "metrics", "x", "y", "cell", "cells", "county", "cbsa",
            "state", "curated"}
    probs = Counter()
    for w in doc["wonders"]:
        if not keys <= w.keys():
            probs["missing keys"] += 1
            continue
        rule = rules.get(w["rule"])
        if rule is None or w["kind"] not in rule.get("kinds", [rule.get("kind")]):
            probs["rule/kind"] += 1
        if not isinstance(w["cell"], int) or (owner and not (0 <= w["cell"] < len(owner) and owner[w["cell"]] >= 0)):
            probs["cell not a map-country land hex"] += 1
        if abbrs and w["state"] not in abbrs:
            probs["state not a world.json country"] += 1
        if w["county"] is not None and geoids and w["county"] not in geoids:
            probs["county not a world.json region"] += 1
        if w["cbsa"] is not None and city_ids is not None and w["cbsa"] not in city_ids:
            probs["cbsa not a cities.json id"] += 1
        if not isinstance(w["rank"], int) or w["rank"] < 1:
            probs["rank"] += 1
    ids = [w.get("id") for w in doc["wonders"]]
    if len(ids) != len(set(ids)):
        probs["duplicate ids"] += 1
    shared = Counter(w.get("cell") for w in doc["wonders"])
    shared = sorted({w["state"] for w in doc["wonders"] if shared[w.get("cell")] > 1})
    if shared:
        out.append(("NOTE", f"wonders.json: wonders share a hex in {shared} (no free land hex of the country nearby)"))
    if probs:
        out.append(("FAIL", f"wonders.json: {dict(probs)}"))
    else:
        per = Counter(w["kind"] for w in doc["wonders"])
        countries = len({w["state"] for w in doc["wonders"]})
        out.append(("PASS", f"wonders.json: {len(doc['wonders'])} wonders in {countries} countries "
                            f"({', '.join(f'{k} {n}' for k, n in per.most_common())})"))
    size = path.stat().st_size
    if size > 300_000:
        out.append(("WARN", f"wonders.json is {size / 1e3:.0f} kB (eager files should stay under ~300 kB)"))
    return out
